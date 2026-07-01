const API = "";

const SURVEY_AI = "https://www.google.com";
const SURVEY_CONTROL = "https://www.google.com";

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
let consentTimestamp = null;

// screen references, only one is visible at a time via the "active" class
const screenConsent = document.getElementById("screen-consent");
const screenStart = document.getElementById("screen-start");
const screenGame = document.getElementById("screen-game");
const screenResults = document.getElementById("screen-results");

const consentCheckbox = document.getElementById("consent-checkbox");
const btnConsentContinue = document.getElementById("btn-consent-continue");

consentCheckbox.addEventListener("change", () => {
  btnConsentContinue.disabled = !consentCheckbox.checked;
});

btnConsentContinue.addEventListener("click", () => {
  consentTimestamp = new Date().toISOString();
  showScreen(screenStart);
});

// button references
const btnStartGame = document.getElementById("btn-start-game");
const btnSubmit = document.getElementById("btn-submit");

// in-game display elements
const stimulusWord = document.getElementById("stimulus-word");
const turnDisplay = document.getElementById("turn-display");
const wordInput = document.getElementById("word-input");
const inputError = document.getElementById("input-error");
const chainTrail = document.getElementById("chain-trail");
const chainWordsEl = document.getElementById("chain-words");
const suggestionBox = document.getElementById("suggestion-box");
const suggestionDisplay = document.getElementById("suggestion-display");
const previousWordDisplay = document.getElementById("previous-word-display");

// show a screen and hide all others by toggling the "active" class
function showScreen(screen) {
  const screens = document.querySelectorAll(".screen");
  for (const s of screens) {
    s.classList.remove("active");
  }
  screen.classList.add("active");
}



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

// rebuild the breadcrumb chain trail from the current chainWords array
function renderChain() {
  const chips = [];
  for (let i = 0; i < chainWords.length; i++) {
    const cls = i === 0 ? "chain-chip chain-chip-start" : "chain-chip";
    chips.push(`<span class="${cls}">${escapeHtml(chainWords[i])}</span>`);
  }
  chainWordsEl.innerHTML = chips.join('<span class="chain-arrow">→</span>');
  chainTrail.classList.remove("hidden");
}




// start the game — mode is assigned server-side
async function startGame() {
  btnStartGame.disabled = true;

  const data = await apiPost("/api/start", { consent_accepted: true, consent_timestamp: consentTimestamp });
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

// submit button and enter key to submitWord
btnSubmit.addEventListener("click", submitWord);
wordInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") submitWord();
});







// show the end screen, log session_complete, and set the survey link
async function showResults() {
  await apiGet(`/api/summary/${sessionId}`);
  const surveyBase = sessionMode === "ai" ? SURVEY_AI : SURVEY_CONTROL;
  document.getElementById("survey-link").href = `${surveyBase}?game_session_id=${encodeURIComponent(sessionId)}`;
  showScreen(screenResults);
}




// escape user-typed strings before inserting into innerhtml to prevent xss
function escapeHtml(str) {
  const div = document.createElement("div");
  div.appendChild(document.createTextNode(str));
  return div.innerHTML;
}
