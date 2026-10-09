export const IDENTITY_MAX_IMAGE_BYTES = 8_000_000;
export const IDENTITY_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);

// The desktop host may keep retrying its shared endpoint lookup. Abandon only
// this caller when it is cancelled, without interrupting other Mirid features.
export function awaitIdentityConfiguration(load, signal) {
  return new Promise((resolve, reject) => {
    const abort = () => {
      signal?.removeEventListener('abort', abort);
      reject(signal?.reason || new DOMException('The operation was cancelled.', 'AbortError'));
    };
    if (signal?.aborted) {
      abort();
      return;
    }
    signal?.addEventListener('abort', abort, { once: true });
    Promise.resolve().then(load).then(
      (configuration) => { signal?.removeEventListener('abort', abort); resolve(configuration); },
      (error) => { signal?.removeEventListener('abort', abort); reject(error); },
    );
  });
}

// Identity images must never follow the general remote-provider routing used by
// chat. Reject non-loopback endpoints before reading an image into a request.
export function identityEndpoint(backend, action) {
  if (!['status', 'compare', 'challenge', 'verify', 'session'].includes(action)) {
    throw new Error('Unknown identity operation.');
  }
  let url;
  try { url = new URL(backend); } catch {
    throw new Error('Mirid has not supplied a local identity service.');
  }
  if (!['http:', 'https:'].includes(url.protocol)
      || !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
      || url.username || url.password || url.search || url.hash) {
    throw new Error('Identity comparison requires the local Mirid backend on this computer.');
  }
  url.pathname = `${url.pathname.replace(/\/+$/, '')}/identity/${action}`;
  return url.href;
}

export function validateIdentityImage(file, maxBytes = IDENTITY_MAX_IMAGE_BYTES) {
  if (!file || !IDENTITY_IMAGE_TYPES.has(file.type)) {
    throw new Error('Choose a JPEG, PNG or WebP image.');
  }
  if (file.size === 0 || file.size > maxBytes) {
    throw new Error(`Choose an image smaller than ${(maxBytes / 1_000_000).toFixed(0)} MB.`);
  }
}

export function imageDataUrl(blob, signal) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    const cancelled = () => new DOMException('The operation was cancelled.', 'AbortError');
    const onAbort = () => {
      reader.abort();
      reject(cancelled());
    };
    const cleanup = () => signal?.removeEventListener('abort', onAbort);
    if (signal?.aborted) {
      reject(cancelled());
      return;
    }
    signal?.addEventListener('abort', onAbort, { once: true });
    reader.onload = () => { cleanup(); resolve(reader.result); };
    reader.onerror = () => { cleanup(); reject(new Error('The selected image could not be read.')); };
    reader.onabort = () => { cleanup(); reject(cancelled()); };
    reader.readAsDataURL(blob);
  });
}

export function signedAssertionLines(text) {
  const tokens = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  if (!tokens.length) throw new Error('Paste at least one signed assertion token.');
  if (tokens.length > 8) throw new Error('Use no more than 8 signed assertion tokens.');
  if (tokens.some((token) => token.length > 8192 || !/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(token))) {
    throw new Error('Each line must contain one compact signed assertion token.');
  }
  return tokens;
}

export function identityDecision(result) {
  const status = result?.decision?.status;
  if (result?.http_status >= 400) return { title: 'Additional evidence needed', supported: false };
  if (status === 'experimental_supported' && result.research_mode === true) {
    return { title: 'Research policy supported', supported: true };
  }
  if (status === 'research_only') return { title: 'Research result - identity not verified', supported: false };
  if (status === 'rejected') return { title: 'Evidence not accepted', supported: false };
  return { title: 'Additional evidence needed', supported: false };
}
