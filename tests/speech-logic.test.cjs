const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const tick = () => new Promise((resolve) => setImmediate(resolve));

function setup() {
  const calls = [], sources = [], statuses = [];
  const context = {
    state: "running", destination: {},
    decodeAudioData: async () => ({ duration: 0.01 }),
    createBufferSource() {
      const source = {
        connect() {}, disconnect() { this.disconnected = true; },
        start() { this.started = true; }, stop() { this.stopped = true; },
      };
      sources.push(source);
      return source;
    },
  };
  const scope = vm.createContext({
    AbortController, setTimeout, clearTimeout,
    fetch: (url, options) => new Promise((resolve, reject) => {
      calls.push({ url, options, resolve, reject });
      options.signal.addEventListener("abort", () => reject(Object.assign(new Error("Aborted"), { name: "AbortError" })));
    }),
  });
  vm.runInContext(fs.readFileSync("app/static/speech.js", "utf8").replace("export class", "class"), scope);
  const Speech = vm.runInContext("Speech", scope);
  const speech = new Speech(context, (text) => statuses.push(text));
  const respond = () => calls[0].resolve({ ok: true, arrayBuffer: async () => new ArrayBuffer(8) });
  return { speech, context, calls, sources, statuses, respond };
}

test("Speech mutes through synthesis, playback and echo tail, then releases the source", async () => {
  const ui = setup();
  const work = ui.speech.speak("Hello", "en");
  assert.equal(ui.speech.muted, true);
  assert.deepEqual(JSON.parse(ui.calls[0].options.body), { text: "Hello", language: "en" });
  ui.respond();
  await tick();
  assert.equal(ui.sources[0].started, true);
  ui.sources[0].onended();
  await tick();
  assert.equal(ui.speech.muted, true, "Speaker echo tail remains muted");
  await work;
  assert.equal(ui.speech.muted, false);
  assert.equal(ui.sources[0].disconnected, true);
});

test("Stop during fetch aborts without playing or reporting a failure", async () => {
  const ui = setup();
  const work = ui.speech.speak("Hallo", "de");
  ui.speech.cancel();
  await work;
  assert.equal(ui.calls[0].options.signal.aborted, true);
  assert.equal(ui.sources.length, 0);
  assert.equal(ui.speech.muted, false);
  await ui.speech.speak("Ignored", "en");
  assert.equal(ui.calls.length, 1);
});

test("Stop during decoding ignores late decoded audio", async () => {
  const ui = setup();
  let decode;
  ui.context.decodeAudioData = () => new Promise((resolve) => { decode = resolve; });
  const work = ui.speech.speak("Hello", "en");
  ui.respond();
  await tick();
  ui.speech.cancel();
  decode({ duration: 1 });
  await work;
  assert.equal(ui.sources.length, 0);
});

test("Stop during playback stops audio and resolves the waiting interview queue", async () => {
  const ui = setup();
  const work = ui.speech.speak("Hello", "en");
  ui.respond();
  await tick();
  ui.speech.cancel();
  await work;
  assert.equal(ui.sources[0].stopped, true);
  assert.equal(ui.sources[0].disconnected, true);
  assert.equal(ui.speech.muted, false);
});

test("Stop during echo tail cancels the wait", async () => {
  const ui = setup();
  const work = ui.speech.speak("Hello", "en");
  ui.respond();
  await tick();
  ui.sources[0].onended();
  await tick();
  ui.speech.cancel();
  await work;
  assert.equal(ui.speech.muted, false);
});

test("Provider rejection and suspended browser audio release the microphone gate", async () => {
  const ui = setup();
  const work = ui.speech.speak("Hello", "en");
  ui.calls[0].resolve({ ok: false, json: async () => ({ detail: "Check credits" }) });
  await assert.rejects(work, /Check credits/);
  assert.equal(ui.speech.muted, false);
  const suspended = setup();
  suspended.context.state = "suspended";
  const blocked = suspended.speech.speak("Hello", "en");
  suspended.respond();
  await assert.rejects(blocked, /paused by your browser/);
  assert.equal(suspended.speech.muted, false);
  assert.equal(suspended.sources.length, 0);
});
