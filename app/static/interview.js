// One conversation per recording. The API key and provider SDK stay in Python.
export class Interview {
  constructor(settings, onReply, onStatus) {
    this.settings = { ...settings };
    this.onReply = onReply;
    this.onStatus = onStatus;
    this.history = [];
    this.pending = [];
    this.seen = new Set();
    this.busy = false;
    this.cancelled = false;
    this.failed = false;
    this.controller = null;
  }

  addTurn(id, text) {
    if (this.cancelled || this.failed || this.seen.has(id)) return;
    this.seen.add(id);
    this.pending.push(text);
    void this.process();
  }

  async process() {
    if (this.busy || this.cancelled || this.failed || !this.pending.length) return;
    this.busy = true;
    this.controller = new AbortController();
    // Coalesce speech finalized while a reply was pending into the next request.
    for (const text of this.pending.splice(0)) {
      this.history.push({ role: "user", content: text });
    }
    this.onStatus("Preparing an interview reply…", "pending");
    const timer = setTimeout(() => this.controller?.abort(), 35000);
    try {
      const response = await fetch("/api/interview/reply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...this.settings, messages: this.history }),
        signal: this.controller.signal,
      });
      const data = await response.json();
      clearTimeout(timer);
      if (this.cancelled) return;
      if (!response.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "The conversation request was rejected. Start a new recording.");
      }
      if (typeof data.text !== "string" || !data.text.trim()) throw new Error("No interview reply was returned.");
      this.history.push({ role: "assistant", content: data.text });
      // Keep turns serialized until the written reply has finished speaking.
      await this.onReply(data.text);
    } catch (error) {
      if (this.cancelled) return;
      this.failed = true;
      this.pending = [];
      const message = error.name === "AbortError" ? "The reply timed out." : error.message;
      this.onStatus(`${message} Transcription can continue; start a new recording to retry replies.`, "error");
    } finally {
      clearTimeout(timer);
      this.controller = null;
      this.busy = false;
      if (!this.cancelled && !this.failed) void this.process();
    }
  }

  cancel() {
    this.cancelled = true;
    this.pending = [];
    this.controller?.abort();
  }
}
