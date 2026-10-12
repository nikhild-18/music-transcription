const {test} = require('node:test');
const assert = require('node:assert/strict');
const {ReviewPlayer} = require('../bass_pipeline/player.js');

function setup() {
  const ctx = {currentTime:10, baseLatency:0.01, outputLatency:0.04,
    destination:{}, resume:async()=>{},
    createBufferSource() { return {playbackRate:{value:1},connect(){},disconnect(){},stop(){},
      start(time,offset) {this.started=[time,offset];}}; },
  };
  const p = new ReviewPlayer(ctx);p.buffer={duration:10};return {p,ctx};
}
const close=(a,b)=>assert.ok(Math.abs(a-b)<1e-6, `${a} versus ${b}`);
test('cursor uses output clock, scheduled start and source-time speed exactly once', async()=>{
  const {p,ctx}=setup();p.currentTime=3;p.playbackRate=0.5;await p.play();
  assert.deepEqual(p.source.started,[10.025,3]);
  close(p.currentTime,3); // scheduled audio has not reached device yet
  ctx.currentTime=12.075;close(p.currentTime,4);
  p.pause();ctx.currentTime=30;close(p.currentTime,4);
  await p.play();ctx.currentTime=32.075;close(p.currentTime,5);
});
test('seeking, speed changes, looping and end stay in clip-local seconds',async()=>{
  const {p,ctx}=setup();await p.play();ctx.currentTime=11.075;close(p.currentTime,1);
  p.currentTime=6;close(p.currentTime,6);
  p.playbackRate=0.5;ctx.currentTime+=2.075;close(p.currentTime,7);
  p.setLoop(true);p.currentTime=9;ctx.currentTime+=4.075;close(p.currentTime,1);
  p.setLoop(false);p.currentTime=9;ctx.currentTime+=4.075;p.tick();
  assert.equal(p.paused,true);close(p.currentTime,10);
});
test('device output timestamp takes precedence over latency estimate',async()=>{
  const {p,ctx}=setup();await p.play();ctx.currentTime=12;
  ctx.getOutputTimestamp=()=>({contextTime:11,performanceTime:performance.now()});
  assert.ok(Math.abs(p.currentTime-0.975)<0.001);
});
test('late resume cannot start a recording that was unloaded',async()=>{
  const {p,ctx}=setup();let resolve;
  ctx.resume=()=>new Promise(r=>{resolve=r;});
  const pending=p.play();p.pause();resolve();await pending;
  assert.equal(p.paused,true);assert.equal(p.source,null);
});
test('pre-stretched audio plays at unity rate and seeks in rendered seconds',async()=>{
  const {p,ctx}=setup();p.buffer={duration:20};p.renderRate=.5;p.rate=.5;
  p.currentTime=3;await p.play();
  assert.equal(p.source.playbackRate.value,1);
  assert.deepEqual(p.source.started,[10.025,6]);
  ctx.currentTime=12.075;close(p.currentTime,4);close(p.duration,10);
});
