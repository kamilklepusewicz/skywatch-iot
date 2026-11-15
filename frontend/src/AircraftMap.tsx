import { useState } from 'react';

import { cameraName, timestamp } from './format';
import type { Aircraft, AircraftView, Camera, Coordinates, Observation, ObservationDetail, Scenario } from './types';

interface Marker extends Coordinates {
  id: string;
  label: string;
  kind: 'aircraft' | 'camera' | 'candidate' | 'origin';
  at?: string | null;
  snapshotAt?: string;
}

const offset = (longitude: number, origin: number) => ((longitude - origin + 540) % 360) - 180;
const RAD = Math.PI / 180;

function project(markers: Marker[], center: Coordinates | undefined) {
  if (!center) return [];
  const ratio = 2;
  const cosLatitude = Math.max(0.01, Math.cos(center.latitude * RAD));
  const coords = markers.map((marker) => ({
    ...marker, x: offset(marker.longitude, center.longitude) * cosLatitude,
    y: marker.latitude - center.latitude,
  }));
  const extent = Math.max(0.03, ...coords.map(({ x, y }) => Math.max(Math.abs(x) / ratio, Math.abs(y))));
  return coords.map(({ x, y, ...marker }) => ({
    ...marker, left: 50 + x / (extent * ratio) * 42, top: 50 - y / extent * 42,
  }));
}

function aircraftMarker(aircraft: Aircraft, candidate = false): Marker {
  return {
    ...aircraft, id: aircraft.address, label: aircraft.callsign ?? aircraft.address,
    kind: candidate ? 'candidate' : 'aircraft', at: aircraft.position_at,
  };
}

interface Props {
  view: AircraftView | undefined;
  error: string | undefined;
  cameras: Camera[];
  scenarios: Scenario[];
  scenarioId: string;
  selectScenario: (value: string) => void;
  observation: ObservationDetail | undefined;
  selection: Observation | null;
  maxPositionAge: number | undefined;
}

export function AircraftMap({
  view, error, cameras, scenarios, scenarioId, selectScenario, observation, selection, maxPositionAge,
}: Props) {
  const [active, setActive] = useState<string>();
  const mode = selection?.mode ?? (scenarioId ? 'replay' : 'live');
  const scenario = scenarios.find((item) => item.scenario_id === (selection ? selection.scenario_id : scenarioId));
  const locations = mode === 'replay'
    ? Object.entries(scenario?.cameras ?? {})
    : cameras.map(({ camera_id, location }) => [camera_id, location] as const);
  const cameraMarkers: Marker[] = locations.flatMap(([id, location]) => location
    ? [{ ...location, id: `camera:${id}`, label: cameraName(id), kind: 'camera' }]
    : []);
  const positions = view?.snapshot?.aircraft ?? [];
  const current = positions.filter(({ position_at, position_age_seconds }) =>
    position_at !== null && position_age_seconds !== null
    && maxPositionAge !== undefined && position_age_seconds <= maxPositionAge,
  );
  const aircraft = selection
    ? (observation?.match.candidates ?? []).map((candidate) => ({
        ...aircraftMarker(candidate.aircraft, true), snapshotAt: candidate.snapshot_at,
      }))
    : current.map((item) => aircraftMarker(item));
  const markers = [...aircraft, ...cameraMarkers];
  const origin = selection ? (mode === 'replay' ? scenario?.origin : null) : view?.origin;
  if (origin) markers.push({ ...origin, id: 'origin', label: 'Środek obszaru ADS-B', kind: 'origin' });
  const points = project(markers, origin ?? cameraMarkers[0] ?? markers[0]);
  const selected = points.find((item) => item.id === active);
  const synthetic = observation?.match.synthetic ?? selection?.match.synthetic ?? view?.synthetic;
  return <section className="card map-card" aria-labelledby="map-title">
    <div className="card-top">
      <div>
        <h2 id="map-title">Mapa lotnicza</h2>
        <p>Widok współrzędnych offline</p>
      </div>
      <span className={`badge ${mode}`}>{mode === 'live' ? 'LIVE' : 'REPLAY · historia'}</span>
    </div>
    {!selection && <label className="map-select">
      Źródło mapy
      <select value={scenarioId} onChange={(event) => {
        selectScenario(event.target.value);
        setActive(undefined);
      }}>
        <option value="">ADS-B LIVE</option>
        {scenarios.map((item) => <option key={item.scenario_id} value={item.scenario_id}>
          REPLAY · {item.scenario_id}{item.synthetic ? ' (syntetyczny)' : ''}
        </option>)}
      </select>
    </label>}
    {selection && <p className="map-meta">Kandydaci dla klatki (UTC) · {timestamp(selection.captured_at)}</p>}
    <div className="map-meta label-row">
      {view?.snapshot && <span>Snapshot ADS-B (UTC) · {timestamp(view.snapshot.source_at)}
        {' · pobranie: '}{timestamp(view.snapshot.retrieved_at)}
      </span>}
      {synthetic && <span className="badge synthetic">Dane syntetyczne</span>}
    </div>
    <div className="plot" role="group" aria-label="Pozycje ADS-B i kamery">
      <span className="north" aria-hidden="true">↑ N</span>
      {points.map((point) => <button key={point.id} className={`marker marker-${point.kind}`}
        style={{ left: `${point.left}%`, top: `${point.top}%` }}
        onClick={() => setActive(point.id)} aria-pressed={active === point.id} aria-label={point.label}
        title={point.at ? `${point.label} · pozycja (UTC) ${timestamp(point.at)}` : point.label}>
        {point.kind === 'camera' ? '▪' : point.kind === 'origin' ? '+' : point.kind === 'candidate' ? '◆' : '•'}
      </button>)}
      {points.length === 0 && <p className="plot-empty">{view || error || selection ? 'Brak pozycji do wyświetlenia' : 'Wczytywanie pozycji…'}</p>}
    </div>
    <div className="map-legend" aria-hidden="true">
      <span><i className="legend-aircraft" />Statek powietrzny</span>
      <span><i className="legend-candidate" />Kandydat</span>
      <span><i className="legend-camera" />Kamera</span>
    </div>
    {selected && <p className="map-meta" aria-live="polite">
      <strong>{selected.label}</strong> · {selected.latitude.toFixed(4)}°, {selected.longitude.toFixed(4)}°
      {selected.at !== undefined && ` · pozycja (UTC) ${timestamp(selected.at)}`}
      {selected.snapshotAt && ` · snapshot (UTC) ${timestamp(selected.snapshotAt)}`}
    </p>}
    {error && <p role="alert" className="error-text">Błąd mapy: {error}</p>}
    {view?.status === 'stale' && <p className="map-meta">Snapshot poza oknem czasowym.</p>}
    {view?.status === 'unavailable' && <p className="map-meta">Brak snapshotu ADS-B dla wybranego źródła.</p>}
    {!!positions.length && current.length < positions.length && maxPositionAge !== undefined
      && <p className="map-meta">Pominięto pozycje zbyt stare lub bez czasu pozycji.</p>}
    {view?.snapshot?.aircraft.length === 0 && <p className="map-meta">Snapshot nie zawiera pozycji.</p>}
  </section>;
}
