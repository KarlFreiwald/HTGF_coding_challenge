// Tests audio conversion and UI lifecycle without a real microphone or API call.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

for (const rate of [16000, 44100, 48000]) {
  test(`PCM captures ${rate} Hz, clips, downmixes, and flushes in order`, () => {
    const events = [];
    let Processor;
    const scope = vm.createContext({
      sampleRate: rate,
      AudioWorkletProcessor: class {
        constructor() { this.port = { postMessage: (data) => events.push(data) }; }
      },
      registerProcessor: (_, klass) => { Processor = klass; },
    });
    vm.runInContext(fs.readFileSync("app/static/pcm-worklet.js", "utf8"), scope);
    const processor = new Processor();
    const count = rate / 10;
    processor.process([[Float32Array.from({ length: count }, (_, i) => i % 2 ? -2 : 2)]]);
    assert.equal(events[0].buffer.byteLength, count * 2);
    const pcm = new DataView(events[0].buffer);
    assert.equal(pcm.getInt16(0, true), 32767);
    assert.equal(pcm.getInt16(2, true), -32768);
    processor.process([[new Float32Array([1, 1]), new Float32Array([-1, 0])]]);
    processor.port.onmessage({ data: { type: "stop" } });
    const tail = new DataView(events[1].buffer);
    assert.equal(tail.getInt16(0, true), 0);
    assert.equal(tail.getInt16(2, true), 16384);
    assert.equal(tail.getInt16(4, true), 0);
    assert.equal(events[2].type, "flushed");
    processor.process([[new Float32Array(count).fill(1)]]);
    assert.equal(events.length, 3, "No audio after Stop");
  });
}

function makeUI() {
  class Element {
    constructor() { this.children = []; this.dataset = {}; this.value = "de"; this.textContent = ""; }
    addEventListener(type, fn) { this[type] = fn; }
    append(...children) { this.children.push(...children); }
    prepend(...children) { this.children.unshift(...children); }
    replaceChildren() { this.children = []; }
    get selectedOptions() { return this.children.filter((child) => child.value === this.value); }
  }
  const elements = new Map();
  const sockets = [];
  const microphones = [];
  const interviews = [];
  const speeches = [];
  class Speech {
    constructor() { this.muted = false; speeches.push(this); }
    async speak(text, language) { this.text = text; this.language = language; }
    cancel() { this.cancelled = true; this.muted = false; }
  }
  class Interview {
    constructor(settings, onReply) { this.settings = settings; this.onReply = onReply; this.turns = []; interviews.push(this); }
    addTurn(id, text) { this.turns.push({ id, text }); }
    cancel() { this.cancelled = true; }
  }
  class Microphone {
    constructor() { this.closed = false; microphones.push(this); }
    async open() { return 48000; }
    start(onAudio) { this.onAudio = onAudio; }
    async stop() { this.onAudio(new ArrayBuffer(9600), 0.1); this.close(); }
    close() { this.closed = true; }
  }
  class Socket {
    static OPEN = 1;
    constructor() { this.readyState = 1; this.bufferedAmount = 0; this.sent = []; sockets.push(this); }
    send(frame) { this.sent.push(frame); }
    close() { this.readyState = 3; }
    emit(event) { this.onmessage({ data: JSON.stringify(event) }); }
  }
  const scope = vm.createContext({
    Microphone, Interview, Speech, WebSocket: Socket, setTimeout, clearTimeout,
    fetch: async () => ({ ok: true, json: async () => ({ default: "gpt-5.4-mini", models: [{ id: "gpt-5.4-mini", label: "GPT-5.4 mini", provider: "openai" }] }) }),
    location: { protocol: "http:", host: "localhost:8000" },
    window: { addEventListener() {} },
    document: {
      querySelector(id) {
        if (!elements.has(id)) elements.set(id, new Element());
        return elements.get(id);
      },
      createElement: () => new Element(),
    },
  });
  const source = fs.readFileSync("app/static/app.js", "utf8").replace(/^import .*;\s*/gm, "");
  vm.runInContext(source, scope);
  elements.get("#tone").value = "professional";
  return { scope, elements, sockets, microphones, interviews, speeches, ready: vm.runInContext("modelLoading", scope) };
}

test("One button starts/stops; newest turns stay on top without duplicate partials", async () => {
  const ui = makeUI();
  await ui.ready;
  const button = ui.elements.get("#recording-toggle");
  await button.click();
  assert.equal(button.textContent, "Stop recording");
  assert.equal(button.disabled, false);
  const socket = ui.sockets[0];
  socket.onopen();
  socket.emit({ type: "ready" });
  socket.emit({ type: "transcript", turn_id: 0, text: "We", final: false });
  socket.emit({ type: "transcript", turn_id: 0, text: "We build", final: false });
  const list = ui.elements.get("#transcript");
  assert.equal(list.children.length, 1);
  socket.emit({ type: "transcript", turn_id: 1, text: "Our team has five people.", final: true });
  assert.equal(list.children.length, 2);
  assert.equal(list.children[0].children[1].textContent, "Our team has five people.");
  await button.click();
  assert.equal(button.textContent, "Stopping…");
  assert.equal(button.disabled, true);
  assert.equal(socket.sent.at(-2).byteLength, 9600);
  assert.equal(JSON.parse(socket.sent.at(-1)).type, "stop");
  assert.equal(ui.microphones[0].closed, true);
  socket.emit({ type: "transcript", turn_id: 0, text: "We build robots.", final: true });
  socket.emit({ type: "stopped" });
  assert.equal(list.children.length, 2);
  assert.equal(list.children[0].children[1].textContent, "Our team has five people.");
  assert.equal(list.children[1].children[1].textContent, "We build robots.");
  assert.equal(button.textContent, "Start recording");
  assert.equal(button.disabled, false);
  // Restart creates a fresh session and clears previous turns only when ready.
  await button.click();
  ui.sockets[1].onopen();
  ui.sockets[1].emit({ type: "ready" });
  assert.equal(list.children.length, 0);
  ui.sockets[1].emit({ type: "error", message: "Test end" });
});

test("Cancellation during permission setup cannot open a stale socket", async () => {
  const ui = makeUI();
  await ui.ready;
  const button = ui.elements.get("#recording-toggle");
  const starting = button.click();
  await button.click();
  await starting;
  assert.equal(ui.sockets.length, 0);
  assert.equal(ui.microphones[0].closed, true);
  assert.equal(ui.elements.get("#language").disabled, false);
  assert.equal(button.textContent, "Start recording");
  assert.equal(button.disabled, false);
});

test("Unexpected disconnect releases microphone and marks unfinished text", async () => {
  const ui = makeUI();
  await ui.ready;
  await ui.scope.start();
  const socket = ui.sockets[0];
  socket.onopen();
  socket.emit({ type: "ready" });
  socket.emit({ type: "transcript", turn_id: 0, text: "<script>literal text</script>", final: false });
  socket.onclose();
  assert.equal(ui.microphones[0].closed, true);
  assert.equal(ui.elements.get("#connection-status").dataset.state, "error");
  assert.equal(ui.elements.get("#transcript").children[0].children[0].textContent, "Incomplete turn");
  assert.equal(ui.elements.get("#recording-toggle").disabled, false);
  assert.equal(ui.elements.get("#recording-toggle").textContent, "Start recording");
});

test("Final turns trigger speech; muted audio becomes silence; Stop cancels replies and restart is clean", async () => {
  const ui = makeUI();
  await ui.ready;
  await ui.scope.start();
  const socket = ui.sockets[0];
  socket.onopen();
  socket.emit({ type: "ready" });
  const interview = ui.interviews[0];
  assert.equal(interview.settings.model, "gpt-5.4-mini");
  assert.equal(interview.settings.tone, "professional");
  assert.equal(ui.elements.get("#model").disabled, true);
  socket.emit({ type: "transcript", turn_id: 0, text: "We build", final: false });
  assert.equal(interview.turns.length, 0);
  socket.emit({ type: "transcript", turn_id: 0, text: "We build robots.", final: true });
  await interview.onReply("<b>Who is on your team?</b>");
  const list = ui.elements.get("#transcript");
  assert.equal(list.children[0].dataset.speaker, "assistant");
  assert.equal(list.children[0].children[1].textContent, "<b>Who is on your team?</b>");
  assert.equal(ui.speeches[0].text, "<b>Who is on your team?</b>");
  assert.equal(ui.speeches[0].language, "de");
  ui.speeches[0].muted = true;
  const audio = new Uint8Array(9600).fill(42);
  ui.microphones[0].onAudio(audio.buffer, 0.5);
  assert.equal(audio.every((value) => value === 0), true);
  assert.equal(ui.elements.get("#microphone-level").value, 0);
  ui.speeches[0].muted = false;
  const unmuted = new Uint8Array(9600).fill(42);
  ui.microphones[0].onAudio(unmuted.buffer, 0.5);
  assert.equal(unmuted[0], 42);
  await ui.scope.stop();
  socket.emit({ type: "transcript", turn_id: 1, text: "Final words.", final: true });
  socket.emit({ type: "stopped" });
  assert.equal(interview.turns.length, 1);
  assert.equal(interview.cancelled, true);
  assert.equal(ui.speeches[0].cancelled, true);
  await interview.onReply("Late reply");
  assert.equal(list.children.length, 3);
  assert.equal(list.children[0].children[1].textContent, "Final words.");
  await ui.scope.start();
  ui.sockets[1].onopen();
  ui.sockets[1].emit({ type: "ready" });
  assert.equal(interview.cancelled, true);
  assert.equal(list.children.length, 0);
  ui.sockets[1].emit({ type: "stopped" });
});

test("Speech failure retains the written reply and returns to listening", async () => {
  const ui = makeUI();
  await ui.ready;
  await ui.scope.start();
  ui.sockets[0].onopen();
  ui.sockets[0].emit({ type: "ready" });
  ui.speeches[0].speak = async () => { throw new Error("Speech unavailable"); };
  await ui.interviews[0].onReply("Who is on your team?");
  assert.equal(ui.elements.get("#transcript").children[0].children[1].textContent, "Who is on your team?");
  assert.equal(ui.elements.get("#reply-status").dataset.state, "error");
  assert.match(ui.elements.get("#connection-status").textContent, /Listening/);
  ui.sockets[0].emit({ type: "stopped" });
});
