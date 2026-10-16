/** B13 real edge/API/queue/FastAPI/database; only acquisition and LLM are replayed. */
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
const origin = 'http://127.0.0.1:8080';
const sha = '7fd1a60b01f91b314f59955a4e4d4e80d8edf11d';
let browser;
before(async () => {
  assert.equal(process.env.B13_ACCEPTANCE, '1', 'Use scripts/verify-mvp.py against its disposable test stack');
  browser = await chromium.launch({ headless: true, ...(process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {}) });
});
after(async () => { await browser?.close(); });

for (const scenario of ['hello-world', 'xss', 'invalid-json']) {
  test(`integrated browser submission → persisted ${scenario}`, async t => {
    const context = await browser.newContext(); t.after(() => context.close());
    const page = await context.newPage(); const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(origin);
    await page.locator('#repository').fill(`https://github.com/octocat/${scenario}`);
    await page.getByRole('checkbox').check();
    const submission = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith('/api/analyses'));
    await page.getByRole('button', { name: 'Iniciar análise', exact: true }).click();
    const response = await submission;
    assert.equal(response.status(), 202);
    const { id } = await response.json();
    assert.match(id, /^[0-9a-f-]{36}$/);
    if (scenario === 'invalid-json') {
      await page.getByText('Falhou', { exact: true }).waitFor({ timeout: 90000 });
      const status = await (await context.request.get(`${origin}/api/analyses/${id}`)).json();
      assert.equal(status.error.code, 'invalid_findings');
      assert.equal(await page.locator('.finding').count(), 0);
    } else {
      await page.locator('.status[data-status="completed"], .status[data-status="failed"]').waitFor({ timeout: 90000 });
      const terminal = await (await context.request.get(`${origin}/api/analyses/${id}`)).json();
      assert.equal(terminal.status, 'completed', `Unexpected terminal error: ${terminal.error?.code ?? 'none'}`);
      await page.locator('.finding').waitFor();
      assert.equal(await page.locator('.finding').count(), 1);
      assert.equal(await page.locator('.finding img, .finding script').count(), 0);
      assert.equal(await page.evaluate(() => window.b13xss), undefined);
      await page.getByText(sha, { exact: true }).waitFor();
      await page.getByText('Linhas 1–1', { exact: true }).waitFor();
      const status = await (await context.request.get(`${origin}/api/analyses/${id}`)).json();
      const findings = await (await context.request.get(`${origin}/api/analyses/${id}/findings`)).json();
      assert.equal(status.status, 'completed');
      assert.equal(status.coverage.included_lines, 1);
      assert.equal(status.provenance.provider, 'fake');
      assert.equal(status.commit_sha, sha);
      assert.equal(findings.data.length, 1);
      assert.deepEqual(findings.data[0].evidence, [{ path: 'README', start_line: 1, end_line: 1 }]);
      // A new browser load must recover durable results without resubmission.
      await page.reload();
      await page.locator('.finding').waitFor();
      assert.equal(await page.locator('.finding').count(), 1);
    }
    assert.deepEqual(errors, []);
  });
}
