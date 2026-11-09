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
  if (!/^[a-zA-Z0-9_.-]+$/.test(name)) { res.writeHead(404).end(); return; }
  try {
    res.setHeader('Content-Type', name.endsWith('.html') ? 'text/html' : name.endsWith('.json') ? 'application/json' : 'application/octet-stream');
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
      await page.waitForFunction(url => window.__instances.some(h => h.source === url), channel.u);
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
    const expected = await page.evaluate(() => window.activeFiltered[1].u);
    await rows.nth(1).click();
    assert.equal(await page.evaluate(() => window.__instances.at(-1).source), expected);
  });
  await browser.close();
  await new Promise(resolve => server.close(resolve));
  console.log(JSON.stringify({type:'synthetic-browser-regression', results}, null, 2));
  process.exitCode = results.some(r => r.status !== 'PASS') ? 1 : 0;
})().catch(error => { console.error(error); server.close(); process.exitCode = 1; });
