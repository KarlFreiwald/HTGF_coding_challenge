// Runs on the audio rendering thread. Output stays silent: no microphone echo.
class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.chunkSamples = Math.round(sampleRate / 10); // 100 ms at the actual rate.
    this.buffer = new ArrayBuffer(this.chunkSamples * 2);
    this.view = new DataView(this.buffer);
    this.offset = 0;
    this.energy = 0;
    this.active = true;
    this.port.onmessage = ({ data }) => {
      if (data.type === "stop") {
        this.active = false;
        // Pad the final short chunk with silence instead of discarding speech.
        if (this.offset > 0) this.emitChunk();
        this.port.postMessage({ type: "flushed" });
      }
    };
  }

  emitChunk() {
    const level = Math.sqrt(this.energy / Math.max(1, this.offset));
    this.port.postMessage({ type: "audio", buffer: this.buffer, level }, [this.buffer]);
    this.buffer = new ArrayBuffer(this.chunkSamples * 2);
    this.view = new DataView(this.buffer);
    this.offset = 0;
    this.energy = 0;
  }

  process(inputs) {
    const channels = inputs[0];
    if (!this.active || !channels?.length) return true;
    for (let i = 0; i < channels[0].length; i++) {
      let sample = 0;
      for (const channel of channels) sample += channel[i];
      sample = Math.max(-1, Math.min(1, sample / channels.length));
      const pcm = Math.round(sample * (sample < 0 ? 32768 : 32767));
      this.view.setInt16(this.offset * 2, pcm, true);
      this.energy += sample * sample;
      this.offset++;
      if (this.offset === this.chunkSamples) this.emitChunk();
    }
    return true;
  }
}

registerProcessor("pcm-processor", PCMProcessor);
