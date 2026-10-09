/* Local microphone capture. Mean downsampling to 16kHz; no recordings/files. */
class PcmCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.frame = new Int16Array(320);
    this.offset = this.clock = this.sum = this.count = 0;
  }
  process(inputs) {
    const input = inputs[0]?.[0];
    if (!input) return true;
    for (const sample of input) {
      this.sum += sample; this.count++; this.clock += 16000;
      if (this.clock >= sampleRate) {
        this.clock -= sampleRate;
        const value = Math.max(-1, Math.min(1, this.sum / this.count));
        this.sum = this.count = 0;
        this.frame[this.offset++] = Math.round(value * (value < 0 ? 32768 : 32767));
        if (this.offset === 320) {
          // Write little-endian explicitly, independent of the browser platform.
          const bytes = new ArrayBuffer(640);
          const view = new DataView(bytes);
          for (let i = 0; i < 320; i++) view.setInt16(i * 2, this.frame[i], true);
          this.port.postMessage(bytes, [bytes]); this.offset = 0;
        }
      }
    }
    return true;
  }
}
registerProcessor('pcm-capture', PcmCapture);
