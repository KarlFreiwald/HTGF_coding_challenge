// One conversation per recording. The API key and provider SDK stay in Python.
export class Interview {
  constructor(conversationId, onReply, onStatus) {
    this.conversationId = conversationId;
    this.onReply = onReply;
    this.onStatus = onStatus;
    this.pending = [];
    this.seen = new Set();
    this.busy = false;
    this.cancelled = false;
    this.failed = false;
    this.controller = null;
  }

  addTurn(id) {
    if (this.cancelled || this.failed || this.seen.has(id)) return;
    this.seen.add(id);
    this.pending.push(id);
    void this.process();
  }

  async process() {
    if (this.busy || this.cancelled || this.failed || !this.pending.length) return;
    this.busy = true;
    this.controller = new AbortController();
    // Coalesce speech finalized while a reply was pending into the next request.
    const turnId = this.pending.at(-1);
    this.pending = [];
    this.onStatus("Preparing an interview reply…", "pending");
    const timer = setTimeout(() => this.controller?.abort(), 35000);
    try {
      const response = await fetch("/api/interview/reply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ conversation_id: this.conversationId, turn_id: turnId }),
        signal: this.controller.signal,
      });
      const data = await response.json();
      clearTimeout(timer);
      if (this.cancelled) return;
      if (!response.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "The conversation request was rejected. Start a new recording.");
      }
      if (data.superseded) return;
      if (typeof data.text !== "string" || !data.text.trim()) throw new Error("No interview reply was returned.");
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
