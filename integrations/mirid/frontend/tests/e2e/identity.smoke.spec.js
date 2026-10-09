import { expect, test } from '@playwright/test';

test.use({ launchOptions: process.env.MIRID_CHROME ? { executablePath: process.env.MIRID_CHROME } : {} });
test.setTimeout(180_000);

const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64');
const IMAGE = { name: 'consented-test.png', mimeType: 'image/png', buffer: PNG };

async function openIdentity(page) {
  await page.route('https://**', (route) => route.abort());
  await page.route('**/identity/status', (route) => route.fulfill({ json: {
    available: true, models_ready: true, research_mode: true,
    trust_configured: false, calibration_configured: false, engine: 'OpenCV YuNet + SFace',
    limits: { max_image_bytes: 8_000_000, max_pixels: 16_000_000 },
  } }));
  await page.goto('/tests/e2e/fixtures/identity-smoke.html', { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'Identity verification', exact: true })).toBeVisible();
  await expect(page.getByText('Local face engine ready', { exact: true })).toBeVisible();
}

test('consented comparison and signed evidence stay local, fail closed and clear in-memory previews', async ({ page }, testInfo) => {
  const sent = [];
  await page.route('**/identity/compare', async (route) => {
    sent.push({ url: route.request().url(), body: route.request().postDataJSON() });
    await route.fulfill({ json: { research_mode: true, face: { status: 'compared', cosine_similarity: 0.7234, metric: 'cosine' }, decision: { status: 'insufficient_evidence', reasons: ['Signed identity and liveness evidence is required.'] } } });
  });
  await page.route('**/identity/challenge', async (route) => {
    sent.push({ url: route.request().url(), body: route.request().postDataJSON() });
    await route.fulfill({ json: { session_id: 'session-test', challenge: 'challenge-test', audience: 'mirid-identity-v1', subject: 'subject-test', evidence_digest: 'sha256-test', expires_at: 1999999999 } });
  });
  await page.route('**/identity/verify', async (route) => {
    sent.push({ url: route.request().url(), body: route.request().postDataJSON() });
    await route.fulfill({ status: 400, json: { research_mode: true, decision: { status: 'review_required', reasons: ['The issuer is not trusted by this installation.'] } } });
  });
  const deleted = [];
  await page.route('**/identity/session', async (route) => {
    deleted.push(route.request().postDataJSON());
    await route.fulfill({ json: { cleared: true } });
  });
  await openIdentity(page);
  await page.locator('#identity-reference').setInputFiles(IMAGE);
  await page.locator('#identity-probe').setInputFiles(IMAGE);
  await expect(page.getByRole('button', { name: 'Compare faces', exact: true })).toBeDisabled();
  expect(sent).toHaveLength(0);
  await page.getByRole('checkbox', { name: /I have permission to use these images/ }).check();
  await page.getByRole('button', { name: 'Compare faces', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Additional evidence needed', exact: true })).toBeVisible();
  await expect(page.getByText('0.7234', { exact: true })).toBeVisible();
  expect(sent[0].body.consent).toBe(true);
  expect(sent[0].body.reference_image).toMatch(/^data:image\/png;base64,/);
  expect(new URL(sent[0].url).hostname).toMatch(/^(localhost|127\.0\.0\.1)$/);
  await page.getByText('Signed identity evidence', { exact: true }).click();
  await page.getByLabel('Subject identifier').fill('subject-test');
  await page.getByRole('button', { name: 'Prepare challenge', exact: true }).click();
  await expect(page.getByLabel('Session challenge')).toHaveValue(/challenge-test/);
  await page.getByLabel('Signed assertions', { exact: true }).fill('aaa.bbb');
  await page.getByRole('button', { name: 'Verify signed evidence', exact: true }).click();
  await expect(page.getByText('The issuer is not trusted by this installation.', { exact: true })).toBeVisible();
  expect(sent[2].body).toEqual({ session_id: 'session-test', assertions: ['aaa.bbb'] });
  await expect.poll(() => deleted.length).toBe(1);
  await expect(page.getByRole('heading', { name: 'Identity verified', exact: true })).toHaveCount(0);
  const screenshotPath = testInfo.outputPath('identity-desktop.png');
  await page.screenshot({ path: screenshotPath, fullPage: true });
  await testInfo.attach('identity-desktop', { path: screenshotPath, contentType: 'image/png' });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'Clear session', exact: true }).click();
  await expect(page.getByAltText('Reference portrait preview')).toHaveCount(0);
  await expect(page.getByAltText('Probe image preview')).toHaveCount(0);
  await expect(page.getByRole('checkbox', { name: /I have permission to use these images/ })).not.toBeChecked();
  const stored = await page.evaluate(() => JSON.stringify({ ...localStorage }));
  expect(stored).not.toContain('data:image/');
  expect(stored).not.toContain('aaa.bbb');
  expect(stored).not.toContain('subject-test');
});

test('camera is explicit and its tracks stop after capture, clear and navigation', async ({ page }) => {
  await page.addInitScript(() => {
    window.__identityTestStreams = [];
    navigator.mediaDevices.getUserMedia = async () => {
      const canvas = document.createElement('canvas');
      canvas.width = 320;
      canvas.height = 240;
      const context = canvas.getContext('2d');
      context.fillStyle = '#758493';
      context.fillRect(0, 0, 320, 240);
      const stream = canvas.captureStream(5);
      window.__identityTestStreams.push(stream);
      return stream;
    };
  });
  await openIdentity(page);
  expect(await page.evaluate(() => window.__identityTestStreams.length)).toBe(0);
  await page.getByRole('button', { name: 'Open camera', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Capture frame', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Capture frame', exact: true }).click();
  await expect(page.getByAltText('Probe image preview')).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.__identityTestStreams.every((stream) => stream.getTracks().every((track) => track.readyState === 'ended')))).toBe(true);
  await page.getByRole('button', { name: 'Open camera', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Capture frame', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Clear session', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.__identityTestStreams.every((stream) => stream.getTracks().every((track) => track.readyState === 'ended')))).toBe(true);
  await page.getByRole('button', { name: 'Open camera', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Capture frame', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Leave identity page', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Identity verification', exact: true })).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => window.__identityTestStreams.every((stream) => stream.getTracks().every((track) => track.readyState === 'ended')))).toBe(true);
});
