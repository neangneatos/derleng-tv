/* Synthetic browser behavior, NOT device playback or upstream stream validation.
 * Run: node test_frontend.cjs [static-release-directory]
 * External scripts, media and fonts never reach the network.
 */
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');
let chromium;
try { ({chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright')); }
catch { throw new Error('Install browser test dependencies with npm ci and npx playwright install chromium, or set PLAYWRIGHT_MODULE.'); }
const root = path.resolve(process.argv[2] || path.join(__dirname, 'dist/hostinger'));
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const catalog = JSON.parse(fs.readFileSync(path.join(root, 'channels_public.json')));
const bootstrap = JSON.parse(html.match(/let channels = (\[.*?\]);/s)[1]);
const absent = catalog.find(c => !bootstrap.some(b => b.id === c.id));
assert(absent, 'Need full-catalog-only channel fixture');
const csp = fs.readFileSync(path.join(root, '.htaccess'), 'utf8').match(/Header always set Content-Security-Policy "([^"]+)"/)[1];
const server = http.createServer((req, res) => {
  res.setHeader('Content-Security-Policy', csp);
  const pathname = new URL(req.url, 'http://localhost').pathname;
  const name = pathname === '/' ? 'index.html' : pathname.slice(1);
  if (!/^(?:[a-zA-Z0-9_.-]+|logos\/[a-f0-9]{64}\.webp)$/.test(name)) { res.writeHead(404).end(); return; }
  try {
    res.setHeader('Content-Type', name.endsWith('.html') ? 'text/html' : name.endsWith('.webp') ? 'image/webp' : name.endsWith('.json') ? 'application/json' : 'application/octet-stream');
    res.end(fs.readFileSync(path.join(root, name)));
  } catch { res.writeHead(404).end(); }
});
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({headless: true});
  const results = [];
  async function scenario(name, run) {
    const context = await browser.newContext();
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', route => {
      const url = route.request().url();
      if (url.startsWith(base) && !url.includes('hls-')) return route.continue();
      return route.fulfill({status: 200, contentType: url.includes('css') ? 'text/css' : 'application/javascript', body: ''});
    });
    await page.addInitScript(() => {
      window.__cspViolations = [];
      document.addEventListener('securitypolicyviolation', e => window.__cspViolations.push(e.violatedDirective));
      window.__instances = [];
      window.__media = {paused: true, currentTime: 0, online: true};
      Object.defineProperty(navigator, 'onLine', {get: () => window.__media.online});
      const proto = HTMLMediaElement.prototype;
      Object.defineProperty(proto, 'paused', {get() { return window.__media.paused; }});
      Object.defineProperty(proto, 'currentTime', {get() { return window.__media.currentTime; }, set(v) { window.__media.currentTime = v; }});
      Object.defineProperty(proto, 'readyState', {get() { return 4; }});
      proto.play = function() { window.__media.paused = false; this.dispatchEvent(new Event('playing')); return Promise.resolve(); };
      proto.pause = function() { window.__media.paused = true; };
      proto.load = function() { window.__media.currentTime = 0; };
      proto.canPlayType = () => '';
      window.__listeners = new Map();
      const add = proto.addEventListener, remove = proto.removeEventListener;
      proto.addEventListener = function(name, fn, ...args) {
        if (this.id === 'video') { if (!window.__listeners.has(name)) window.__listeners.set(name, new Set()); window.__listeners.get(name).add(fn); }
        return add.call(this, name, fn, ...args);
      };
      proto.removeEventListener = function(name, fn, ...args) {
        window.__listeners.get(name)?.delete(fn);
        return remove.call(this, name, fn, ...args);
      };
      class Hls {
        static Events = {MANIFEST_PARSED: 'manifest', ERROR: 'error'};
        static ErrorTypes = {NETWORK_ERROR: 'network', MEDIA_ERROR: 'media'};
        static isSupported() { return true; }
        constructor() { this.handlers = {}; this.recoveries = 0; window.__instances.push(this); }
        on(name, fn) { this.handlers[name] = fn; if (name === 'manifest') queueMicrotask(() => this.emit('manifest', {})); }
        emit(name, data) { this.handlers[name]?.(name, data); }
        loadSource(source) { this.source = source; }
        attachMedia() {}
        detachMedia() {}
        stopLoad() {}
        startLoad() {}
        recoverMediaError() { this.recoveries++; }
        destroy() { this.destroyed = true; }
      }
      window.Hls = Hls;
    });
    await page.clock.install();
    try { await run(page, base); assert.deepEqual(errors, []); assert.deepEqual(await page.evaluate(() => window.__cspViolations), []); results.push({name, status: 'PASS'}); }
    catch (error) { results.push({name, status: 'FAIL', reason: error.message}); }
    finally { await context.close(); }
  }
  async function open(page, suffix = '') {
    await page.goto(base + '/' + suffix);
    await page.clock.runFor(600);
  }
  const text = page => page.locator('#now-state-text').textContent();
  await scenario('cid outside bootstrap resolves from versioned catalog', async page => {
    await open(page, '?cid=' + absent.id);
    await page.waitForFunction(id => window.__instances.some(h => h.source === id), absent.u);
    assert.equal(await page.locator('#now-title').textContent(), absent.n);
    assert.equal(await page.evaluate(() => window.__instances.length), 1);
  });
  await scenario('full catalog accepts HTTP and preserves nonstandard HTTPS ports', async page => {
    await open(page);
    await page.waitForFunction(() => fullCatalogLoaded);
    assert.equal(await page.evaluate(() => channels.length), catalog.length);
    for (const channel of [catalog.find(c => c.u.startsWith('http://')),
                           catalog.find(c => new URL(c.u).protocol === 'https:' && new URL(c.u).port)]) {
      assert(channel, 'Required scheme/port fixture');
      await open(page, '?cid=' + channel.id);
      await page.waitForFunction(url => window.__instances.some(h => h.source === url), (channel.p || channel.u).startsWith('http://') ? '/relay.php?cid=' + channel.id : (channel.p || channel.u));
      assert.equal(await page.locator('#now-title').textContent(), channel.n);
    }
  });
  await scenario('arbitrary u parameter never becomes a media source', async page => {
    await open(page, '?u=https%3A%2F%2Fattacker.invalid%2Fprivate.m3u8');
    assert(await page.evaluate(() => window.__instances.length > 0));
    assert(await page.evaluate(() => window.__instances.every(h => !h.source.includes('attacker.invalid'))));
  });
  await scenario('unknown cid fails cleanly without unrelated playback', async page => {
    await open(page, '?cid=unknown-channel');
    await page.waitForFunction(() => document.querySelector('#now-state-text').textContent.includes('UNAVAILABLE'));
    assert.equal(await page.evaluate(() => window.__instances.length), 0);
  });
  await scenario('unpaused ready media needs progress before PLAYING; stalled progress times out', async page => {
    await open(page);
    assert(!(await text(page)).includes('LIVE'));
    await page.evaluate(() => { const v = document.querySelector('#video'); v.currentTime = 1; v.dispatchEvent(new Event('timeupdate')); });
    assert((await text(page)).includes('LIVE'));
    await page.clock.runFor(21000);
    assert(!(await text(page)).includes('LIVE'));
  });
  await scenario('network stalled and transient waiting do not cover advancing video', async page => {
    await open(page);
    await page.evaluate(() => {
      const v = document.querySelector('#video');
      v.currentTime = 1; v.dispatchEvent(new Event('timeupdate'));
      v.dispatchEvent(new Event('stalled'));
    });
    assert((await text(page)).includes('LIVE'), 'Fetch stalled is not playback stalled');
    await page.evaluate(() => document.querySelector('#video').dispatchEvent(new Event('waiting')));
    assert((await text(page)).includes('LIVE'), 'Debounce transient waiting');
    await page.clock.runFor(400);
    await page.evaluate(() => {
      const v = document.querySelector('#video');
      v.currentTime = 1.4; v.dispatchEvent(new Event('timeupdate'));
    });
    await page.clock.runFor(1200);
    assert((await text(page)).includes('LIVE'));
  });
  await scenario('sustained waiting buffers and clears only with progress', async page => {
    await open(page);
    await page.evaluate(() => {
      const v = document.querySelector('#video');
      v.currentTime = 1; v.dispatchEvent(new Event('timeupdate'));
      v.dispatchEvent(new Event('waiting'));
    });
    await page.clock.runFor(1600);
    assert(!(await text(page)).includes('LIVE'));
    await page.evaluate(() => document.querySelector('#video').dispatchEvent(new Event('playing')));
    assert(!(await text(page)).includes('LIVE'));
    await page.evaluate(() => {
      const v = document.querySelector('#video');
      v.currentTime = 2; v.dispatchEvent(new Event('timeupdate'));
    });
    assert((await text(page)).includes('LIVE'));
  });
  await scenario('cached logos decode, failures use initials, and genres are reachable', async page => {
    await open(page);
    await page.waitForFunction(() => fullCatalogLoaded);
    const logo = page.locator('.channel-logo').first();
    assert(await logo.count(), 'Expected cached broadcaster logo');
    await logo.evaluate(img => img.decode());
    assert(await logo.evaluate(img => img.naturalWidth > 0));
    await logo.evaluate(img => img.dispatchEvent(new Event('error')));
    assert(await logo.evaluate(img => img.hidden));
    assert(await logo.locator('..').locator('.channel-initials').textContent());
    await page.locator('[data-cat="ALL"]').click();
    assert.equal(await page.evaluate(() => window.activeFiltered.length), catalog.length);
    const genres = [...new Set(catalog.map(c => c.t))];
    for (const genre of genres) {
      const tab = page.locator('.cat-btn[data-cat="' + genre + '"]');
      assert.equal(await tab.count(), 1, 'Genre needs a tab: ' + genre);
      await tab.click();
      assert.equal(await page.evaluate(() => window.activeFiltered.length), catalog.filter(c => c.t === genre).length);
    }
  });
  await scenario('verified HTTPS preference preserves channel ID and retries original relay', async page => {
    const ch = catalog.find(c => c.p && c.u.startsWith('http://'));
    assert(ch, 'Expected preferred HTTPS fixture');
    await open(page, '?cid=' + ch.id);
    assert.equal(await page.evaluate(() => window.__instances.at(-1).source), ch.p);
    await page.evaluate(() => {
      const h = window.__instances.at(-1);
      h.emit('error', {fatal:true,type:'media'});
      h.emit('error', {fatal:true,type:'media'});
    });
    await page.clock.runFor(1250);
    assert.equal(await page.evaluate(() => window.__instances.at(-1).source), '/relay.php?cid=' + ch.id);
    assert.equal(await page.locator('#now-title').textContent(), ch.n);
  });
  await scenario('country labels distinguish origin from feed markets', async page => {
    await open(page);
    await page.waitForFunction(() => fullCatalogLoaded);
    const labels = await page.evaluate(() => {
      const marketOnly = channels.find(c => c.country_basis === 'origin_unknown_curated_feed_market');
      const unknown = channels.find(c => c.country_basis === 'unresolved');
      const known = channels.find(c => c.country_basis === 'broadcaster_origin');
      return {market:getCountryLabel(marketOnly), unknown:getCountryLabel(unknown), known:getCountryLabel(known), knownGroup:known.g};
    });
    assert(labels.market.includes('origin unverified'));
    assert.equal(labels.unknown, 'Country unverified');
    assert.equal(labels.known, labels.knownGroup);
  });
  await scenario('fatal media recovery and application retries terminate', async page => {
    await open(page);
    for (let attempt = 0; attempt < 3; attempt++) {
      await page.evaluate(() => { const h = window.__instances.at(-1); h.emit('error', {fatal:true,type:'media'}); h.emit('error', {fatal:true,type:'media'}); });
      if (attempt < 2) await page.clock.runFor((attempt + 1) * 1200 + 20);
    }
    assert((await text(page)).includes('UNAVAILABLE'));
    await page.clock.runFor(30000);
    assert.equal(await page.evaluate(() => window.__instances.length), 3);
    assert(await page.evaluate(() => window.__instances.every(h => h.recoveries === 1 && h.destroyed)));
  });
  await scenario('rapid switching removes old listeners and ignores stale HLS callback', async page => {
    await open(page);
    await page.evaluate(() => { for (let i = 0; i < 12; i++) play(i % Math.min(2, window.activeFiltered.length)); });
    assert.equal(await page.evaluate(() => window.__listeners.get('timeupdate').size), 1);
    const before = await text(page);
    await page.evaluate(() => { const old = window.__instances[0]; old.emit('manifest', {}); old.emit('error', {fatal:true,type:'media'}); });
    assert.equal(await text(page), before);
    assert(await page.evaluate(() => window.__instances.slice(0, -1).every(h => h.destroyed)));
  });
  await scenario('offline stays OFFLINE despite buffered progress and online reconnects', async page => {
    await open(page);
    await page.evaluate(() => { window.__media.online = false; dispatchEvent(new Event('offline')); });
    assert((await text(page)).includes('OFFLINE'));
    await page.evaluate(() => { const v = document.querySelector('#video'); v.currentTime = 1; v.dispatchEvent(new Event('timeupdate')); });
    assert((await text(page)).includes('OFFLINE'), 'Buffered timeupdate must not overwrite OFFLINE');
    await page.evaluate(() => { window.__media.online = true; dispatchEvent(new Event('online')); });
    await page.clock.runFor(20);
    assert(!(await text(page)).includes('OFFLINE'));
  });
  await scenario('retry preserves playing channel after category filtering changes', async page => {
    await open(page);
    const source = await page.evaluate(() => window.__instances.at(-1).source);
    await page.evaluate(() => {
      document.querySelector('.cat-btn[data-cat="News"]').click();
      const h = window.__instances.at(-1);
      h.emit('error', {fatal:true,type:'media'});
      h.emit('error', {fatal:true,type:'media'});
    });
    await page.clock.runFor(1250);
    assert.equal(await page.evaluate(() => window.__instances.at(-1).source), source);
  });
  await scenario('delegated channel click works under release CSP', async page => {
    await open(page);
    const rows = page.locator('.channel-row');
    assert(await rows.count() > 1);
    const expected = await page.evaluate(() => { const c = window.activeFiltered[1]; const u = c.p || c.u; return u.startsWith('http://') ? '/relay.php?cid=' + c.id : u; });
    await rows.nth(1).click();
    assert.equal(await page.evaluate(() => window.__instances.at(-1).source), expected);
  });
  await scenario('responsive layouts keep player and channels accessible from phone to 4K', async page => {
    await open(page);
    for (const [width, height] of [[320,480],[320,568],[390,844],[568,320],[844,390],[768,1024],[820,1180],[1024,768],[1366,768],[1440,900],[1920,1080],[3840,2160]]) {
      await page.setViewportSize({width,height});
      const layout = await page.evaluate(() => {
        const box = id => { const r=document.querySelector(id).getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height,b:r.bottom,right:r.right}; };
        return {overflow:document.documentElement.scrollWidth > innerWidth + 1, player:box('#player-wrap'), list:box('#channel-list'), video:box('.video-viewport'), controls:box('#controls')};
      });
      assert(!layout.overflow, `Horizontal overflow at ${width}x${height}`);
      assert(layout.list.h >= 80, `Channel list too short at ${width}x${height}: ${JSON.stringify(layout)}`);
      assert(layout.list.b <= height + 1, `Clipped list at ${width}x${height}`);
      assert(layout.video.h >= 95, `Video collapsed at ${width}x${height}`);
      if (width >= 1000 || (width >= 560 && width > height)) {
        assert(layout.list.x >= layout.player.right - 1, `Missing split layout at ${width}x${height}`);
      }
      if (width >= 1366) assert(layout.video.h > 240, 'Desktop video still phone-sized');
      if (process.env.RESPONSIVE_SCREENSHOTS && [390,768,1366,1920].includes(width)) {
        await page.screenshot({path:path.join(process.env.RESPONSIVE_SCREENSHOTS, `layout-${width}x${height}.png`)});
      }
    }
  });
  await scenario('keyboard category activation, remote arrows and fullscreen exit remain usable', async page => {
    await page.setViewportSize({width:1920,height:1080});
    await open(page);
    const button=page.locator('[data-cat="Music"]');
    await button.focus();
    await page.keyboard.press('Enter');
    assert(await button.evaluate(el=>el.classList.contains('active')));
    assert.equal(await page.evaluate(()=>window.__media.paused),false, 'Category Enter must not toggle playback');
    await page.keyboard.press('ArrowRight');
    assert.notEqual(await page.evaluate(()=>document.activeElement.dataset.cat),'Music');
    await page.locator('.channel-row').first().focus();
    await page.keyboard.press('ArrowDown');
    assert.equal(await page.evaluate(()=>document.activeElement.dataset.idx),'1');
    await page.evaluate(()=>document.body.classList.add('is-fullscreen'));
    await page.keyboard.press('Escape');
    assert.equal(await page.evaluate(()=>document.body.classList.contains('is-fullscreen')),false);
    assert(await page.locator('#channel-list').isVisible());
  });
  await scenario('fullscreen fallback fills every viewport and Escape restores the layout', async page => {
    await open(page);
    await page.evaluate(()=>{document.querySelector('#player-wrap').requestFullscreen=undefined; document.querySelector('#player-wrap').webkitRequestFullscreen=undefined; document.querySelector('#player-wrap').webkitRequestFullScreen=undefined;});
    for (const [width,height] of [[320,568],[844,390],[768,1024],[1024,768],[1366,768],[1920,1080],[3840,2160]]) {
      await page.setViewportSize({width,height});
      await page.locator('#fullscreen-btn').click();
      const box=await page.locator('.video-viewport').boundingBox();
      assert(Math.abs(box.width-width)<=1 && Math.abs(box.height-height)<=1, `Fullscreen not filled at ${width}x${height}: ${JSON.stringify(box)}`);
      assert.equal(await page.locator('#channel-list').isVisible(),false);
      await page.locator('#fullscreen-btn').focus();
      assert.equal(await page.locator('.now-playing-bar').evaluate(el=>getComputedStyle(el).opacity),'1');
      await page.keyboard.press('Escape');
      assert(await page.locator('#channel-list').isVisible());
    }
  });
  await scenario('native fullscreen exit clears cinema mode and restores browsing', async page => {
    await page.setViewportSize({width:1366,height:768});
    await open(page);
    await page.locator('#fullscreen-btn').click();
    await page.waitForFunction(()=>!!document.fullscreenElement);
    await page.evaluate(()=>document.exitFullscreen());
    await page.waitForFunction(()=>!document.body.classList.contains('is-fullscreen'));
    assert(await page.locator('#channel-list').isVisible());
  });
  await scenario('authenticated selection switches in-place and repeated version does not restart', async page => {
    let pick = null;
    await page.addInitScript(() => { window.Telegram = {WebApp:{initData:'signed-fixture'}}; });
    await page.route('**/bot-selection.php', route => route.fulfill({contentType:'application/json',body:JSON.stringify({ok:true,auth_date:1,selection:pick})}));
    await open(page);
    const target = catalog.find(c => c.id !== bootstrap[0].id);
    pick = {cid:target.id,version:'101',at:2};
    await page.evaluate(() => syncBotSelection());
    assert.equal(await page.evaluate(() => currentChannel.id),target.id);
    assert.equal(new URL(page.url()).searchParams.get('cid'),target.id);
    const generation = await page.evaluate(() => playSessionId);
    await page.evaluate(() => syncBotSelection());
    assert.equal(await page.evaluate(() => playSessionId),generation);
    await page.evaluate(() => handleNavigation(false));
    assert.equal(await page.evaluate(() => playSessionId),generation);
  });
  await scenario('explicit channel link wins older bot selection', async page => {
    await page.addInitScript(() => { window.Telegram = {WebApp:{initData:'signed-fixture'}}; });
    await page.route('**/bot-selection.php', route => route.fulfill({contentType:'application/json',body:JSON.stringify({ok:true,auth_date:100,selection:{cid:bootstrap[0].id,version:'102',at:99}})}));
    await open(page,'?cid='+absent.id);
    await page.waitForFunction(() => fullCatalogLoaded && currentChannel);
    await page.evaluate(() => syncBotSelection());
    assert.equal(await page.evaluate(() => currentChannel.id),absent.id);
  });
  await scenario('ordinary browser makes no authenticated selection requests', async page => {
    let calls=0;
    await page.route('**/bot-selection.php', route => {calls++;return route.fulfill({status:401,body:'{}'});});
    await open(page);
    await page.evaluate(() => syncBotSelection());
    assert.equal(calls,0);
  });
  await scenario('minimized Telegram defers selection until activated', async page => {
    await page.addInitScript(() => { window.__tgEvents={}; window.Telegram={WebApp:{initData:'fixture',onEvent:(n,f)=>window.__tgEvents[n]=f}}; });
    await page.route('**/bot-selection.php', route=>route.fulfill({contentType:'application/json',body:JSON.stringify({ok:true,auth_date:1,selection:{cid:absent.id,version:'201',at:2}})}));
    await open(page);
    await page.waitForFunction(()=>fullCatalogLoaded);
    await page.evaluate(()=>{ window.__tgEvents.deactivated(); });
    const prior=await page.evaluate(()=>currentChannel?.id);
    await page.evaluate(()=>syncBotSelection());
    assert.equal(await page.evaluate(()=>currentChannel?.id),prior);
    await page.evaluate(()=>window.__tgEvents.activated());
    await page.waitForFunction(id=>currentChannel?.id===id,absent.id);
  });
  await scenario('older selection does not override newer local channel choice', async page => {
    await page.addInitScript(()=>{window.Telegram={WebApp:{initData:'fixture'}};});
    await page.route('**/bot-selection.php',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({ok:true,auth_date:1,selection:{cid:absent.id,version:'301',at:2}})}));
    await open(page); await page.waitForFunction(()=>fullCatalogLoaded);
    await page.evaluate(()=>{localChoiceAt=3;});
    const prior=await page.evaluate(()=>currentChannel?.id);
    await page.evaluate(()=>syncBotSelection());
    assert.equal(await page.evaluate(()=>currentChannel?.id),prior);
  });
  await browser.close();
  await new Promise(resolve => server.close(resolve));
  console.log(JSON.stringify({type:'synthetic-browser-regression', results}, null, 2));
  process.exitCode = results.some(r => r.status !== 'PASS') ? 1 : 0;
})().catch(error => { console.error(error); server.close(); process.exitCode = 1; });
