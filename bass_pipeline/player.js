/* Clock-controlled playback of server-rendered, pitch-preserving PCM. */
class ReviewPlayer {
  constructor(context) {
    this.context = context;
    this.buffer = null;
    this.source = null;
    this.offset = 0;
    this.rate = 1;
    this.renderRate = 1;
    this.loop = false;
    this.paused = true;
    this.anchor = 0;
    this.generation = 0;
    this.onended = () => {};
  }
  async decode(bytes, renderRate = 1) {
    this.pause();
    this.offset = 0;
    this.buffer = await this.context.decodeAudioData(bytes);
    this.renderRate = renderRate;
    this.rate = renderRate;
  }
  get duration() { return (this.buffer?.duration || 0) * this.renderRate; }
  outputTime() {
    const stamp = this.context.getOutputTimestamp?.();
    if (stamp && stamp.contextTime > 0 && stamp.performanceTime > 0) {
      return Math.min(this.context.currentTime,
        stamp.contextTime + Math.max(0, performance.now() - stamp.performanceTime) / 1000);
    }
    // Explicit fallback estimate when device timestamps are unavailable.
    return Math.max(0, this.context.currentTime -
      (this.context.baseLatency || 0) - (this.context.outputLatency || 0));
  }
  get currentTime() {
    if (this.paused || !this.buffer) return this.offset;
    const position = this.offset + Math.max(0, this.outputTime() - this.anchor) * this.rate;
    if (this.loop) return position % this.duration;
    return Math.min(this.duration, position);
  }
  get playbackRate() { return this.rate; }
  set playbackRate(rate) {
    if (![0.5, 0.75, 1].includes(rate)) throw Error('Unsupported playback rate');
    const playing = !this.paused;
    this.pause(); this.rate = rate;
    if (playing) this.start();
  }
  set currentTime(value) {
    const playing = !this.paused;
    this.pause();
    this.offset = Math.max(0, Math.min(value, this.duration));
    if (playing) this.start();
  }
  start() {
    if (!this.buffer || !this.paused) return;
    if (this.offset >= this.duration) this.offset = 0;
    const source = this.context.createBufferSource();
    source.buffer = this.buffer;
    source.playbackRate.value = this.rate / this.renderRate;
    source.loop = this.loop;
    source.connect(this.context.destination);
    this.anchor = this.context.currentTime + 0.025;
    source.start(this.anchor, this.offset / this.renderRate);
    this.source = source;
    this.paused = false;
  }
  async play() {
    const generation = ++this.generation;
    await this.context.resume();
    if (generation === this.generation) this.start();
  }
  pause() {
    this.generation++;
    this.offset = this.currentTime;
    this.paused = true;
    if (this.source) {
      this.source.stop(); this.source.disconnect(); this.source = null;
    }
  }
  setLoop(value) {
    const playing = !this.paused;
    this.pause(); this.loop = value;
    if (playing) this.start();
  }
  tick() {
    if (!this.paused && !this.loop && this.currentTime >= this.duration) {
      this.pause(); this.onended();
    }
  }
}
if (typeof module !== 'undefined') module.exports = {ReviewPlayer};
