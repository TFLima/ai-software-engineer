/** Production Angular bundle, simulated public API, no external repository/provider calls. */
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import { id, sha, analysis, findings, apiError } from './fixtures.mjs';
const root = join(dirname(fileURLToPath(import.meta.url)), '../dist/frontend/browser');
let server, browser, origin;
before(async () => {
  server = createServer(async (req, res) => {
    try {
      const name = new URL(req.url, 'http://localhost').pathname.slice(1) || 'index.html';
      if (name.includes('..') || name.startsWith('api/')) throw new Error();
      res.setHeader('Content-Type', name.endsWith('.js') ? 'application/javascript' : name.endsWith('.css') ? 'text/css' : 'text/html');
      res.end(await readFile(join(root, name)));
    } catch { res.writeHead(404); res.end(); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  origin = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({ headless: true, ...(process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {}) });
});
after(async () => { await browser?.close(); if (server) await new Promise(resolve => server.close(resolve)); });
async function session(t, handler, options = {}) {
  const context = await browser.newContext(options); t.after(() => context.close());
  const page = await context.newPage(); const errors = []; page.on('pageerror', e => errors.push(e.message));
  t.after(() => assert.deepEqual(errors, []));
  await page.route('**/api/**', handler); await page.clock.install(); await page.goto(origin); return page;
}
async function json(route, data, status = 200, headers = {}) { await route.fulfill({ status, contentType: 'application/json', headers, body: JSON.stringify(data) }); }
async function ready(page) { await page.locator('#repository').fill('https://GitHub.com/Example/Small-App.git/'); await page.getByRole('checkbox').check(); }
async function shown(page, text) { await page.getByText(text, { exact: true }).first().waitFor(); }
const start = page => page.getByRole('button', { name: 'Iniciar análise', exact: true });

test('consent gates admission; all lifecycle states, pagination, SHA and escaped HTML', async t => {
  let reads = 0, posts = 0;
  const page = await session(t, async route => {
    const req = route.request(), path = new URL(req.url());
    if (req.method() === 'POST') {
      posts++; assert.deepEqual(req.postDataJSON(), { repository_url: 'https://github.com/example/small-app' });
      assert.equal(req.headers()['accept'], 'application/json'); assert.match(req.headers()['idempotency-key'], /^[0-9a-f-]{36}$/);
      return json(route, { schema_version: 1, id, status: 'queued' }, 202);
    }
    if (path.pathname.endsWith('/findings')) return json(route, findings(Number(path.searchParams.get('page'))));
    return json(route, analysis(['queued', 'running', 'completed'][Math.min(reads++, 2)]));
  });
  await page.locator('#repository').fill('https://github.com/example/small-app'); assert.equal(await start(page).isEnabled(), false); assert.equal(posts, 0);
  await ready(page); await start(page).click(); await shown(page, 'Na fila');
  assert.equal(reads, 1); await page.clock.runFor(2000); await shown(page, 'Em análise'); assert.equal(reads, 2);
  await page.clock.runFor(4000); await shown(page, 'Concluída'); await shown(page, 'Achado 1');
  assert.equal(await page.locator('.finding').count(), 5); assert.equal(await page.locator('.finding img, .finding script').count(), 0);
  assert.equal(await page.evaluate(() => window.xss), undefined); await shown(page, sha); await shown(page, 'Linhas 1–10');
  if (process.env.B11_SCREENSHOT_DIR) await page.screenshot({ path: join(process.env.B11_SCREENSHOT_DIR, 'b11-desktop.png'), fullPage: true });
  await page.getByRole('button', { name: 'Próxima', exact: true }).click(); await shown(page, 'Achado 6'); assert.equal(await page.locator('.finding').count(), 1);
  await page.getByRole('button', { name: 'Anterior', exact: true }).click(); await shown(page, 'Achado 1');
  await page.clock.runFor(60000); assert.equal(reads, 3);
});

test('lost submission response and reload preserve the key, but acknowledgment resets', async t => {
  const keys = []; let posts = 0;
  const page = await session(t, route => {
    if (route.request().method() === 'POST') { keys.push(route.request().headers()['idempotency-key']); if (++posts === 1) return route.abort('failed'); return json(route, { schema_version: 1, id, status: 'failed' }, 202); }
    return json(route, analysis('failed'));
  });
  await ready(page); await start(page).click(); await page.getByText('O envio não foi confirmado.', { exact: false }).waitFor();
  await page.reload(); assert.equal(await page.getByRole('checkbox').isChecked(), false);
  await page.getByRole('checkbox').check(); await start(page).click(); await shown(page, 'Falhou');
  assert.equal(keys.length, 2); assert.equal(keys[0], keys[1]);
  assert.equal(await page.getByRole('heading', { name: 'Achados', exact: true }).count(), 0);
});

test('admission Retry-After disables submission without automatic POST retries', async t => {
  let calls = 0;
  const page = await session(t, route => { calls++; return json(route, apiError('admission_limited'), 429, { 'Retry-After': '60' }); });
  await ready(page); await start(page).click(); await page.getByText('Aguarde 60 segundos', { exact: false }).waitFor();
  assert.equal(await start(page).isEnabled(), false); await page.clock.runFor(60050); assert.equal(await start(page).isEnabled(), true); assert.equal(calls, 1);
});

test('terminal failure is actionable and stops polling without loading results', async t => {
  let reads = 0;
  const page = await session(t, route => { reads++; return json(route, analysis('failed')); });
  await page.goto(`${origin}/#analysis/${id}`); await shown(page, 'Falhou'); await page.getByText('o provedor de IA não está configurado', { exact: false }).waitFor();
  await page.clock.runFor(60000); assert.equal(reads, 1);
});

test('valid empty findings explain limitations and mobile layout stays within viewport', async t => {
  const page = await session(t, route => json(route, route.request().url().includes('/findings') ? findings(1, 0) : analysis()), { viewport: { width: 390, height: 844 } });
  await page.goto(`${origin}/#analysis/${id}`); await shown(page, 'Nenhum achado no contexto inspecionado');
  await page.getByText('Isso não certifica a qualidade', { exact: false }).waitFor();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  if (process.env.B11_SCREENSHOT_DIR) await page.screenshot({ path: join(process.env.B11_SCREENSHOT_DIR, 'b11-mobile.png'), fullPage: true });
});

test('backoff caps at 10s and new-analysis navigation cancels polling', async t => {
  let reads = 0;
  const page = await session(t, route => { reads++; return json(route, analysis('queued')); });
  await page.evaluate(() => {
    window.pollDelays = [];
    const schedule = window.setTimeout;
    window.setTimeout = (handler, delay, ...args) => {
      if ([2000, 4000, 8000, 10000].includes(delay)) window.pollDelays.push(delay);
      return schedule(handler, delay, ...args);
    };
  });
  await page.goto(`${origin}/#analysis/${id}`); await shown(page, 'Na fila');
  for (const delay of [2000, 4000, 8000, 10000, 10000]) {
    const previous = reads; await page.clock.runFor(delay); await page.waitForTimeout(100);
    assert.equal(reads, previous + 1);
  }
  assert.deepEqual(await page.evaluate(() => window.pollDelays), [2000, 4000, 8000, 10000, 10000, 10000]);
  await page.getByRole('button', { name: 'Nova análise', exact: true }).click();
  await page.waitForFunction(() => !location.hash); const stopped = reads;
  await page.clock.runFor(60000); assert.equal(reads, stopped);
});

test('five unavailable reads honor cooldown, pause and recover via explicit resume', async t => {
  let reads = 0;
  const page = await session(t, route => { reads++; return reads <= 5 ? json(route, apiError('application_unavailable'), 503, { 'Retry-After': '30' }) : json(route, analysis('failed')); });
  await page.goto(`${origin}/#analysis/${id}`); await page.getByText('A aplicação está temporariamente indisponível.', { exact: false }).waitFor();
  for (let n = 1; n < 5; n++) { await page.clock.runFor(30000); await page.waitForTimeout(100); }
  await shown(page, 'O acompanhamento está pausado.'); assert.equal(reads, 5); await page.clock.runFor(60000); assert.equal(reads, 5);
  await page.getByRole('button', { name: 'Retomar acompanhamento', exact: true }).click(); await shown(page, 'Falhou'); assert.equal(reads, 6);
});

test('invalid page SHA is not displayed; retry fetches the requested page', async t => {
  let pageTwo = 0;
  const page = await session(t, route => {
    const path = new URL(route.request().url()); if (!path.pathname.endsWith('/findings')) return json(route, analysis());
    const n = Number(path.searchParams.get('page')); if (n === 2 && ++pageTwo === 1) return json(route, { ...findings(2), commit_sha: 'b'.repeat(40) });
    return json(route, findings(n));
  });
  await page.goto(`${origin}/#analysis/${id}`); await shown(page, 'Achado 1');
  await page.getByRole('button', { name: 'Próxima', exact: true }).click(); await page.getByText('Os resultados não puderam ser validados.', { exact: false }).waitFor();
  assert.equal(await page.getByText('Achado 6', { exact: true }).count(), 0);
  await page.getByRole('button', { name: 'Tentar carregar novamente', exact: true }).click(); await shown(page, 'Achado 6'); assert.equal(pageTwo, 2);
});

test('unsupported status version is rejected and manual status refresh works', async t => {
  let reads = 0;
  const page = await session(t, route => json(route, ++reads === 1 ? { ...analysis(), schema_version: 2 } : analysis('failed')));
  await page.goto(`${origin}/#analysis/${id}`); await shown(page, 'O acompanhamento está pausado.');
  assert.equal(await page.getByRole('heading', { name: 'Achados', exact: true }).count(), 0);
  await page.getByRole('button', { name: 'Retomar acompanhamento', exact: true }).click(); await shown(page, 'Falhou');
});
