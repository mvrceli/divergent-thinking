import uuid
import io
import base64
import os
from difflib import get_close_matches

from dotenv import load_dotenv
import google.generativeai as genai

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import gensim.downloader as api
if os.environ.get("GENSIM_DATA_DIR"):
    api.BASE_DIR = os.environ["GENSIM_DATA_DIR"]
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from forward_flow import analyze_forward_flow

load_dotenv()
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
gemini_model = genai.GenerativeModel("gemini-2.0-flash")

app = Flask(__name__, static_folder="../frontend", static_url_path="")
CORS(app)


print("loading word2vec")
model = api.load("word2vec-google-news-300")
print("model loaded")

# initial possible words
STIMULUS_WORDS = [
    "ocean", "mountain", "bridge", "garden", "castle",
    "river", "forest", "mirror", "thunder", "candle",
    "shadow", "compass", "island", "clock", "diamond",
    "rocket", "desert", "puzzle", "library", "volcano",
]

TOTAL_TURNS = 20
MIN_RELATEDNESS = 0.10


INTERVENTION_START = 7  
INTERVENTION_END = 13   




sessions: dict[str, dict] = {}


def word_in_vocab(word: str) -> bool:
    return normalise(word) in model.key_to_index


def normalise(word: str) -> str:
    return word.strip().lower().replace(" ", "_")


def select_word_with_gemini(previous_word: str, candidate_words: list[str]):
    if not candidate_words:
        return None

    try:
        if len(candidate_words) == 1:
            return candidate_words[0]

        candidates_str = ", ".join(candidate_words)
        print(f"[GEMINI DEBUG] Previous word: '{previous_word}'")
        print(f"[GEMINI DEBUG] Candidate words ({len(candidate_words)}): {candidate_words}")

        prompt = f"""You are helping expand divergent thinking in a word association game.

Given the previous word: "{previous_word}"

And these candidate words: {candidates_str}

IMPORTANT RULES:
- You MUST choose a word from the list above. No substitutions, no similar words.
- You MUST only return a word that appears in the candidate list.
- Do NOT suggest a related word if it's not in the list.
- Do NOT modify or change any word from the list.
- Do NOT choose words that are plurals of one another.

Select the SINGLE BEST word from the list that:
1. Is COMMONLY KNOWN - avoid obscure, technical, or specialized terms
2. Is related to "{previous_word}", yet explores a new direction.
3. Makes sense as a next step in word association in a way that explores new topics.
4. Would help a typical person expand their thinking (not industry jargon)
5. Helps create unexpected but sensible connections

Respond with ONLY one word from the candidate list, nothing else. No explanation, no punctuation, just the word exactly as it appears in the list."""

        response = gemini_model.generate_content(prompt)
        selected_word = response.text.strip()
        print(f"[GEMINI DEBUG] Gemini response: '{selected_word}'")

        candidate_words_lower = [w.lower() for w in candidate_words]
        if selected_word.lower() in candidate_words_lower:
            original_idx = candidate_words_lower.index(selected_word.lower())
            matched_word = candidate_words[original_idx]
            print(f"[GEMINI DEBUG] Selected word '{selected_word}' matches candidate '{matched_word}' (exact match)")
            return matched_word

        close_matches = get_close_matches(selected_word.lower(), candidate_words_lower, n=1, cutoff=0.8)
        if close_matches:
            matched_lower = close_matches[0]
            original_idx = candidate_words_lower.index(matched_lower)
            matched_word = candidate_words[original_idx]
            print(f"[GEMINI DEBUG] Selected word '{selected_word}' non exact-matches candidate '{matched_word}'")
            return matched_word

        print(f"[GEMINI DEBUG] Gemini returned '{selected_word}' which is not in candidates. Using fallback.")
        return candidate_words[0]

    except Exception as e:
        print(f"Warning: Gemini API error: {e}. Falling back to first candidate.")
        return candidate_words[0] if candidate_words else None








def cosine_similarity(w1: str, w2: str):
    """Return cosine similarity between two words, or None if either is not in vocab."""
    w1, w2 = normalise(w1), normalise(w2)
    if w1 not in model.key_to_index or w2 not in model.key_to_index:
        return None
    return float(model.similarity(w1, w2))






def is_valid_word(word: str):
    """
    Check if a word is valid for suggestions.
    """
    if not word or len(word) < 3:
        return False
    
    # no underscores
    if "_" in word:
        return False
    
    # no digits
    if any(char.isdigit() for char in word):
        return False
    
    # punctuation check
    import string
    for char in word:
        if char in string.punctuation and char not in "-'":
            return False
    
    # no all caps
    if word.isupper() and len(word) > 1:
        return False
    

    
    return True







def find_words_at_new_location(word: str, min_sim: float = 0.3, max_sim: float = 0.5, num_words: int = 20) -> list[str]:
    """
    Find words near the half-magnitude point of the word's vector.
    1. Compute target = word_vec * 0.5.
    2. Scan the full vocabulary in chunks to find the 1000 nearest by Euclidean distance to target.
    3. Keep only those whose cosine similarity to the original word falls in [min_sim, max_sim].
    """
    import random

    word = normalise(word)
    if word not in model.key_to_index:
        return []

    try:
        reference_vec = model[word]
        ref_magnitude = np.linalg.norm(reference_vec)
        target_position = reference_vec * 0.5

        print(f"[VECTOR TRANSFORM] Word: '{word}'")
        print(f"[VECTOR TRANSFORM] Original magnitude: {ref_magnitude:.4f}  →  target magnitude: {np.linalg.norm(target_position):.4f}")

        vocab_size = len(model.key_to_index)
        all_distances = np.empty(vocab_size, dtype=np.float32)

        chunk_size = 50_000
        for start in range(0, vocab_size, chunk_size):
            end = min(start + chunk_size, vocab_size)
            chunk = model.vectors[start:end]
            diffs = chunk - target_position
            all_distances[start:end] = np.linalg.norm(diffs, axis=1)

        # find the 1000 nearest by Euclidean distance
        k = 1000
        nearest_indices = np.argpartition(all_distances, k)[:k]

        # compute cosine similarities for all 1000 nearest and log the distribution
        all_cosine_sims = []
        for idx in nearest_indices:
            candidate_word = model.index_to_key[idx]
            if candidate_word == word:
                continue
            candidate_vec = model.vectors[idx]
            candidate_norm = np.linalg.norm(candidate_vec)
            if candidate_norm > 0 and ref_magnitude > 0:
                cosine_sim = float(np.dot(reference_vec, candidate_vec) / (ref_magnitude * candidate_norm))
                all_cosine_sims.append((idx, candidate_word, cosine_sim))

        if all_cosine_sims:
            sims_only = [s for _, _, s in all_cosine_sims]
            print(f"[VECTOR TRANSFORM] Cosine sim distribution among 1000 nearest — "
                  f"min: {min(sims_only):.3f}, max: {max(sims_only):.3f}, "
                  f"mean: {np.mean(sims_only):.3f}, "
                  f"in range [{min_sim},{max_sim}]: {sum(min_sim <= s <= max_sim for s in sims_only)}")

        # filter by cosine similarity range
        candidates = []
        for _, word_str, sim in all_cosine_sims:
            if min_sim <= sim <= max_sim:
                candidates.append((word_str, sim))

        # convert and validate
        seen = set()
        valid_words = []
        for candidate_word, _ in candidates:
            # for multi-word compounds (e.g. "apricot_jelly"), extract the last token
            parts = candidate_word.split("_")
            word_to_check = parts[-1] if len(parts) > 1 else parts[0]
            if word_to_check in seen:
                continue
            if is_valid_word_for_suggestion(word_to_check):
                seen.add(word_to_check)
                valid_words.append(word_to_check)

        random.shuffle(valid_words)
        result = valid_words[:num_words]

        if result:
            print(f"[VECTOR TRANSFORM] {len(candidates)} passed cosine filter → {len(valid_words)} valid → returning {len(result)}: {result[:3]}")
        else:
            print(f"[VECTOR TRANSFORM] No valid words found in cosine range [{min_sim}, {max_sim}] among 1000 Euclidean-nearest.")

        return result
    except Exception as e:
        print(f"Error in find_words_at_new_location: {e}")
        return []




def is_valid_word_for_suggestion(word: str) -> bool:
    """
    Check if a converted word is valid for suggestions.
    """
    if not word or len(word) < 3:
        return False
    
    # reject multi words
    if " " in word:
        return False
    
    # check for digits
    if any(char.isdigit() for char in word):
        return False
    
    # check for unwanted punctuation 
    import string
    for char in word:
        if char in string.punctuation and char not in "-'":
            return False
    
    # all caps
    if word.isupper() and len(word) > 1:
        return False

    # starts with uppercase — likely a proper noun
    if word[0].isupper():
        return False

    # too rare — only allow top 150k most frequent words
    normalised = word.replace(" ", "_")
    rank = model.key_to_index.get(normalised)
    if rank is None or rank > 150_000:
        return False

    return True


def get_random_suggestion(num_attempts: int = 200):
    """Return a random valid word from the top 150k word2vec vocabulary."""
    import random
    top_k = 150_000
    indices = random.sample(range(top_k), min(num_attempts, top_k))
    for i in indices:
        candidate = model.index_to_key[i]
        parts = candidate.split("_")
        word_to_check = parts[-1] if len(parts) > 1 else parts[0]
        if is_valid_word_for_suggestion(word_to_check):
            return word_to_check
    return None


def compute_divergence(prompt_word: str, new_word: str, all_previous: list[str]):
    """
    Compute divergence metrics for a new word.
    """


    sim_to_prompt = cosine_similarity(prompt_word, new_word)

    sims_to_previous = []
    for pw in all_previous:
        s = cosine_similarity(new_word, pw)
        if s is not None:
            sims_to_previous.append({"word": pw, "similarity": round(s, 4)})

    if sims_to_previous:
        avg_sim_to_previous = round(float(np.mean([s["similarity"] for s in sims_to_previous])), 4)
    else:
        avg_sim_to_previous = None




    # divergence = 1 − similarity  (the higher the more divergent)
    if sim_to_prompt is not None:
        div_from_prompt = round(1 - sim_to_prompt, 4)
    else:
        div_from_prompt = None
    
    if avg_sim_to_previous is not None:
        div_from_previous = round(1 - avg_sim_to_previous, 4)
    else:
        div_from_previous = None

    if sim_to_prompt is not None:
        similarity_to_prompt = round(sim_to_prompt, 4)
    else:
        similarity_to_prompt = None
    


    return {
        "word": new_word,
        "prompt_word": prompt_word,
        "in_vocab": word_in_vocab(new_word),
        "similarity_to_prompt": similarity_to_prompt,
        "divergence_from_prompt": div_from_prompt,
        "similarities_to_previous": sims_to_previous,
        "avg_similarity_to_previous": avg_sim_to_previous,
        "divergence_from_previous": div_from_previous,
    }





def project_chain_to_3d(words: list[str]):
    """Project chain words into 3D using an SVD-based PCA projection."""
    vectors = []
    labels = []

    for word in words:
        key = normalise(word)
        if key in model.key_to_index:
            vectors.append(model[key])
            labels.append(word)

    if not vectors:
        return []

    matrix = np.asarray(vectors, dtype=np.float32)
    matrix = matrix - matrix.mean(axis=0, keepdims=True)

    if matrix.shape[0] == 1:
        coords = np.zeros((1, 3), dtype=np.float32)
    else:
        _, _, vt = np.linalg.svd(matrix, full_matrices=False)
        components = vt[:3]
        coords = matrix @ components.T

        if coords.shape[1] < 3:
            coords = np.pad(coords, ((0, 0), (0, 3 - coords.shape[1])), mode="constant")

    return [
        {
            "word": label,
            "x": float(point[0]),
            "y": float(point[1]),
            "z": float(point[2]),
        }
        for label, point in zip(labels, coords)
    ]






#APIS

@app.route("/api/start", methods=["POST"])
def start_game():
    """Start a new game session. Returns a session ID and an initial stimulus."""
    data = request.get_json(force=True) or {}
    mode = data.get("mode", "ai")
    if mode not in ("ai", "control"):
        mode = "ai"

    session_id = str(uuid.uuid4())
    stimulus = str(np.random.choice(STIMULUS_WORDS))
    sessions[session_id] = {
        "initial_stimulus": stimulus,
        "current_prompt": stimulus,
        "chain": [stimulus],
        "responses": [],
        "intervention_responses": [],
        "mode": mode,
    }
    return jsonify({
        "session_id": session_id,
        "stimulus": stimulus,
        "current_prompt": stimulus,
        "total_turns": TOTAL_TURNS,
        "intervention_start": INTERVENTION_START,
        "intervention_end": INTERVENTION_END,
        "mode": mode,
    })


@app.route("/api/respond", methods=["POST"])
def respond():
    """
    Submit a word association response for a session.
    """
    data = request.get_json(force=True)
    session_id = data.get("session_id")
    word = data.get("word", "").strip()

    if not session_id or session_id not in sessions:
        return jsonify({"error": "Invalid session"}), 400
    if not word:
        return jsonify({"error": "No word provided"}), 400

    session = sessions[session_id]
    if len(session["responses"]) >= TOTAL_TURNS:
        return jsonify({"error": "Session complete"}), 400




    prompt = session["current_prompt"]


    # check that the word is in vocabulary
    if not word_in_vocab(word):
        return jsonify({
            "rejected": True,
            "reason": f'"{word}" is not in the vocabulary. Try a different word.',
        }), 200

    # check if word is related enough
    sim = cosine_similarity(prompt, word)
    if sim is not None and sim < MIN_RELATEDNESS:
        return jsonify({
            "rejected": True,
            "reason": f'"{word}" is not related enough to "{prompt}" '
                      f'(similarity {sim:.2f}, need ≥ {MIN_RELATEDNESS}). '
                      f'Think of a word that connects to "{prompt}".',
            "similarity": round(sim, 4),
            "threshold": MIN_RELATEDNESS,
        }), 200

    # compute divergence against current prompt + full history
    all_previous = session["chain"]  # includes all prompts and responses so far
    result = compute_divergence(prompt, word, all_previous)
    session["responses"].append(result)

    # track if this was during intervention phase
    current_turn = len(session["responses"])
    in_intervention_phase = INTERVENTION_START <= current_turn <= INTERVENTION_END
    if in_intervention_phase:
        session["intervention_responses"].append({
            "turn": current_turn,
            "response": result,
        })

    # users word becomes the next prompt
    session["chain"].append(word)
    session["current_prompt"] = word

    done = len(session["responses"]) >= TOTAL_TURNS

    # get suggestions if correct phase
    suggestion = None
    suggestion_candidates = None
    if INTERVENTION_START <= len(session["responses"]) + 1 <= INTERVENTION_END:
        session_mode = session.get("mode", "ai")
        if session_mode == "control":
            suggestion = get_random_suggestion()
        else:
            suggestion_candidates = find_words_at_new_location(word, min_sim=0.3, max_sim=0.5, num_words=20)
            if suggestion_candidates:
                suggestion = select_word_with_gemini(word, suggestion_candidates)
                if not suggestion and suggestion_candidates:
                    suggestion = suggestion_candidates[0]

    return jsonify({
        "rejected": False,
        "turn": len(session["responses"]),
        "total_turns": TOTAL_TURNS,
        "result": result,
        "next_prompt": word,
        "done": done,
        "in_intervention_phase": in_intervention_phase,
        "suggestion": suggestion,
        "suggestion_candidates": suggestion_candidates,
    })


@app.route("/api/summary/<session_id>", methods=["GET"])
def summary(session_id: str):
    """Return the full session summary."""
    if session_id not in sessions:
        return jsonify({"error": "Invalid session"}), 400

    session = sessions[session_id]
    responses = session["responses"]
    chain_3d = project_chain_to_3d(session["chain"])

    divergences = []
    for r in responses:
        if r["divergence_from_prompt"] is not None:
            divergences.append(r["divergence_from_prompt"])
    avg_divergence = round(float(np.mean(divergences)), 4) if divergences else None





    # calculate divergence before and after intervention
    if len(responses) >= INTERVENTION_START - 1:
        before_intervention = responses[:INTERVENTION_START - 1]
    else:
        before_intervention = []
    
    if len(responses) >= INTERVENTION_START:
        during_intervention = responses[INTERVENTION_START - 1:INTERVENTION_END]
    else:
        during_intervention = []
    
    if len(responses) > INTERVENTION_END:
        after_intervention = responses[INTERVENTION_END:]
    else:
        after_intervention = []

    avg_divergence_before = None
    avg_divergence_during = None
    avg_divergence_after = None




    if before_intervention:
        divs_before = []
        for r in before_intervention:
            if r["divergence_from_prompt"] is not None:
                divs_before.append(r["divergence_from_prompt"])
        if divs_before:
            avg_divergence_before = round(float(np.mean(divs_before)), 4)
        else:
            avg_divergence_before = None

    if during_intervention:
        divs_during = []
        for r in during_intervention:
            if r["divergence_from_prompt"] is not None:
                divs_during.append(r["divergence_from_prompt"])
        if divs_during:
            avg_divergence_during = round(float(np.mean(divs_during)), 4)
        else:
            avg_divergence_during = None

    if after_intervention:
        divs_after = []
        for r in after_intervention:
            if r["divergence_from_prompt"] is not None:
                divs_after.append(r["divergence_from_prompt"])
        if divs_after:
            avg_divergence_after = round(float(np.mean(divs_after)), 4)
        else:
            avg_divergence_after = None



    return jsonify({
        "initial_stimulus": session["initial_stimulus"],
        "chain": session["chain"],
        "chain_3d": chain_3d,
        "responses": responses,
        "avg_divergence": avg_divergence,
        "avg_divergence_before_intervention": avg_divergence_before,
        "avg_divergence_during_intervention": avg_divergence_during,
        "avg_divergence_after_intervention": avg_divergence_after,
        "total_responses": len(responses),
        "intervention_start": INTERVENTION_START,
        "intervention_end": INTERVENTION_END,
    })








@app.route("/api/suggest/<session_id>", methods=["POST"])
def get_suggestion(session_id: str):
    """
    Get a suggestion for a given word based on embedding space position.
    """
    if session_id not in sessions:
        return jsonify({"error": "Invalid session"}), 400

    data = request.get_json(force=True)
    word = data.get("word", "").strip()

    if not word:
        return jsonify({"error": "No word provided"}), 400

    # find words at new location in embedding space with cosine similarity ranking
    suggestions = find_words_at_new_location(word, min_sim=0.3, max_sim=0.5, num_words=20)

    return jsonify({
        "word": word,
        "suggestions": suggestions,
        "primary_suggestion": suggestions[0] if suggestions else None,
    })







@app.route("/api/forward-flow/<session_id>", methods=["GET"])
def get_forward_flow(session_id: str):
    """
    Compute forward flow analysis and return visualization + metrics.
    """
    if session_id not in sessions:
        return jsonify({"error": "Invalid session"}), 400

    session = sessions[session_id]
    chain = session["chain"]


    # run forward flow analysis
    result = analyze_forward_flow(chain)
    
    # convert figure to base64 PNG
    buff = io.BytesIO()
    result["figure"].savefig(buff, format="png", dpi=100, bbox_inches="tight")
    buff.seek(0)
    img_base64 = base64.b64encode(buff.getvalue()).decode("utf-8")
    plt.close(result["figure"])
    



    
    # per-word summary
    summary = []
    for i, (word, flow) in enumerate(zip(chain, result["flow_values"])):
        summary.append({
            "index": i,
            "word": word,
            "forward_flow": round(flow, 4) if flow is not None else None,
            "is_seed": (i == 0),
        })
    
    return jsonify({
        "session_id": session_id,
        "forward_flow_values": [round(f, 4) if f is not None else None for f in result["flow_values"]],
        "overall_flow_score": round(result["overall_score"], 4) if result["overall_score"] is not None else None,
        "plot_image": f"data:image/png;base64,{img_base64}",
        "word_summary": summary,
        "chain_length": len(chain),
    })


# serve frontend route
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=True, host="0.0.0.0", port=port)
