import test from 'node:test';
import assert from 'node:assert/strict';
import { awaitIdentityConfiguration, identityDecision, identityEndpoint, signedAssertionLines, validateIdentityImage } from './identityVerification.js';

test('cancelling an endpoint wait promptly releases its caller while the shared lookup continues', async () => {
  let resolveLookup;
  const lookup = new Promise((resolve) => { resolveLookup = resolve; });
  const controller = new AbortController();
  const pending = awaitIdentityConfiguration(() => lookup, controller.signal);
  controller.abort();
  await assert.rejects(pending, { name: 'AbortError' });
  resolveLookup({ backend: 'http://localhost:8000' });
  assert.deepEqual(await lookup, { backend: 'http://localhost:8000' });
  assert.deepEqual(await awaitIdentityConfiguration(() => lookup, new AbortController().signal), { backend: 'http://localhost:8000' });
  let calls = 0;
  await assert.rejects(awaitIdentityConfiguration(() => { calls += 1; }, controller.signal), { name: 'AbortError' });
  assert.equal(calls, 0);
});

test('identity images can only use the configured loopback identity endpoints', () => {
  assert.equal(identityEndpoint('http://127.0.0.1:8123', 'compare'), 'http://127.0.0.1:8123/identity/compare');
  assert.equal(identityEndpoint('http://localhost:8123/', 'status'), 'http://localhost:8123/identity/status');
  assert.equal(identityEndpoint('http://[::1]:8123/api', 'verify'), 'http://[::1]:8123/api/identity/verify');
  for (const endpoint of ['https://provider.example', 'http://192.168.1.2:8000', 'http://localhost.evil.test', 'file:///tmp/images', 'http://user:secret@localhost', 'http://localhost?next=https://example.com', 'http://localhost/#redirect']) {
    assert.throws(() => identityEndpoint(endpoint, 'compare'), /local Mirid backend/);
  }
  assert.throws(() => identityEndpoint('http://localhost:8000', '../chat'), /Unknown identity operation/);
});

test('research policy support is never presented as a production identity verification', () => {
  assert.equal(identityDecision({ decision: { status: 'experimental_supported' } }).supported, false);
  assert.equal(identityDecision({ research_mode: false, decision: { status: 'experimental_supported' } }).supported, false);
  assert.deepEqual(identityDecision({ research_mode: true, decision: { status: 'experimental_supported' } }), { title: 'Research policy supported', supported: true });
  assert.equal(identityDecision({ http_status: 400, research_mode: true, decision: { status: 'experimental_supported' } }).supported, false);
  for (const status of ['accepted', 'verified', 'review_required', 'insufficient_evidence', 'research_only', 'rejected', 'unknown']) {
    assert.equal(identityDecision({ research_mode: true, decision: { status } }).supported, false);
  }
});

test('signed evidence accepts compact tokens only and never parses self-asserted claims as trust', () => {
  assert.deepEqual(signedAssertionLines('aaa.bbb\n\n ccc.ddd '), ['aaa.bbb', 'ccc.ddd']);
  assert.throws(() => signedAssertionLines(''), /at least one/);
  assert.throws(() => signedAssertionLines('{"identity_verified":true}'), /compact signed/);
  assert.throws(() => signedAssertionLines('aaa.bbb.ccc'), /compact signed/);
  assert.throws(() => signedAssertionLines(`aaa.${'b'.repeat(8192)}`), /compact signed/);
  assert.throws(() => signedAssertionLines(Array(9).fill('aaa.bbb').join('\n')), /no more than 8/);
});

test('image size and supported media types are checked before submission', () => {
  validateIdentityImage({ type: 'image/jpeg', size: 100 });
  assert.throws(() => validateIdentityImage({ type: 'image/svg+xml', size: 100 }), /JPEG, PNG or WebP/);
  assert.throws(() => validateIdentityImage({ type: 'image/png', size: 8_000_001 }), /smaller than 8 MB/);
  assert.throws(() => validateIdentityImage({ type: 'image/webp', size: 0 }), /smaller than/);
});
