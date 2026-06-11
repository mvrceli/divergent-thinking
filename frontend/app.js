// base url for all api calls — empty string means same origin as the served page
const API = "";

const SURVEY_AI      = "https://vuamsterdam.eu.qualtrics.com/jfe/form/SV_25bUDTiA7tubP94";
const SURVEY_CONTROL = "https://vuamsterdam.eu.qualtrics.com/jfe/form/SV_3VgX8DeNOKTC94a";

// global session state
let sessionId = null;
let sessionMode = null;
let currentPrompt = null;
let initialStimulus = null;
let turn = 0;
let chainWords = [];
let interventionStart = 7;
let interventionEnd = 13;
let currentSuggestion = null;
let isWaiting = false;

// screen references — only one is visible at a time via the "active" class
const screenConsent = document.getElementById("screen-consent");
const screenStart = document.getElementById("screen-start");
const screenGame = document.getElementById("screen-game");
const screenResults = document.getElementById("screen-results");

// consent screen elements
const consentCheckbox = document.getElementById("consent-checkbox");
const btnConsentContinue = document.getElementById("btn-consent-continue");

consentCheckbox.addEventListener("change", () => {
  btnConsentContinue.disabled = !consentCheckbox.checked;
});

btnConsentContinue.addEventListener("click", () => showScreen(screenStart));

// button references
const btnStartGame = document.getElementById("btn-start-game");
const btnSubmit = document.getElementById("btn-submit");
const btnRestart = document.getElementById("btn-restart");

// in-game display elements
const stimulusWord = document.getElementById("stimulus-word");
const turnDisplay = document.getElementById("turn-display");
const wordInput = document.getElementById("word-input");
const inputError = document.getElementById("input-error");
const resultSummary = document.getElementById("result-summary");
const resultDetails = document.getElementById("result-details");
const forwardFlowPlot = document.getElementById("forward-flow-plot");
const chainTrail = document.getElementById("chain-trail");
const chainWordsEl = document.getElementById("chain-words");
const suggestionBox = document.getElementById("suggestion-box");
const suggestionDisplay = document.getElementById("suggestion-display");
const previousWordDisplay = document.getElementById("previous-word-display");

// show a screen and hide all others by toggling the "active" class
function showScreen(screen) {
  document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
  screen.classList.add("active");
}



// fetch helpers — thin wrappers around fetch to avoid repeating headers and json parsing
async function apiPost(path, body) {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

async function apiGet(path) {
  const res = await fetch(`${API}${path}`);
  return res.json();
}

// map a divergence score to a css class for colour coding
function divClass(val) {
  if (val == null) return "";
  if (val >= 0.75) return "div-high";
  if (val >= 0.5) return "div-med";
  return "div-low";
}

// format a numeric score to 4 decimal places, or "N/A" if missing
function formatScore(val) {
  return val != null ? val.toFixed(4) : "N/A";
}



// rebuild the breadcrumb chain trail from the current chainWords array
function renderChain() {
  chainWordsEl.innerHTML = chainWords
    .map((w, i) => {
      const cls = i === 0 ? "chain-chip chain-chip-start" : "chain-chip";
      return `<span class="${cls}">${escapeHtml(w)}</span>`;
    })
    .join('<span class="chain-arrow">→</span>');
  chainTrail.classList.remove("hidden");
}




// start the game — mode is assigned server-side
async function startGame() {
  btnStartGame.disabled = true;

  const data = await apiPost("/api/start", {});
  sessionId = data.session_id;
  sessionMode = data.mode;
  currentPrompt = data.current_prompt;
  initialStimulus = data.stimulus;
  interventionStart = data.intervention_start || 7;
  interventionEnd = data.intervention_end || 13;
  turn = 0;
  chainWords = [currentPrompt];
  currentSuggestion = null;

  stimulusWord.textContent = currentPrompt;
  turnDisplay.textContent = "0";
  suggestionBox.classList.add("hidden");
  inputError.textContent = "";
  chainTrail.classList.add("hidden");

  showScreen(screenGame);
  wordInput.focus();
  btnStartGame.disabled = false;
}

btnStartGame.addEventListener("click", () => startGame());




// submit the current word input to the server and update the ui for the next turn
async function submitWord() {
  if (isWaiting) return;
  const word = wordInput.value.trim();
  if (!word) { inputError.textContent = "Please enter a word."; return; }
  inputError.textContent = "";
  isWaiting = true;
  btnSubmit.disabled = true;
  wordInput.disabled = true;

  const data = await apiPost("/api/respond", { session_id: sessionId, word });

  if (data.error) {
    inputError.textContent = data.error;
    wordInput.disabled = false;
    btnSubmit.disabled = false;
    isWaiting = false;
    return;
  }

  // surface rejection reason and let the user retype without advancing the turn
  if (data.rejected) {
    inputError.textContent = data.reason;
    wordInput.disabled = false;
    wordInput.select();
    btnSubmit.disabled = false;
    isWaiting = false;
    return;
  }

  turn = data.turn;
  turnDisplay.textContent = turn;
  const r = data.result;

  // update chain
  chainWords.push(r.word);
  renderChain();

  // show/hide suggestion box based on intervention phase
  const nextTurn = turn + 1;
  if (nextTurn >= interventionStart && nextTurn <= interventionEnd && data.suggestion) {
    currentSuggestion = data.suggestion;
    suggestionDisplay.textContent = currentSuggestion;
    previousWordDisplay.textContent = r.word;
    suggestionBox.classList.remove("hidden");
  } else {
    suggestionBox.classList.add("hidden");
    currentSuggestion = null;
  }

  wordInput.value = "";
  wordInput.disabled = false;
  btnSubmit.disabled = false;
  isWaiting = false;

  if (data.done) {
    showResults();
  } else {
    // update the prompt word for next turn
    currentPrompt = data.next_prompt;
    stimulusWord.textContent = currentPrompt;
    wordInput.focus();
  }
}

// wire up submit button and enter key to submitWord
btnSubmit.addEventListener("click", submitWord);
wordInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") submitWord();
});




// fetch the forward flow chart from the server and inject it as an inline image
async function fetchAndDisplayForwardFlow(sessionId) {

  const data = await apiGet(`/api/forward-flow/${sessionId}`);

  // TODO: check error if malformed ff data

  if (forwardFlowPlot && data.plot_image) {
    const img = document.createElement("img");
    img.src = data.plot_image;
    img.style.width = "100%";
    img.style.height = "auto";
    img.style.borderRadius = "8px";
    forwardFlowPlot.innerHTML = "";
    forwardFlowPlot.appendChild(img);

    const summary = document.createElement("div");
    summary.style.marginTop = "1rem";
    summary.style.padding = "0.75rem";
    summary.style.backgroundColor = "rgba(99, 102, 241, 0.05)";
    summary.style.borderRadius = "6px";
    summary.style.fontSize = "0.9rem";

    const scoreDiv = document.createElement("div");
    scoreDiv.style.marginBottom = "0.5rem";
    const scoreLabel = document.createElement("strong");
    scoreLabel.textContent = "Overall Flow Score: ";
    const scoreVal = document.createElement("span");
    scoreVal.style.color = "var(--highlight)";
    scoreVal.textContent = formatScore(data.overall_flow_score);
    scoreDiv.appendChild(scoreLabel);
    scoreDiv.appendChild(scoreVal);

    const explainDiv = document.createElement("div");
    explainDiv.style.fontSize = "0.8rem";
    explainDiv.style.color = "var(--text-muted)";
    explainDiv.textContent = "This measures how much your word choices diverge from your previous associations. Higher scores indicate greater semantic diversity.";

    summary.appendChild(scoreDiv);
    summary.appendChild(explainDiv);
    forwardFlowPlot.appendChild(summary);
    }
  }




// fetch the session summary and build the full results screen
async function showResults() {
  const data = await apiGet(`/api/summary/${sessionId}`);

  // render chain as a visual path
  const chainHtml = data.chain
    .map(w => `<span class="chain-chip">${escapeHtml(w)}</span>`)
    .join('<span class="chain-arrow">→</span>');

  // show intervention section if data
  const intSection = document.getElementById("intervention-section");
  if (data.avg_divergence_before_intervention || data.avg_divergence_during_intervention || data.avg_divergence_after_intervention) {
    intSection.style.display = "block";
    document.getElementById("int-before").textContent = formatScore(data.avg_divergence_before_intervention);
    document.getElementById("int-before").className = "int-score " + divClass(data.avg_divergence_before_intervention);
    document.getElementById("int-during").textContent = formatScore(data.avg_divergence_during_intervention);
    document.getElementById("int-during").className = "int-score " + divClass(data.avg_divergence_during_intervention);
    document.getElementById("int-after").textContent = formatScore(data.avg_divergence_after_intervention);
    document.getElementById("int-after").className = "int-score " + divClass(data.avg_divergence_after_intervention);
  }

  // build the big average divergence score display
  const label = document.createElement("span");
  label.className = "big-label";
  label.textContent = "Average Divergence Score";

  const score = document.createElement("span");
  score.className = "big-score " + divClass(data.avg_divergence);
  score.textContent = formatScore(data.avg_divergence);

  const stimulusP = document.createElement("p");
  stimulusP.style.marginTop = "0.5rem";
  stimulusP.style.color = "var(--text-muted)";
  stimulusP.innerHTML = "Starting word: <strong>" + escapeHtml(data.initial_stimulus) + "</strong>";

  const chainDiv = document.createElement("div");
  chainDiv.className = "chain-summary";
  chainDiv.innerHTML = chainHtml;

  resultSummary.innerHTML = "";
  resultSummary.appendChild(label);
  resultSummary.appendChild(score);
  resultSummary.appendChild(stimulusP);
  resultSummary.appendChild(chainDiv);

  // build the per-turn results table
  const table = document.createElement("table");
  table.className = "result-table";

  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  const headers = ["#", "Prompt", "Response", "Similarity", "Div. from Prompt", "Div. from All"];
  headers.forEach(h => {
    const th = document.createElement("th");
    th.textContent = h;
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  data.responses.forEach((r, i) => {
    const turnNum = i + 1;
    const isIntervention = turnNum >= data.intervention_start && turnNum <= data.intervention_end;
    const row = document.createElement("tr");
    if (isIntervention) {
      row.style.background = "rgba(245, 158, 11, 0.03)";
    }

    const cells = [
      turnNum + (isIntervention ? " *" : ""),
      escapeHtml(r.prompt_word),
      escapeHtml(r.word),
      formatScore(r.similarity_to_prompt),
      formatScore(r.divergence_from_prompt),
      formatScore(r.divergence_from_previous)
    ];

    cells.forEach((cell, idx) => {
      const td = document.createElement("td");
      if (idx === 4 || idx === 5) {
        td.className = divClass(idx === 4 ? r.divergence_from_prompt : r.divergence_from_previous);
      }
      td.textContent = cell;
      row.appendChild(td);
    });
    tbody.appendChild(row);
  });
  table.appendChild(tbody);

  resultDetails.innerHTML = "";
  resultDetails.appendChild(table);

  const note = document.createElement("p");
  note.style.fontSize = "0.8rem";
  note.style.color = "var(--text-muted)";
  note.style.marginTop = "0.5rem";
  note.textContent = "* Indicates responses during the intervention phase (turns with Suggestions)";
  resultDetails.appendChild(note);

  document.getElementById("survey-link").href = sessionMode === "ai" ? SURVEY_AI : SURVEY_CONTROL;

  showScreen(screenResults);

  //fetch and display forward flow graph
  fetchAndDisplayForwardFlow(sessionId);
}

// restart — reset all state and return to the start screen
btnRestart.addEventListener("click", () => {
  sessionId = null;
  currentPrompt = null;
  initialStimulus = null;
  turn = 0;
  chainWords = [];
  if (forwardFlowPlot) {
    forwardFlowPlot.innerHTML = "";
  }
  showScreen(screenStart);
});



// escape user-typed strings before inserting into innerhtml to prevent xss
function escapeHtml(str) {
  const div = document.createElement("div");
  div.appendChild(document.createTextNode(str));
  return div.innerHTML;
}
