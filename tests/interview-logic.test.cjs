const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const tick = () => new Promise((resolve) => setImmediate(resolve));

function makeInterview() {
  const calls = [], replies = [], statuses = [];
  const scope = vm.createContext({
    AbortController, setTimeout, clearTimeout,
    fetch: (url, options) => new Promise((resolve) => calls.push({
      url, body: JSON.parse(options.body), signal: options.signal,
      resolve: (data, ok = true) => resolve({ ok, json: async () => data }),
    })),
  });
  vm.runInContext(fs.readFileSync("app/static/interview.js", "utf8").replace("export class", "class"), scope);
  const Interview = vm.runInContext("Interview", scope);
  const settings = { model: "gpt-5.4", language: "de", tone: "professional" };
  const interview = new Interview(settings, (text) => replies.push(text), (...status) => statuses.push(status));
  return { interview, settings, calls, replies, statuses };
}

test("Final turns deduplicate, requests serialize, settings stay fixed and history includes replies", async () => {
  const ui = makeInterview();
  ui.interview.addTurn(0, "We build robots.");
  ui.interview.addTurn(0, "We build robots.");
  ui.settings.model = "different-model";
  ui.interview.addTurn(1, "Five engineers.");
  assert.equal(ui.calls.length, 1);
  ui.calls[0].resolve({ text: "Who is on the team?" });
  await tick();
  assert.equal(ui.calls.length, 2);
  assert.equal(ui.calls[1].body.model, "gpt-5.4");
  assert.deepEqual(ui.calls[1].body.messages, [
    { role: "user", content: "We build robots." },
    { role: "assistant", content: "Who is on the team?" },
    { role: "user", content: "Five engineers." },
  ]);
  ui.calls[1].resolve({ text: "How far along is the product?" });
  await tick();
  assert.equal(ui.replies.length, 2);
});

test("Restart cancellation aborts and ignores late replies", async () => {
  const ui = makeInterview();
  ui.interview.addTurn(0, "Hello");
  ui.interview.cancel();
  assert.equal(ui.calls[0].signal.aborted, true);
  ui.calls[0].resolve({ text: "Late reply" });
  await tick();
  ui.interview.addTurn(1, "Ignored");
  assert.equal(ui.replies.length, 0);
  assert.equal(ui.calls.length, 1);
});

test("API error stops paid retries and preserves the transcript history", async () => {
  const ui = makeInterview();
  ui.interview.addTurn(0, "Hello");
  ui.interview.addTurn(1, "More speech");
  ui.calls[0].resolve({ detail: "Add OPENAI_API_KEY" }, false);
  await tick();
  ui.interview.addTurn(2, "Still speaking");
  assert.equal(ui.calls.length, 1);
  assert.equal(ui.replies.length, 0);
  assert.equal(ui.interview.history[0].content, "Hello");
  assert.equal(ui.statuses.at(-1)[1], "error");
  assert.match(ui.statuses.at(-1)[0], /OPENAI_API_KEY/);
});
