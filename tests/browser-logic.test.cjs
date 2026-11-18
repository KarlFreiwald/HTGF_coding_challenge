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
  }
  const elements = new Map();
  const sockets = [];
  const microphones = [];
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
    Microphone, WebSocket: Socket, setTimeout, clearTimeout,
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
  const source = fs.readFileSync("app/static/app.js", "utf8").replace(/^import .*;\s*/, "");
  vm.runInContext(source, scope);
  return { scope, elements, sockets, microphones };
}

test("One button starts/stops; newest turns stay on top without duplicate partials", async () => {
  const ui = makeUI();
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
