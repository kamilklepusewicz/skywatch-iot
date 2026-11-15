import { useCallback, useEffect, useRef, useState } from 'react';

import { AircraftMap } from './AircraftMap';
import { CameraCard } from './Cameras';
import { History, ObservationDetails } from './Observations';
import { resources, useResource, useUpdates } from './api';
import type { Resource } from './api';
import { cameraName, metric } from './format';
import type { AircraftView, Camera, Health, Observation, ObservationDetail, Scenario } from './types';

const connectionLabel = { connecting: 'Łączenie', online: 'Połączono', retrying: 'Ponowne łączenie' };
const PAGE_SIZE = 30;
const initialRevisions: Record<Resource, number> = {
  health: 0, cameras: 0, scenarios: 0, observations: 0, aircraft: 0,
};

export function App() {
  const [revision, setRevision] = useState(initialRevisions);
  const [cameraFilter, setCameraFilter] = useState('');
  const [modeFilter, setModeFilter] = useState('');
  const [scenarioFilter, setScenarioFilter] = useState('');
  const [cursors, setCursors] = useState<string[]>([]);
  const [selected, setSelected] = useState<Observation | null>(null);
  const [mapScenario, setMapScenario] = useState('');
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const pending = useRef(new Set<Resource>());
  const refresh = useCallback((affected: readonly Resource[] = resources) => {
    for (const resource of affected) pending.current.add(resource);
    if (refreshTimer.current !== undefined) return;
    refreshTimer.current = setTimeout(() => {
      refreshTimer.current = undefined;
      const changes = [...pending.current];
      pending.current.clear();
      setRevision((value) => {
        const next = { ...value };
        for (const resource of changes) next[resource] += 1;
        return next;
      });
    }, 220);
  }, []);
  useEffect(() => {
    const queued = pending.current;
    return () => {
      clearTimeout(refreshTimer.current);
      refreshTimer.current = undefined;
      queued.clear();
    };
  }, []);
  const connection = useUpdates(refresh);

  const health = useResource<Health>('/api/health', revision.health);
  const cameras = useResource<Camera[]>('/api/cameras', revision.cameras);
  const scenarios = useResource<Scenario[]>('/api/scenarios', revision.scenarios);
  const historyQuery = new URLSearchParams({ limit: String(PAGE_SIZE + 1) });
  const cursor = cursors.at(-1);
  if (cursor) historyQuery.set('before', cursor);
  if (cameraFilter) historyQuery.set('camera_id', cameraFilter);
  if (modeFilter) historyQuery.set('mode', modeFilter);
  if (scenarioFilter) historyQuery.set('scenario_id', scenarioFilter);
  const observations = useResource<Observation[]>(`/api/observations?${historyQuery}`, revision.observations);
  const page = observations?.data?.slice(0, PAGE_SIZE);
  const hasOlder = (observations?.data?.length ?? 0) > PAGE_SIZE;
  const detail = useResource<ObservationDetail>(
    selected ? `/api/observations/${encodeURIComponent(selected.observation_id)}` : null,
    revision.observations,
  );
  const mapQuery = new URLSearchParams({ mode: mapScenario ? 'replay' : 'live' });
  if (mapScenario) mapQuery.set('scenario_id', mapScenario);
  const map = useResource<AircraftView>(selected ? null : `/api/aircraft?${mapQuery}`, revision.aircraft);
  const error = health?.error ?? cameras?.error ?? scenarios?.error ?? observations?.error;
  const brokerReady = health?.data?.mqtt_subscribed ?? false;
  const controlsReady = brokerReady && !health?.error && !cameras?.error && connection !== 'retrying';
  const feedTiming = health?.data?.adsb_timing;
  const brokerLabel = brokerReady ? 'Połączony' : health?.data?.mqtt_connected ? 'Brak subskrypcji' : 'Rozłączony';

  return <>
    <header className="site-header">
      <div className="header-inner">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">⌁</span>
          <div><p>SkyWatch IoT</p><span>Panel obserwacji lotniczych</span></div>
        </div>
        <div className="label-row connection">
          <span className={`badge ${brokerReady ? 'good' : 'muted'}`}>MQTT · {health?.data ? brokerLabel : '…'}</span>
          <span className={`badge ${connection === 'online' ? 'good' : 'muted'}`}>
            <span className="dot" />{connectionLabel[connection]}
          </span>
        </div>
      </div>
    </header>
    <main>
      {connection === 'retrying' && <p className="connection-notice" role="status">
        Utracono połączenie WebSocket. Historia i mapa mogą być nieaktualne.
      </p>}
      {error && <div className="error-banner" role="alert">
        <span>Błąd pobierania danych: {error}</span>
        <button onClick={() => refresh()}>Spróbuj ponownie</button>
      </div>}
      <section className="camera-section" aria-labelledby="camera-title">
        <h1 id="camera-title">Kamery</h1>
        {cameras?.data
          ? <div className="camera-grid">{cameras.data.map((camera) => <CameraCard
              key={camera.camera_id} camera={camera} scenarios={scenarios?.data ?? []}
              brokerReady={controlsReady} refresh={() => refresh(['cameras'])} />)}</div>
          : !error && <p className="card empty">Wczytywanie kamer…</p>}
        {cameras?.data?.length === 0 && <p className="card empty">Brak zarejestrowanych kamer.</p>}
      </section>
      <div className="workspace">
        <section className="card history" aria-labelledby="history-title">
          <div className="card-top history-heading">
            <h2 id="history-title">Historia obserwacji</h2>
            <div className="label-row filters">
              <label><span className="sr-only">Filtr kamery</span>
                <select value={cameraFilter} onChange={(event) => { setCameraFilter(event.target.value); setCursors([]); }}>
                  <option value="">Wszystkie kamery</option>
                  {cameras?.data?.map((camera) =>
                    <option key={camera.camera_id} value={camera.camera_id}>{cameraName(camera.camera_id)}</option>)}
                </select>
              </label>
              <label><span className="sr-only">Filtr źródła</span>
                <select value={modeFilter} onChange={(event) => { setModeFilter(event.target.value);
                  if (event.target.value === 'live') setScenarioFilter('');
                  setCursors([]); }}>
                  <option value="">LIVE i REPLAY</option><option value="live">LIVE</option><option value="replay">REPLAY</option>
                </select>
              </label>
              <label><span className="sr-only">Filtr scenariusza</span>
                <select value={scenarioFilter} disabled={modeFilter === 'live'} onChange={(event) => {
                  setScenarioFilter(event.target.value);
                  setCursors([]);
                }}>
                  <option value="">Wszystkie scenariusze</option>
                  {scenarios?.data?.map(({ scenario_id }) =>
                    <option key={scenario_id} value={scenario_id}>{scenario_id}</option>)}
                </select>
              </label>
            </div>
          </div>
          {(!observations?.error || observations.data) && <History
            observations={page} selected={selected?.observation_id ?? null} open={setSelected} />}
          {(cursors.length > 0 || hasOlder) && <div className="pagination">
            <button disabled={!cursors.length} onClick={() => setCursors(cursors.slice(0, -1))}>Nowsze</button>
            <button disabled={!hasOlder} onClick={() => {
              const last = page?.at(-1);
              if (last) setCursors([...cursors, last.observation_id]);
            }}>Starsze</button>
          </div>}
          {detail?.data && <ObservationDetails observation={detail.data} error={detail.error}
            close={() => setSelected(null)} />}
          {selected && !detail?.data && <div className="details">
            {detail?.error
              ? <p role="alert" className="error-text">Błąd szczegółów: {detail.error}</p>
              : <p className="muted-text">Wczytywanie szczegółów…</p>}
            <button onClick={() => setSelected(null)}>Zamknij</button>
          </div>}
        </section>
        <aside className="map-column">
          <AircraftMap view={map?.data}
            error={map?.error} maxPositionAge={health?.data?.timing?.max_position_age_seconds}
            cameras={cameras?.data ?? []} scenarios={scenarios?.data ?? []} scenarioId={mapScenario}
            selectScenario={setMapScenario} observation={detail?.data} selection={selected} />
          {feedTiming?.warning && <p className="error-text feed-error">
            ADS-B LIVE · różnica pobranie − czas źródła: {metric(feedTiming.retrieval_minus_source_seconds, 's')}.
          </p>}
          {health?.data?.adsb_last_error && <p className="error-text feed-error">ADS-B LIVE · {health.data.adsb_last_error}</p>}
        </aside>
      </div>
    </main>
  </>;
}
