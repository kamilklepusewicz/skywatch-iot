import { cameraName, matchLabel, matchReason, metric, objectLabel, timestamp } from './format';
import type { MatchSummary, Observation, ObservationDetail } from './types';

export function MatchBadge({ match }: { match: MatchSummary }) {
  return <span className={`badge match-${match.status}`}>
    {match.status === 'multiple' ? `${match.candidate_count} kandydatów` : matchLabel[match.status]}
  </span>;
}

interface HistoryProps {
  observations: Observation[] | undefined;
  selected: string | null;
  open: (observation: Observation) => void;
}

export function History({ observations, selected, open }: HistoryProps) {
  if (!observations) return <p className="empty">Wczytywanie obserwacji…</p>;
  if (!observations.length) return <p className="empty">Brak obserwacji.</p>;
  return <div className="table-scroll">
    <table>
      <thead><tr>
        <th scope="col">Czas klatki (UTC)</th>
        <th scope="col">Kamera</th>
        <th scope="col">Obiekt</th>
        <th scope="col">Pewność detekcji</th>
        <th scope="col">Źródło</th>
        <th scope="col">Dopasowanie</th>
      </tr></thead>
      <tbody>
        {Array.from(new Map(observations.map((item) => [item.observation_id, item])).values(), (item) => (
          <tr key={item.observation_id} className={selected === item.observation_id ? 'selected' : ''}>
            <td><button className="text-button" aria-label={`Otwórz obserwację ${item.observation_id}`}
              aria-pressed={selected === item.observation_id} onClick={() => open(item)}>
              {timestamp(item.captured_at)}
            </button></td>
            <td>{cameraName(item.camera_id)}{item.track_id && <code className="track-id">{item.track_id}</code>}</td>
            <td>{objectLabel[item.object_type]}</td>
            <td>{Math.round(item.confidence * 100)}%</td>
            <td><span className={`badge ${item.mode}`}>{item.mode.toUpperCase()}</span>
              {item.match.synthetic && <small>Syntetyczne</small>}
            </td>
            <td><MatchBadge match={item.match} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>;
}

export function ObservationDetails({ observation, error, close }: {
  observation: ObservationDetail; error?: string; close: () => void;
}) {
  const { match } = observation;
  return <section className="card details" aria-labelledby="detail-title">
    <div className="card-top">
      <h2 id="detail-title">Szczegóły obserwacji</h2>
      <button onClick={close}>Zamknij</button>
    </div>
    {error && <p role="alert" className="error-text">
      Szczegóły mogą być nieaktualne. Nie udało się ich odświeżyć ({error}).
    </p>}
    {observation.timing?.warning && <p className="error-text">
      Różnica odbiór − klatka: {metric(observation.timing.receipt_minus_capture_seconds, 's')}.
      Sprawdź zegary i opóźnienie transmisji.
    </p>}
    <div className="label-row">
      <span className={`badge ${observation.mode}`}>{observation.mode.toUpperCase()}</span>
      <MatchBadge match={match} />
      {match.synthetic && <span className="badge synthetic">Dane syntetyczne</span>}
    </div>
    <dl className="detail-facts">
      <div><dt>Identyfikator</dt><dd><code>{observation.observation_id}</code></dd></div>
      <div><dt>Kamera</dt><dd>{cameraName(observation.camera_id)}</dd></div>
      <div><dt>Klatka (UTC)</dt><dd>{timestamp(observation.captured_at)}</dd></div>
      <div><dt>Odbiór (UTC)</dt><dd>{timestamp(observation.received_at)}</dd></div>
      <div><dt>Klasa obiektu</dt><dd>{objectLabel[observation.object_type]}</dd></div>
      <div><dt>Pewność detekcji</dt><dd>{Math.round(observation.confidence * 100)}%</dd></div>
      <div><dt>Identyfikator ścieżki</dt><dd>{observation.track_id ?? '—'}</dd></div>
      <div><dt>Scenariusz</dt><dd>{observation.scenario_id ?? '—'}</dd></div>
      <div><dt>Ramka [x, y, szer., wys.]</dt><dd>{observation.bbox.map((value) => value.toFixed(3)).join(', ')}</dd></div>
    </dl>
    <h3>Potencjalne dopasowania</h3>
    <p>{matchReason[match.reason] ?? matchLabel[match.status]}</p>
    {!!match.candidates.length && <p className="muted-text">Potwierdzenie tożsamości wymaga danych o polu widzenia kamery.</p>}
    <div className="candidate-list">
      {match.candidates.map(({ aircraft, distance_km, time_delta_seconds, snapshot_at }) => (
        <article className="candidate" key={aircraft.address}>
          <h4>{aircraft.callsign ?? aircraft.address}</h4>
          <p>{aircraft.address}{aircraft.aircraft_type && ` · ${aircraft.aircraft_type}`}</p>
          <dl className="detail-facts">
            <div><dt>Pozycja (UTC)</dt><dd>{timestamp(aircraft.position_at)}</dd></div>
            <div><dt>Snapshot (UTC)</dt><dd>{timestamp(snapshot_at)}</dd></div>
            <div><dt>Odległość</dt><dd>{metric(distance_km, 'km')}</dd></div>
            <div><dt>Różnica czasu</dt><dd>{metric(time_delta_seconds, 's')}</dd></div>
            <div><dt>Wysokość barometryczna</dt><dd>{metric(aircraft.altitude_baro_ft, 'ft')}</dd></div>
            <div><dt>Wysokość geometryczna</dt><dd>{metric(aircraft.altitude_geom_ft, 'ft')}</dd></div>
            <div><dt>Prędkość względem ziemi</dt><dd>{metric(aircraft.ground_speed_kt, 'kt')}</dd></div>
            <div><dt>Kąt drogi</dt><dd>{metric(aircraft.track_deg, '°')}</dd></div>
          </dl>
        </article>
      ))}
    </div>
  </section>;
}
