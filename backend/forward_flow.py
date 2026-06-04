import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from typing import Tuple, List, Optional
import gensim.downloader as api

# load the Word2Vec model (same as in app.py)
model = api.load("word2vec-google-news-300")


def normalise(word: str):
    """Normalize word for model lookup."""
    return word.strip().lower().replace(" ", "_")


def get_embeddings(words: List[str]) -> List[Optional[np.ndarray]]:
    """
    Convert words to embeddings using Word2Vec.
    """
    embeddings = []
    for word in words:
        normalized = normalise(word)
        if normalized in model.key_to_index:
            embeddings.append(model[normalized])
        else:
            embeddings.append(None)
    return embeddings


def compute_forward_flow(embeddings: List[Optional[np.ndarray]]) -> Tuple[List[float], float]:
    """
    Compute forward flow values for a sequence of embeddings.
    """
    forward_flow = [None]  #first word (seed) has no previous words
    
    for n in range(1, len(embeddings)):
        # skip if previous word not in vocab
        if embeddings is None:
            continue

        current_embedding = embeddings[n]
        

        
        # compute distances to all previous words
        distances = []
        for i in range(n):
            if embeddings[i] is None:
                continue
            prev_embedding = embeddings[i]
            

            
            # cosine similarity from embedings, then convert to distance
            similarity = float(np.dot(current_embedding, prev_embedding) / (np.linalg.norm(current_embedding) * np.linalg.norm(prev_embedding)))
            distance = 1 - similarity
            distances.append(distance)
        
        # average distance to all previous words
        if distances:
            flow_n = float(np.mean(distances))
            forward_flow.append(flow_n)
        else:
            forward_flow.append(None)
    
    # overall score: mean of all valid flow values (excluding first word and None values)
    valid_flows = []
    for f in forward_flow[1:]:
        if f is not None:
            valid_flows.append(f)
    if valid_flows:
        overall_score = float(np.mean(valid_flows))
    else:
        overall_score = None
    
    return forward_flow, overall_score


def smooth_curve(values: List[Optional[float]], window: int = 3) -> List[Optional[float]]:
    """
    Smooth values using rolling average.

    """
    smoothed = [None] * len(values)
    
    for i in range(len(values)):
        # get window around i (handling boundaries)
        start = max(0, i - window // 2)
        end = min(len(values), i + window // 2 + 1)
        
        #average only non-None values in window
        window_vals = []
        for j in range(start, end):
            if values[j] is not None:
                window_vals.append(values[j])
        
        if window_vals:
            smoothed[i] = float(np.mean(window_vals))
    
    return smoothed





def plot_forward_flow(
    words: List[str],
    flow_values: List[Optional[float]],
    overall_score: Optional[float] = None,
    smooth: bool = True,
    smooth_window: int = 3,
    figsize: Tuple[int, int] = (14, 7),
    save_path: Optional[str] = None,) -> plt.Figure:
    """
    Create a visualization of forward flow trajectory.
    
    """
    fig, ax = plt.subplots(figsize=figsize, dpi=100)
    
    #prepare data: only plot valid indices
    valid_indices = []
    y_vals_list = []
    for i, val in enumerate(flow_values):
        if val is not None:
            valid_indices.append(i)
            y_vals_list.append(val)
    y_vals = np.array(y_vals_list)

    
    if not valid_indices:
        ax.text(0.5, 0.5, "No valid flow data to plot", ha="center", va="center")
        ax.set_title("Forward Flow of Thought Sequence")
        return fig
    
    x_vals = np.array(valid_indices)

    #compute smoothed values if requested
    smoothed_vals = None
    if smooth:
        smoothed_full = smooth_curve(flow_values, window=smooth_window)
        smoothed_vals_list = []
        for i in valid_indices:
            smoothed_vals_list.append(smoothed_full[i])
        smoothed_vals = np.array(smoothed_vals_list)
    
    # color gradient: green (low) to blue (high)
    colors = []
    y_min, y_max = y_vals.min(), y_vals.max()
    y_range = y_max - y_min if y_max > y_min else 1.0
    



    for y in y_vals:
        normalized = (y - y_min) / y_range
        # gradient: green (0) -> cyan (0.5) -> blue (1)
        r = 0 * normalized
        g = 1 - 0.5 * normalized
        b = normalized
        colors.append((r, g, b))
    
    # plot smoothed curve first (background)
    if smoothed_vals is not None:
        ax.plot(x_vals, smoothed_vals, linewidth=2.5, alpha=0.6, 
                color="purple", label="Smoothed (rolling avg)", linestyle="--", zorder=2)
    
    # plot main line
    ax.plot(x_vals, y_vals, linewidth=2, color="darkblue", alpha=0.7, 
            label="Forward Flow", zorder=3)
    
    # plot dots with color gradient
    for i, (x, y, color) in enumerate(zip(x_vals, y_vals, colors)):
        ax.scatter(x, y, s=120, color=color, edgecolor="black", 
                  linewidth=1.5, zorder=4, alpha=0.9)
    





    
    # add word labels above points
    words_at_indices = []
    for i in valid_indices:
        words_at_indices.append(words[i])
    
    for x, y, word in zip(x_vals, y_vals, words_at_indices):
        ax.text(x, y + 0.015, word, ha="center", va="bottom", fontsize=9, 
               fontweight="bold", alpha=0.8)
    
    # draw horizontal line for overall average
    if overall_score is not None:
        ax.axhline(y=overall_score, color="red", linestyle="--", 
                  linewidth=2, alpha=0.6, label=f"Average Flow: {overall_score:.3f}", zorder=1)
    
    # styling
    ax.set_xlabel("Word Index", fontsize=12, fontweight="bold")
    ax.set_ylabel("Forward Flow (avg distance to previous words)", fontsize=12, fontweight="bold")
    ax.set_title("Forward Flow of Thought Sequence", fontsize=14, fontweight="bold", pad=20)
    
    ax.grid(True, alpha=0.3, linestyle=":", zorder=0)
    ax.legend(loc="best", fontsize=10, framealpha=0.9)
    
    # set x-axis ticks at each word
    ax.set_xticks(x_vals)
    ax.set_xticklabels([f"T{i}" for i in x_vals], fontsize=9)
    
    # add subtle background
    ax.set_facecolor("#f8f9fa")
    fig.patch.set_facecolor("white")
    
    plt.tight_layout()
    
    # save 
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    
    return fig






def analyze_forward_flow(words: List[str], save_path: Optional[str] = None):
    """
    Complete forward flow analysis pipeline.
    """


    # get embeddings
    embeddings = get_embeddings(words)
    
    # compute forward flow
    flow_values, overall_score = compute_forward_flow(embeddings)
    
    # create visualization
    fig = plot_forward_flow(words, flow_values, overall_score, save_path=save_path)
    
    valid_indices_list = []
    for i, f in enumerate(flow_values):
        if f is not None:
            valid_indices_list.append(i)
    
    return {
        "words": words,
        "flow_values": flow_values,
        "overall_score": overall_score,
        "figure": fig,
        "valid_indices": valid_indices_list,
    }

