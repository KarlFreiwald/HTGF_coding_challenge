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

async function read(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error("History request failed");
  return response.json();
}

async function showInterview() {
  const request = ++requestNumber;
  detail.hidden = true;
  status.textContent = "Loading transcript…";
  try {
    const { conversation, messages } = await read(`/api/history/${picker.value}`);
    if (request !== requestNumber) return;
    const end = conversation.ended_at ? ` · Ended ${date(conversation.ended_at)}` : "";
    settings.textContent = `Started ${date(conversation.started_at)}${end} · ${conversation.status} · ${language(conversation.language)} · ${conversation.tone} · ${conversation.model} (${conversation.provider})`;
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
