import { useCallback, useEffect, useState } from 'react';

import { cameraName } from './format';
import type { Camera, Mode } from './types';

interface PreviewStatus {
  camera_id: string;
  mode: Mode | 'idle';
  scenario_id: string | null;
  captured_at: string | null;
  width: number | null;
  height: number | null;
  frame_age_seconds: number | null;
  detector: string;
  error: string | null;
}

const POLL_INTERVAL = 1000;
const STREAM_RETRY_INTERVAL = 2000;
const MAX_RETRY_INTERVAL = 15_000;
const STOPPED = 'Kamera zatrzymana. Uruchom LIVE lub wybierz REPLAY, aby zobaczyć obraz.';

interface StreamState {
  attempt: number;
  phase: 'loading' | 'ready' | 'retrying';
  delay: number;
}

function PreviewStream({ base, name, mode }: { base: string; name: string; mode: PreviewStatus['mode'] }) {
  const [stream, setStream] = useState<StreamState>({ attempt: 0, phase: 'loading', delay: STREAM_RETRY_INTERVAL });
  const setSource = useCallback((image: HTMLImageElement | null) => {
    if (!image) return;
    image.src = `${base}/stream.mjpg?attempt=${stream.attempt}`;
    return () => image.removeAttribute('src');
  }, [base, stream.attempt]);

  function showFrame() {
    setStream((previous) => previous.phase === 'loading'
      ? { ...previous, phase: 'ready', delay: STREAM_RETRY_INTERVAL }
      : previous);
  }

  useEffect(() => {
    if (stream.phase !== 'retrying') return;
    const timer = setTimeout(() => setStream((previous) => ({
      attempt: previous.attempt + 1,
      phase: 'loading',
      delay: Math.min(previous.delay * 2, MAX_RETRY_INTERVAL),
    })), stream.delay);
    return () => clearTimeout(timer);
  }, [stream.delay, stream.phase]);

  if (stream.phase === 'retrying') {
    return <p className="preview-message" role="status">Nie udało się odebrać obrazu. Ponawiam połączenie…</p>;
  }

  const ready = stream.phase === 'ready';
  return <>
    <img ref={setSource} hidden={!ready} alt={`Podgląd obrazu (${name})`} onLoad={showFrame}
      onError={() => setStream((previous) => ({ ...previous, phase: 'retrying' }))} />
    {ready
      ? <span className={`badge preview-mode ${mode}`}><span className="dot" />{mode === 'replay' ? 'REPLAY' : 'LIVE'}</span>
      : <p className="preview-message" role="status">Łączenie ze strumieniem…</p>}
  </>;
}

export function CameraPreview({ camera }: { camera: Camera }) {
  const { camera_id: cameraId, online, mode } = camera;
  const base = `/preview/${encodeURIComponent(cameraId)}`;
  const name = cameraName(cameraId);
  const idle = mode === 'idle';
  const [result, setResult] = useState<{ base: string; data?: PreviewStatus }>();

  useEffect(() => {
    if (!online) {
      setResult(undefined);
      return;
    }
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let delay = POLL_INTERVAL;
    async function poll() {
      try {
        const response = await fetch(`${base}/status.json`, {
          cache: 'no-store',
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(3000)]),
        });
        if (!response.ok) throw new Error('Preview unavailable');
        const data: PreviewStatus = await response.json();
        if (data.camera_id !== cameraId) throw new Error('Unexpected camera');
        delay = POLL_INTERVAL;
        if (!controller.signal.aborted) setResult({ base, data });
      } catch {
        delay = Math.min(delay * 2, MAX_RETRY_INTERVAL);
        if (!controller.signal.aborted) setResult({ base });
      } finally {
        // An idle agent can report a capture error after it stops.
        if (!idle && !controller.signal.aborted) timer = setTimeout(() => void poll(), delay);
      }
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [base, cameraId, idle, online]);

  const status = online && result?.base === base ? result.data : undefined;
  const stale = status?.frame_age_seconds != null && status.frame_age_seconds > 5;
  let message = '';
  if (!online) message = 'Kamera offline. Oczekiwanie na połączenie…';
  else if (status?.error && (!idle || status.mode === 'idle')) message = `Błąd kamery: ${status.error}`;
  else if (idle || status?.mode === 'idle') message = STOPPED;
  else if (!status) message = result?.base === base
    ? 'Podgląd niedostępny. Próbuję połączyć się ponownie…'
    : 'Łączenie z podglądem…';
  else if (stale) message = 'Brak nowych klatek. Sprawdź połączenie kamery.';
  else if (!status.captured_at) message = 'Oczekiwanie na pierwszą klatkę…';

  return (
    <section className="camera-preview" aria-label={`Podgląd (${name})`}>
      <div className="preview-screen">
        {status && !message
          ? <PreviewStream key={base} base={base} name={name} mode={status.mode} />
          : <p className="preview-message" role="status">{message}</p>}
      </div>
      <div className="preview-caption">
        <span>{message ? 'Podgląd kamery' : `${status?.width} × ${status?.height}`}</span>
        {status?.detector === 'motion' && <span>Detekcja ruchu · ramki „unknown”</span>}
        {status?.detector === 'yolo' && <span>YOLO · samoloty i ptaki</span>}
      </div>
    </section>
  );
}
