// Optional integration check: requires Playwright + Chromium, not a project dependency.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
(async()=>{
  const browser=await chromium.launch({headless:true, ...(process.env.BROWSER_CHANNEL?{channel:process.env.BROWSER_CHANNEL}:{})});
  try {
    const page=await browser.newPage();
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto((process.env.VIEWER_URL||'http://127.0.0.1:8771')+'/?run=playback-sync-v1&recording=timing-clicks&speed=0.5');
    await page.waitForFunction(()=>document.getElementById('playClock').disabled===false);
    assert.equal(await page.locator('#run').inputValue(),'playback-sync-v1');
    assert.equal(await page.locator('#speed').inputValue(),'0.5');
    assert.match(await page.locator('#eventStatus').textContent(),/5 events/);
    await page.locator('#playClock').click();
    await page.waitForFunction(()=>player&&!player.paused&&player.currentTime>0.2);
    const time=await page.evaluate(()=>({position:player.currentTime,rate:player.playbackRate,
      duration:player.duration,renderedDuration:player.buffer.duration,context:audioContext.state,clock:!!audioContext.getOutputTimestamp}));
    assert.equal(time.rate,0.5);assert.equal(time.duration,6);assert.equal(time.renderedDuration,12);assert.equal(time.context,'running');
    assert.equal(await page.evaluate(()=>player.source.playbackRate.value),1);
    await page.locator('#playClock').click();
    assert.equal(await page.evaluate(()=>player.paused),true);
    await page.locator('#plot').focus();await page.keyboard.press('ArrowRight');
    const sourcePosition=await page.evaluate(()=>player.currentTime);
    assert.equal(await page.locator('#audio').count(),0);
    assert.equal(await page.locator('#engine').count(),0);
    await page.locator('#speed').selectOption('0.75');
    await page.waitForFunction(()=>player?.renderRate===0.75);
    assert.ok(Math.abs(await page.evaluate(()=>player.currentTime)-sourcePosition)<0.01);
    await page.locator('#rewindClock').click();
    assert.equal(await page.evaluate(()=>player.currentTime),0);
    await page.locator('#run').selectOption('correction-review-v2');
    await page.locator('#dataset').selectOption('babyslakh');
    await page.locator('#recording').selectOption({label:'[failed] babyslakh-Track00001-S03'});
    await page.waitForFunction(()=>events.length===2);
    assert.match(await page.locator('#eventList').textContent(),/Overlapping same-pitch start/);
    await page.locator('#eventList summary').first().click();
    await page.locator('#eventList button').first().click();
    await page.waitForFunction(()=>clip&&player&&events.length===2&&clip.start>0);
    assert.equal(await page.evaluate(()=>events.some(e=>e.start_seconds>=clip.start&&e.start_seconds<clip.end)),true);
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({status:'passed',...time}));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
