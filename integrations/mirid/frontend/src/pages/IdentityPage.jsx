import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Camera, CameraOff, Check, Copy, Fingerprint, ImagePlus, Loader2, RefreshCw, ShieldCheck, Trash2 } from 'lucide-react';
import { Button } from '../components/ui/button';
import { getBackendUrl, loadPortConfig } from '../config/api';
import {
  IDENTITY_MAX_IMAGE_BYTES,
  awaitIdentityConfiguration,
  identityDecision,
  identityEndpoint,
  imageDataUrl,
  signedAssertionLines,
  validateIdentityImage,
} from '../utils/identityVerification';

const inputClass = 'w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

function cameraError(error) {
  if (error?.name === 'NotAllowedError') return 'Camera access was not granted. Allow camera access in the desktop permissions, or choose a probe image.';
  if (error?.name === 'NotFoundError') return 'No camera was found. Connect one, or choose a probe image.';
  if (error?.name === 'NotReadableError') return 'The camera is busy or unavailable. Close other camera apps, or choose a probe image.';
  return 'Mirid could not open the camera. Choose a probe image to continue.';
}

function ImageCard({ title, description, image, onChange, inputId, children }) {
  return (
    <section className="min-w-0 rounded-xl border bg-card p-4 md:p-5" aria-labelledby={`${inputId}-title`}>
      <h2 id={`${inputId}-title`} className="text-base font-semibold">{title}</h2>
      <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{description}</p>
      <div className="my-4 flex aspect-[4/3] min-h-40 items-center justify-center overflow-hidden rounded-lg border border-dashed bg-muted/25">
        {image ? (
          <img src={image.url} alt={`${title} preview`} className="h-full w-full object-contain" />
        ) : (
          <div className="flex flex-col items-center gap-2 px-4 text-center text-sm text-muted-foreground">
            <ImagePlus className="h-7 w-7" aria-hidden="true" />
            <span>No image selected</span>
          </div>
        )}
      </div>
      {image && <p className="mb-3 break-words text-xs text-muted-foreground">{image.label}</p>}
      <label htmlFor={inputId} className="mb-2 block text-sm font-medium">{image ? 'Replace image' : 'Choose image'}</label>
      <input id={inputId} type="file" accept="image/jpeg,image/png,image/webp" onChange={onChange}
        className="block w-full min-w-0 text-sm text-muted-foreground file:mr-3 file:rounded-md file:border file:border-input file:bg-background file:px-3 file:py-2 file:text-sm file:font-medium file:text-foreground" />
      {children}
    </section>
  );
}

export default function IdentityPage() {
  const [images, setImages] = useState({ reference: null, probe: null });
  const imagesRef = useRef(images);
  const [consent, setConsent] = useState(false);
  const [service, setService] = useState(null);
  const [serviceError, setServiceError] = useState('');
  const [statusLoading, setStatusLoading] = useState(true);
  const [operation, setOperation] = useState('');
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [subject, setSubject] = useState('');
  const [challenge, setChallenge] = useState(null);
  const challengeRef = useRef(null);
  const [assertions, setAssertions] = useState('');
  const [copied, setCopied] = useState(false);
  const [cameraState, setCameraState] = useState('off');
  const [cameraReady, setCameraReady] = useState(false);
  const streamRef = useRef(null);
  const videoRef = useRef(null);
  const cameraEpoch = useRef(0);
  const requestRef = useRef(null);
  const statusRequestRef = useRef(null);
  const mountedRef = useRef(true);
  const copyTimerRef = useRef(null);

  const stopCamera = useCallback(() => {
    cameraEpoch.current += 1;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    if (mountedRef.current) {
      setCameraState('off');
      setCameraReady(false);
    }
  }, []);

  const cancelOperation = useCallback(() => {
    requestRef.current?.abort();
    requestRef.current = null;
    setOperation('');
  }, []);

  const releaseChallenge = useCallback(() => {
    const session = challengeRef.current;
    challengeRef.current = null;
    if (!session?.session_id) return;
    // Best-effort release also runs when navigation unmounts this page. The
    // backend's short TTL removes a session if the local service is unreachable.
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    awaitIdentityConfiguration(loadPortConfig, controller.signal).then(() => fetch(identityEndpoint(getBackendUrl(), 'session'), {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: session.session_id }),
      cache: 'no-store',
      redirect: 'error',
      credentials: 'same-origin',
      keepalive: true,
      signal: controller.signal,
    })).catch(() => { /* Session expiry remains the fallback. */ }).finally(() => clearTimeout(timeout));
  }, []);

  const invalidateEvidence = useCallback(() => {
    cancelOperation();
    releaseChallenge();
    setResult(null);
    setChallenge(null);
    setAssertions('');
    setCopied(false);
    setError('');
  }, [cancelOperation, releaseChallenge]);

  const localRequest = useCallback(async (action, body, signal) => {
    await awaitIdentityConfiguration(loadPortConfig, signal);
    if (signal.aborted) throw new DOMException('The operation was cancelled.', 'AbortError');
    const endpoint = identityEndpoint(getBackendUrl(), action);
    const response = await fetch(endpoint, {
      method: body ? 'POST' : 'GET',
      ...(body ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}),
      signal,
      cache: 'no-store',
      redirect: 'error',
      credentials: 'same-origin',
    });
    let data;
    try { data = await response.json(); } catch {
      throw new Error('The local identity service returned an unreadable response.');
    }
    if (!response.ok) {
      // An invalid signature is a completed review decision, even though the
      // service correctly returns HTTP 400 and consumes the one-use session.
      if (action === 'verify' && data?.decision) return { ...data, http_status: response.status };
      const detail = typeof data?.detail === 'string' ? data.detail : typeof data?.error === 'string' ? data.error : '';
      const failure = new Error(detail || `The local identity service could not complete this request (${response.status}).`);
      failure.httpStatus = response.status;
      throw failure;
    }
    return data;
  }, []);

  const refreshStatus = useCallback(async () => {
    statusRequestRef.current?.abort();
    const controller = new AbortController();
    statusRequestRef.current = controller;
    setStatusLoading(true);
    setServiceError('');
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const data = await localRequest('status', null, controller.signal);
      if (!controller.signal.aborted && mountedRef.current) setService(data);
    } catch (cause) {
      if (mountedRef.current && statusRequestRef.current === controller) {
        setService(null);
        setServiceError(controller.signal.aborted ? 'The local identity service did not respond. Check that Mirid is running, then refresh.' : cause.message || 'The local identity service could not be reached.');
      }
    } finally {
      clearTimeout(timeout);
      if (mountedRef.current && statusRequestRef.current === controller) setStatusLoading(false);
    }
  }, [localRequest]);

  useEffect(() => {
    mountedRef.current = true;
    refreshStatus();
    return () => {
      mountedRef.current = false;
      requestRef.current?.abort();
      statusRequestRef.current?.abort();
      releaseChallenge();
      clearTimeout(copyTimerRef.current);
      stopCamera();
      Object.values(imagesRef.current).forEach((image) => { if (image) URL.revokeObjectURL(image.url); });
      imagesRef.current = { reference: null, probe: null };
    };
  }, [refreshStatus, releaseChallenge, stopCamera]);

  useEffect(() => {
    if (cameraState !== 'on' || !videoRef.current || !streamRef.current) return;
    videoRef.current.srcObject = streamRef.current;
    videoRef.current.play().catch(() => {
      if (mountedRef.current) {
        stopCamera();
        setError('The camera preview could not start. Choose a probe image to continue.');
      }
    });
  }, [cameraState, stopCamera]);

  const replaceImage = (key, file, label) => {
    const maxBytes = Math.min(IDENTITY_MAX_IMAGE_BYTES, service?.limits?.max_image_bytes || IDENTITY_MAX_IMAGE_BYTES);
    validateIdentityImage(file, maxBytes);
    invalidateEvidence();
    const previous = imagesRef.current[key];
    const next = { ...imagesRef.current, [key]: { file, url: URL.createObjectURL(file), label } };
    imagesRef.current = next;
    setImages(next);
    if (previous) URL.revokeObjectURL(previous.url);
  };

  const chooseImage = (key, event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    try {
      if (key === 'probe') stopCamera();
      replaceImage(key, file, file.name);
    } catch (cause) {
      setError(cause.message);
    }
  };

  const openCamera = async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('This desktop webview does not provide camera access. Choose a probe image to continue.');
      return;
    }
    stopCamera();
    const epoch = cameraEpoch.current;
    setError('');
    setCameraState('opening');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } } });
      if (!mountedRef.current || epoch !== cameraEpoch.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      setCameraState('on');
    } catch (cause) {
      if (mountedRef.current && epoch === cameraEpoch.current) {
        setCameraState('off');
        setError(cameraError(cause));
      }
    }
  };

  const captureProbe = () => {
    const video = videoRef.current;
    if (!video?.videoWidth || !video.videoHeight) return;
    const canvas = document.createElement('canvas');
    const scale = Math.min(1, 1600 / Math.max(video.videoWidth, video.videoHeight));
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    const context = canvas.getContext('2d');
    if (!context) {
      setError('Mirid could not capture this camera frame. Choose a probe image to continue.');
      return;
    }
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const epoch = cameraEpoch.current;
    canvas.toBlob((blob) => {
      canvas.width = 0;
      canvas.height = 0;
      if (!mountedRef.current || epoch !== cameraEpoch.current) return;
      if (!blob) {
        setError('The camera frame could not be captured. Try again.');
        return;
      }
      try {
        replaceImage('probe', blob, 'Captured camera frame');
        stopCamera();
      } catch (cause) { setError(cause.message); }
    }, 'image/jpeg', 0.92);
  };

  const clearSession = () => {
    invalidateEvidence();
    stopCamera();
    Object.values(imagesRef.current).forEach((image) => { if (image) URL.revokeObjectURL(image.url); });
    imagesRef.current = { reference: null, probe: null };
    setImages(imagesRef.current);
    setSubject('');
    setConsent(false);
  };

  const run = async (action) => {
    if (!consent || !imagesRef.current.reference || !imagesRef.current.probe) return;
    const selected = imagesRef.current;
    cancelOperation();
    const controller = new AbortController();
    requestRef.current = controller;
    setOperation(action);
    setError('');
    setResult(null);
    const timeout = setTimeout(() => controller.abort(), 60000);
    try {
      let body;
      if (action === 'verify') {
        if (!challenge?.session_id) throw new Error('Prepare a new challenge before submitting signed evidence.');
        body = { session_id: challenge.session_id, assertions: signedAssertionLines(assertions) };
      } else {
        if (action === 'challenge' && !subject.trim()) throw new Error('Enter the subject identifier used by your trusted issuer.');
        await awaitIdentityConfiguration(loadPortConfig, controller.signal);
        identityEndpoint(getBackendUrl(), action);
        const [referenceImage, probeImage] = await Promise.all([
          imageDataUrl(selected.reference.file, controller.signal),
          imageDataUrl(selected.probe.file, controller.signal),
        ]);
        body = { reference_image: referenceImage, probe_image: probeImage, consent: true,
          ...(action === 'challenge' ? { subject: subject.trim() } : {}) };
      }
      const data = await localRequest(action, body, controller.signal);
      if (controller.signal.aborted || !mountedRef.current) return;
      if (action === 'challenge') {
        if (!data?.session_id || !data?.challenge) throw new Error('The identity service did not return a usable challenge.');
        releaseChallenge();
        challengeRef.current = data;
        setChallenge(data);
        setAssertions('');
        setCopied(false);
      } else {
        setResult(data);
        if (action === 'verify') {
          releaseChallenge();
          setChallenge(null);
          setAssertions('');
        }
      }
    } catch (cause) {
      if (mountedRef.current && requestRef.current === controller) {
        if (action === 'verify' && cause.httpStatus) {
          releaseChallenge();
          setChallenge(null);
          setAssertions('');
        }
        setError(controller.signal.aborted ? 'The identity request timed out. Retry when the local engine is ready.' : cause.message || 'The local identity request failed.');
      }
    } finally {
      clearTimeout(timeout);
      if (mountedRef.current && requestRef.current === controller) {
        requestRef.current = null;
        setOperation('');
      }
    }
  };

  const copyChallenge = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(challenge, null, 2));
      if (!mountedRef.current) return;
      setCopied(true);
      clearTimeout(copyTimerRef.current);
      copyTimerRef.current = setTimeout(() => { if (mountedRef.current) setCopied(false); }, 2000);
    } catch {
      setError('Clipboard access is unavailable. Select and copy the challenge text below.');
    }
  };

  const ready = Boolean(images.reference && images.probe && consent && service?.available && service?.models_ready);
  const busy = Boolean(operation);
  const decision = identityDecision(result);
  const similarity = result?.face?.status === 'compared' && Number.isFinite(result?.face?.cosine_similarity) ? result.face.cosine_similarity : null;
  const reasons = Array.isArray(result?.decision?.reasons) ? result.decision.reasons.filter((reason) => typeof reason === 'string') : [];

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6 pb-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-2xl">
          <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-widest text-muted-foreground"><Fingerprint className="h-4 w-4" aria-hidden="true" />Local identity tools</div>
          <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">Identity verification</h1>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">Explore facial variation with a local comparison and signed identity evidence. Results apply to the configured research policy.</p>
        </div>
        <Button variant="outline" size="sm" onClick={clearSession}><Trash2 className="mr-2 h-4 w-4" aria-hidden="true" />Clear session</Button>
      </header>

      <section className="flex flex-wrap items-start justify-between gap-3 rounded-xl border bg-card px-4 py-3" aria-label="Local engine status">
        <div className="min-w-0 text-sm">
          <p className="font-medium">{statusLoading ? 'Checking the local engine...' : serviceError ? 'Local engine unavailable' : service?.models_ready ? 'Local face engine ready' : 'Face models are not installed'}</p>
          <p className="mt-1 break-words text-xs leading-relaxed text-muted-foreground">{serviceError || (service?.models_ready ? `${service.engine || 'Local face comparison'}. Research verification. ${service.trust_configured && service.calibration_configured ? 'Issuer trust and calibration are configured.' : 'Issuer trust and calibration must be configured for a supported research result.'}` : 'Install the identity face models in the local backend, then refresh.')}</p>
        </div>
        <Button variant="ghost" size="sm" disabled={statusLoading} onClick={refreshStatus}><RefreshCw className={`mr-2 h-4 w-4 ${statusLoading ? 'animate-spin' : ''}`} aria-hidden="true" />Refresh</Button>
      </section>

      <div className="grid gap-4 md:grid-cols-2">
        <ImageCard title="Reference portrait" description="Choose the reference image for this one-to-one comparison." image={images.reference} inputId="identity-reference" onChange={(event) => chooseImage('reference', event)} />
        <ImageCard title="Probe image" description="Use a camera frame or a second image to test a change in appearance." image={images.probe} inputId="identity-probe" onChange={(event) => chooseImage('probe', event)}>
          <div className="mt-4 border-t pt-4">
            {cameraState === 'off' ? (
              <Button variant="outline" className="w-full" onClick={openCamera}><Camera className="mr-2 h-4 w-4" aria-hidden="true" />Open camera</Button>
            ) : (
              <div className="space-y-3">
                {cameraState === 'opening' ? <p role="status" className="text-sm text-muted-foreground">Waiting for camera permission...</p> : (
                  <video ref={videoRef} autoPlay muted playsInline onLoadedMetadata={() => setCameraReady(true)} aria-label="Live camera preview" className="aspect-video w-full rounded-lg bg-black object-contain" />
                )}
                <div className="flex flex-wrap gap-2">
                  <Button onClick={captureProbe} disabled={!cameraReady}><Camera className="mr-2 h-4 w-4" aria-hidden="true" />Capture frame</Button>
                  <Button variant="outline" onClick={stopCamera}><CameraOff className="mr-2 h-4 w-4" aria-hidden="true" />Close camera</Button>
                </div>
              </div>
            )}
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">The camera closes after capture. A camera frame does not establish liveness or rule out a replay.</p>
          </div>
        </ImageCard>
      </div>

      <section className="space-y-4 rounded-xl border bg-card p-4 md:p-5" aria-label="Comparison controls">
        <label className="flex cursor-pointer items-start gap-3 text-sm leading-relaxed">
          <input type="checkbox" checked={consent} onChange={(event) => { setConsent(event.target.checked); if (!event.target.checked) invalidateEvidence(); }} className="mt-1 h-4 w-4 shrink-0 accent-primary" />
          <span>I have permission to use these images and consent to processing them for this comparison on this computer.</span>
        </label>
        <div className="flex flex-wrap items-center gap-3">
          <Button disabled={!ready || busy} onClick={() => run('compare')}>
            {operation === 'compare' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> : <Fingerprint className="mr-2 h-4 w-4" aria-hidden="true" />}
            {operation === 'compare' ? 'Comparing images...' : 'Compare faces'}
          </Button>
          <p className="max-w-xl text-xs leading-relaxed text-muted-foreground">Images stay in this page and the local identity service. They are not added to chat, sent to a model provider, or saved in browser storage.</p>
        </div>
      </section>

      <details className="rounded-xl border bg-card p-4 md:p-5">
        <summary className="cursor-pointer text-sm font-semibold">Signed identity evidence</summary>
        <div className="mt-4 space-y-4">
          <p className="text-sm leading-relaxed text-muted-foreground">Create a challenge for these exact images, then supply assertions from your configured trusted issuer. The service checks their signatures and session binding before applying its verification policy.</p>
          <div>
            <label htmlFor="identity-subject" className="mb-2 block text-sm font-medium">Subject identifier</label>
            <input id="identity-subject" type="text" autoComplete="off" value={subject} maxLength={256} placeholder="Identifier recognised by your trusted issuer" className={inputClass}
              onChange={(event) => { setSubject(event.target.value); invalidateEvidence(); }} />
          </div>
          <Button variant="outline" disabled={!ready || !subject.trim() || busy} onClick={() => run('challenge')}>
            {operation === 'challenge' && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />}
            {operation === 'challenge' ? 'Preparing challenge...' : 'Prepare challenge'}
          </Button>
          {challenge && (
            <div className="space-y-4 rounded-lg border bg-background p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <label htmlFor="identity-challenge" className="text-sm font-medium">Session challenge</label>
                <Button variant="ghost" size="sm" onClick={copyChallenge}>{copied ? <Check className="mr-2 h-4 w-4" aria-hidden="true" /> : <Copy className="mr-2 h-4 w-4" aria-hidden="true" />}{copied ? 'Copied' : 'Copy challenge'}</Button>
              </div>
              <textarea id="identity-challenge" readOnly rows={8} value={JSON.stringify(challenge, null, 2)} className={`${inputClass} font-mono text-xs`} />
              <div>
                <label htmlFor="identity-assertions" className="mb-2 block text-sm font-medium">Signed assertions</label>
                <textarea id="identity-assertions" value={assertions} rows={5} autoComplete="off" spellCheck={false} className={`${inputClass} font-mono text-xs`} placeholder="One compact signed token per line" onChange={(event) => { setAssertions(event.target.value); setError(''); }} />
              </div>
              <Button disabled={!ready || !assertions.trim() || busy} onClick={() => run('verify')}>
                {operation === 'verify' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> : <ShieldCheck className="mr-2 h-4 w-4" aria-hidden="true" />}
                {operation === 'verify' ? 'Checking signed evidence...' : 'Verify signed evidence'}
              </Button>
              <p className="text-xs leading-relaxed text-muted-foreground">A valid signature proves control of a key. Identity also depends on trusted enrolment, the required attestations and a calibrated comparison policy.</p>
            </div>
          )}
        </div>
      </details>

      {error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">{error}</div>}
      {result && (
        <section aria-label="Identity result" aria-live="polite" className="space-y-4 rounded-xl border bg-card p-4 md:p-5">
          <div className="flex items-start gap-3">
            {decision.supported ? <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-hidden="true" /> : <Fingerprint className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" aria-hidden="true" />}
            <div>
              <h2 className="text-lg font-semibold">{decision.title}</h2>
              {decision.supported && <p className="mt-1 text-sm text-muted-foreground">This session meets the configured research policy. It is not a production identity credential.</p>}
              {result.face?.status === 'inconclusive' && <p className="mt-1 text-sm text-muted-foreground">The images did not yield a usable face comparison. Try clear portraits with one visible face in each image.</p>}
            </div>
          </div>
          {similarity !== null && <div className="rounded-lg bg-muted/40 px-4 py-3"><p className="text-xs text-muted-foreground">Cosine similarity</p><p className="mt-1 font-mono text-2xl tabular-nums">{similarity.toFixed(4)}</p><p className="mt-1 text-xs leading-relaxed text-muted-foreground">A comparison score, not the probability that both images show the same person.</p></div>}
          {reasons.length > 0 && <ul className="list-disc space-y-1 pl-5 text-sm leading-relaxed text-muted-foreground">{reasons.map((reason, index) => <li key={`${index}-${reason}`}>{reason}</li>)}</ul>}
          <details className="border-t pt-3"><summary className="cursor-pointer text-sm font-medium">Technical result</summary><pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-muted/40 p-3 text-xs">{JSON.stringify(result, null, 2)}</pre></details>
        </section>
      )}
      <p className="text-xs leading-relaxed text-muted-foreground">JPEG, PNG or WebP, up to 8 MB each. Clear session or leave this page to release the previews and close the camera. Challenge images are held by the local service only until the session is used or expires.</p>
    </div>
  );
}
