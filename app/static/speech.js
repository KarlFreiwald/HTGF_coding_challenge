// Reuse the microphone's AudioContext, unlocked by the Start button gesture.
export class Speech {
  constructor(context, onStatus) {
    this.context = context;
    this.onStatus = onStatus;
    this.muted = false;
    this.cancelled = false;
    this.controller = null;
    this.source = null;
    this.release = null;
  }

  async speak(text, language) {
    if (this.cancelled) return;
    this.muted = true;
    this.controller = new AbortController();
    const timer = setTimeout(() => this.controller?.abort(), 35000);
    this.onStatus("Preparing voice · Mic paused", "synthesizing");
    try {
      const response = await fetch("/api/speech", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, language }),
        signal: this.controller.signal,
      });
      if (this.cancelled) return;
      if (!response.ok) {
        const data = await response.json();
        throw new Error(typeof data.detail === "string" ? data.detail : "Speech generation failed.");
      }
      const bytes = await response.arrayBuffer();
      if (this.cancelled) return;
      const audio = await this.context.decodeAudioData(bytes);
      if (this.cancelled) return;
      clearTimeout(timer);
      if (this.context.state !== "running") {
        throw new Error("Audio playback is paused by your browser. Stop and start recording to enable it again.");
      }
      if (!Number.isFinite(audio.duration) || audio.duration > 120) {
        throw new Error("The spoken reply is too long.");
      }
      this.source = this.context.createBufferSource();
      this.source.buffer = audio;
      this.source.connect(this.context.destination);
      this.onStatus("Interviewer speaking · Mic paused", "speaking");
      await new Promise((resolve, reject) => {
        // Also release if a browser suspends playback instead of firing onended.
        const playbackTimer = setTimeout(() => reject(new Error("Audio playback timed out.")), (audio.duration + 5) * 1000);
        this.release = () => { clearTimeout(playbackTimer); resolve(); };
        this.source.onended = this.release;
        this.source.start();
      });
      this.release = null;
      if (this.cancelled) return;
      // Cover the worklet's last 100 ms chunk and a short speaker echo tail.
      await new Promise((resolve) => {
        const tailTimer = setTimeout(resolve, 300);
        this.release = () => { clearTimeout(tailTimer); resolve(); };
      });
    } catch (error) {
      if (!this.cancelled) {
        throw new Error(error.name === "AbortError" ? "Speech generation timed out." : error.message);
      }
    } finally {
      clearTimeout(timer);
      this.release?.();
      this.release = null;
      this.disposeSource();
      this.controller = null;
      this.muted = false;
    }
  }

  disposeSource() {
    if (!this.source) return;
    this.source.onended = null;
    try { this.source.stop(); } catch { /* Already stopped or never started. */ }
    this.source.disconnect();
    this.source = null;
  }

  cancel() {
    this.cancelled = true;
    this.controller?.abort();
    this.release?.();
    this.disposeSource();
    this.muted = false;
  }
}
