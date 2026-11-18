import { Microphone } from "/static/microphone.js";

const statusText = document.querySelector("#connection-status");
const recordingButton = document.querySelector("#recording-toggle");
const language = document.querySelector("#language");
const meter = document.querySelector("#microphone-level");
const transcript = document.querySelector("#transcript");
const emptyTranscript = document.querySelector("#empty-transcript");
const turnAnnouncement = document.querySelector("#turn-announcement");
let current = null;

function setStatus(text, state = "pending") {
  statusText.textContent = text;
  statusText.dataset.state = state;
}

function finish(session, message, isError = false) {
  if (session.finished) return;
  session.finished = true;
  clearTimeout(session.timer);
  session.microphone.close();
  session.socket?.close();
  for (const turn of session.turns.values()) {
    if (!turn.final) turn.label.textContent = "Incomplete turn";
  }
  if (current !== session) return;
  current = null;
  meter.value = 0;
  recordingButton.textContent = "Start recording";
  recordingButton.disabled = false;
  language.disabled = false;
  setStatus(message, isError ? "error" : "ok");
}

function updateTranscript(session, event) {
  if (!Number.isInteger(event.turn_id) || typeof event.text !== "string") return;
  if (!event.text.trim()) return;
  let turn = session.turns.get(event.turn_id);
  if (!turn) {
    const item = document.createElement("li");
    const label = document.createElement("span");
    label.className = "turn-label";
    const text = document.createElement("p");
    item.append(label, text);
    transcript.prepend(item);
    turn = { item, label, text, final: false };
    session.turns.set(event.turn_id, turn);
    emptyTranscript.hidden = true;
  }
  // A turn has a stable ID. Replace updates instead of appending duplicates.
  if (turn.final && !event.final) return;
  turn.text.textContent = event.text;
  turn.final = event.final;
  turn.item.dataset.final = String(event.final);
  turn.label.textContent = `Turn ${event.turn_id + 1} · ${event.final ? "Complete" : "Listening"}`;
  if (event.final) turnAnnouncement.textContent = `Completed turn: ${event.text}`;
}

async function start() {
  if (current) return;
  const session = {
    microphone: new Microphone(), socket: null, timer: null,
    turns: new Map(), ready: false, stopping: false, finished: false,
  };
  current = session;
  recordingButton.textContent = "Stop recording";
  recordingButton.disabled = false;
  language.disabled = true;
  setStatus("Allow microphone access to begin.");

  try {
    const sampleRate = await session.microphone.open();
    if (session.finished) return;
    setStatus("Connecting to transcription…");
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${scheme}://${location.host}/ws/transcribe`);
    session.socket = socket;
    session.timer = setTimeout(() => finish(session, "Connection timed out. Please try again.", true), 25000);

    socket.onopen = () => {
      if (session.finished) { socket.close(); return; }
      socket.send(JSON.stringify({ type: "start", language: language.value, sample_rate: sampleRate }));
    };
    socket.onmessage = ({ data }) => {
      if (session.finished) return;
      try {
        const event = JSON.parse(data);
        if (event.type === "ready") {
          clearTimeout(session.timer);
          session.ready = true;
          transcript.replaceChildren();
          emptyTranscript.hidden = false;
          turnAnnouncement.textContent = "";
          session.microphone.start((buffer, level) => {
            if (session.finished || socket.readyState !== WebSocket.OPEN) return;
            if (socket.bufferedAmount > sampleRate * 2) {
              finish(session, "The connection cannot keep up with the microphone. Please restart.", true);
              return;
            }
            socket.send(buffer);
            meter.value = Math.min(1, level * 5);
          }, () => finish(session, "Microphone capture stopped unexpectedly. Please restart.", true));
          setStatus("Listening. Speak naturally; completed turns will appear below.", "ok");
        } else if (event.type === "transcript") {
          updateTranscript(session, event);
        } else if (event.type === "stopped") {
          finish(session, "Recording stopped. Your transcript remains below.");
        } else if (event.type === "error") {
          finish(session, event.message || "Transcription failed. Please try again.", true);
        }
      } catch {
        finish(session, "Could not process the transcription response. Please restart.", true);
      }
    };
    socket.onerror = () => finish(session, "Could not connect to the application. Check that it is running.", true);
    socket.onclose = () => {
      if (!session.finished) finish(session, "The connection closed unexpectedly. The last turn may be incomplete.", true);
    };
  } catch (error) {
    if (session.finished) return;
    const messages = {
      NotAllowedError: "Microphone access was denied. Allow it in your browser and try again.",
      NotFoundError: "No microphone was found. Connect one and try again.",
      NotReadableError: "The microphone could not be opened. Check whether another app is using it.",
    };
    finish(session, messages[error.name] || error.message || "Could not start the microphone.", true);
  }
}

async function stop() {
  const session = current;
  if (!session || session.stopping) return;
  session.stopping = true;
  recordingButton.textContent = "Stopping…";
  recordingButton.disabled = true;
  if (!session.ready) {
    finish(session, "Recording cancelled.");
    return;
  }
  setStatus("Finishing the last turn…");
  try {
    // Flush the AudioWorklet's last chunk before sending the stop command.
    await session.microphone.stop();
    meter.value = 0;
    if (session.finished) return;
    session.socket.send(JSON.stringify({ type: "stop" }));
    session.timer = setTimeout(() => {
      finish(session, "Final transcription timed out. The last turn may be incomplete.", true);
    }, 12000);
  } catch {
    finish(session, "Recording stopped, but the last turn may be incomplete.", true);
  }
}

recordingButton.addEventListener("click", () => current ? stop() : start());
window.addEventListener("pagehide", () => {
  if (current) finish(current, "Recording stopped.");
});
