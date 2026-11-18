export class Microphone {
  constructor() {
    this.closed = false;
    this.context = null;
    this.stream = null;
    this.source = null;
    this.processor = null;
    this.onFlushed = null;
  }

  async open() {
    if (!navigator.mediaDevices?.getUserMedia || !window.AudioContext) {
      throw new Error("Microphone capture requires a supported browser on localhost or HTTPS.");
    }
    this.context = new AudioContext();
    await this.context.resume();
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
    // Stop can be clicked while the permission prompt is still open.
    if (this.closed) {
      stream.getTracks().forEach((track) => track.stop());
      throw new Error("Recording cancelled.");
    }
    this.stream = stream;
    await this.context.audioWorklet.addModule("/static/pcm-worklet.js");
    if (this.closed) throw new Error("Recording cancelled.");
    return this.context.sampleRate;
  }

  start(onAudio, onEnded) {
    if (this.closed) return;
    this.source = this.context.createMediaStreamSource(this.stream);
    this.processor = new AudioWorkletNode(this.context, "pcm-processor", {
      numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1],
    });
    this.processor.port.onmessage = ({ data }) => {
      if (data.type === "audio") onAudio(data.buffer, data.level);
      if (data.type === "flushed") this.onFlushed?.();
    };
    this.processor.onprocessorerror = onEnded;
    this.stream.getAudioTracks().forEach((track) => { track.onended = onEnded; });
    this.source.connect(this.processor);
    this.processor.connect(this.context.destination);
  }

  async stop() {
    if (this.closed) return;
    try {
      if (this.processor) {
        await new Promise((resolve, reject) => {
          const timer = setTimeout(() => reject(new Error("Could not finish microphone capture.")), 1000);
          this.onFlushed = () => { clearTimeout(timer); resolve(); };
          this.processor.port.postMessage({ type: "stop" });
        });
      }
    } finally {
      this.close();
    }
  }

  close() {
    if (this.closed) return;
    this.closed = true;
    this.stream?.getTracks().forEach((track) => {
      track.onended = null;
      track.stop();
    });
    this.source?.disconnect();
    if (this.processor) {
      this.processor.onprocessorerror = null;
      this.processor.port.onmessage = null;
      this.processor.disconnect();
    }
    if (this.context && this.context.state !== "closed") this.context.close().catch(() => {});
  }
}
