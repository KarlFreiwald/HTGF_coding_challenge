const picker = document.querySelector("#saved-interview");
const refresh = document.querySelector("#refresh-history");
const status = document.querySelector("#history-status");
const detail = document.querySelector("#saved-detail");
const settings = document.querySelector("#saved-settings");
const transcript = document.querySelector("#transcript");
const dates = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "medium" });
const date = (iso) => dates.format(new Date(iso));
const language = (code) => code === "de" ? "German" : "English";
let requestNumber = 0;
let summaryTimer;

const summaryFields = {
  startup_name: "Startup", sector: "Sector", team: "Team", product: "Product",
  development_stage: "Development stage", traction: "Traction", market: "Market",
  competition: "Competition", financing_needs: "Financing needs", planned_round: "Planned round",
  next_step: "Next step",
};

function addField(list, label, value) {
  const term = document.createElement("dt");
  const description = document.createElement("dd");
  term.textContent = label;
  description.textContent = value;
  list.append(term, description);
}

function renderSummary(summary) {
  document.querySelector("#interview-title").textContent = summary?.startup_name || "Interview details";
  document.querySelector("#summary-panel").hidden = !summary;
  if (!summary) return;
  document.querySelector("#summary-status").textContent = "";
  document.querySelector("#overview").textContent = summary.overview;
  const highlights = document.querySelector("#highlights");
  highlights.replaceChildren();
  for (const [label, values] of [
    ["Stage & traction", [summary.development_stage, summary.traction]],
    ["Financing", [summary.financing_needs, summary.planned_round]],
    ["Next step", [summary.next_step]],
  ]) {
    const text = values.filter(Boolean).join(" · ");
    if (text) addField(highlights, label, text);
  }
  const fields = document.querySelector("#summary-fields");
  fields.replaceChildren();
  for (const [key, label] of Object.entries(summaryFields)) {
    addField(fields, label, summary[key] || "Not discussed");
  }
}

// Stop finishes before summary generation. Briefly recheck recent interviews
// without clearing the transcript or moving a reader's scroll position.
function waitForSummary(conversation, request) {
  if (Date.now() - Date.parse(conversation.ended_at) >= 45000) return;
  summaryTimer = setTimeout(async () => {
    if (request !== requestNumber) return;
    try {
      const { summary } = await read(`/api/history/${conversation.id}`);
      if (request !== requestNumber) return;
      if (summary) renderSummary(summary);
      else waitForSummary(conversation, request);
    } catch {
      // Manual refresh remains available.
    }
  }, 4000);
}

async function read(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error("History request failed");
  return response.json();
}

async function showInterview() {
  clearTimeout(summaryTimer);
  const request = ++requestNumber;
  detail.hidden = true;
  status.textContent = "Loading transcript…";
  try {
    const { conversation, messages, summary } = await read(`/api/history/${picker.value}`);
    if (request !== requestNumber) return;
    const end = conversation.ended_at ? ` · Ended ${date(conversation.ended_at)}` : "";
    settings.textContent = `Started ${date(conversation.started_at)}${end} · ${conversation.status} · ${language(conversation.language)} · ${conversation.tone} · ${conversation.model} (${conversation.provider})`;
    document.querySelector("#summary-details").open = false;
    renderSummary(summary);
    const eligible = conversation.status === "ended" && messages.some(message => message.role === "user");
    if (!summary) {
      document.querySelector("#summary-status").textContent = eligible
        ? "No saved summary yet. Refresh history to check again."
        : "";
      if (eligible && conversation.ended_at) waitForSummary(conversation, request);
    }
    transcript.replaceChildren();
    for (const message of messages) {
      const item = document.createElement("li");
      item.dataset.speaker = message.role;
      const speaker = document.createElement("span");
      speaker.className = "turn-label";
      speaker.textContent = message.role === "user" ? "Founder" : "Interviewer";
      const text = document.createElement("p");
      text.textContent = message.content;
      item.append(speaker, text);
      transcript.append(item);
    }
    detail.hidden = false;
    status.textContent = messages.length ? "" : "This interview ended before any messages were saved.";
  } catch {
    if (request === requestNumber) status.textContent = "Could not load this transcript. Refresh history to try again.";
  }
}

async function loadHistory() {
  clearTimeout(summaryTimer);
  ++requestNumber;
  const selected = picker.value;
  refresh.disabled = true;
  picker.disabled = true;
  detail.hidden = true;
  status.textContent = "Loading interviews…";
  try {
    const rows = await read("/api/history");
    picker.replaceChildren();
    for (const row of rows) {
      const option = document.createElement("option");
      option.value = row.id;
      option.textContent = `${date(row.started_at)} · ${language(row.language)} · ${row.status}`;
      picker.append(option);
    }
    if (!rows.length) {
      status.textContent = "No past interviews yet.";
      return;
    }
    if (rows.some(row => row.id === selected)) picker.value = selected;
    picker.disabled = false;
    await showInterview();
  } catch {
    status.textContent = "Could not load past interviews. Refresh history to try again.";
  } finally {
    refresh.disabled = false;
  }
}

picker.addEventListener("change", showInterview);
refresh.addEventListener("click", loadHistory);
loadHistory();
