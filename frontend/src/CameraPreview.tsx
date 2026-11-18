import { useEffect, useState } from 'react';

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

export function CameraPreview({ camera }: { camera: Camera }) {
  const base = `/preview/${encodeURIComponent(camera.camera_id)}`;
  const [result, setResult] = useState<{ base: string; data?: PreviewStatus }>();
  const [streamFailed, setStreamFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const response = await fetch(`${base}/status.json`, {
          cache: 'no-store',
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(3000)]),
        });
        if (!response.ok) throw new Error('Preview unavailable');
        const data: PreviewStatus = await response.json();
        if (data.camera_id !== camera.camera_id) throw new Error('Unexpected camera');
        if (!controller.signal.aborted) setResult({ base, data });
      } catch {
        if (!controller.signal.aborted) setResult({ base });
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(() => void poll(), 1000);
      }
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [base, camera.camera_id]);

  useEffect(() => {
    if (!streamFailed) return;
    const timer = setTimeout(() => {
      setAttempt((value) => value + 1);
      setStreamFailed(false);
    }, 2000);
    return () => clearTimeout(timer);
  }, [streamFailed]);

  const status = result?.base === base ? result.data : undefined;
  const stale = status?.frame_age_seconds != null && status.frame_age_seconds > 5;
  const idle = camera.mode === 'idle' || status?.mode === 'idle';
  let message = '';
  if (!camera.online) message = 'Kamera offline. Oczekiwanie na połączenie…';
  else if (status?.error) message = `Błąd kamery: ${status.error}`;
  else if (!status) message = result?.base === base
    ? 'Podgląd niedostępny. Próbuję połączyć się ponownie…'
    : 'Łączenie z podglądem…';
  else if (idle) message = 'Kamera zatrzymana. Kliknij „Uruchom LIVE”, aby zobaczyć obraz, lub wybierz REPLAY.';
  else if (stale) message = 'Brak nowych klatek. Sprawdź połączenie kamery.';
  else if (!status.captured_at) message = 'Oczekiwanie na pierwszą klatkę…';
  else if (streamFailed) message = 'Nie udało się odebrać obrazu. Ponawiam połączenie…';

  return (
    <section className="camera-preview" aria-label={`Podgląd — ${cameraName(camera.camera_id)}`}>
      <div className="preview-screen">
        {message ? <p className="preview-message" role="status">{message}</p> : <>
          <img src={`${base}/stream.mjpg?attempt=${attempt}`}
            alt={`Podgląd obrazu — ${cameraName(camera.camera_id)}`}
            onError={() => setStreamFailed(true)} />
          <span className={`badge preview-mode ${status?.mode === 'replay' ? 'replay' : 'live'}`}>
            <span className="dot" />{status?.mode === 'replay' ? 'REPLAY' : 'LIVE'}
          </span>
        </>}
      </div>
      <div className="preview-caption">
        <span>{message ? 'Podgląd kamery' : `${status?.width} × ${status?.height}`}</span>
        {status?.detector === 'motion' && <span>Detekcja ruchu · ramki „unknown”</span>}
        {status?.detector === 'yolo' && <span>YOLO · samoloty i ptaki</span>}
      </div>
    </section>
  );
}
