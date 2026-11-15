import { useState } from 'react';

import { api } from './api';
import { cameraName, commandLabel, timestamp } from './format';
import type { Camera, CommandRequest, CommandResult, Scenario } from './types';

const operation = { idle: 'Bezczynna', live: 'LIVE', replay: 'REPLAY' };
const actionName = { start_live: 'Uruchom LIVE', start_replay: 'Uruchom REPLAY', stop: 'Zatrzymaj' };

interface Props {
  camera: Camera;
  scenarios: Scenario[];
  brokerReady: boolean;
  refresh: () => void;
}

export function CameraCard({ camera, scenarios, brokerReady, refresh }: Props) {
  const [scenarioId, setScenarioId] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [issued, setIssued] = useState<CommandResult>();
  const available = scenarios.filter((item) =>
    Object.keys(item.cameras).length === 0 || Object.hasOwn(item.cameras, camera.camera_id),
  );
  const selected = available.find((item) => item.scenario_id === scenarioId);
  const saved = camera.latest_command;
  const command = saved && (!issued || Date.parse(saved.issued_at) >= Date.parse(issued.issued_at))
    ? saved : issued;
  const awaitingAck = command?.status === 'pending' || command?.status === 'delivery_uncertain';
  const locked = sending || !brokerReady || !camera.online || awaitingAck;

  async function send(body: CommandRequest) {
    setSending(true);
    setError('');
    try {
      const result = await api<CommandResult>(`/api/cameras/${encodeURIComponent(camera.camera_id)}/commands`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      setIssued(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Błąd wysyłania');
    } finally {
      refresh();
      setSending(false);
    }
  }

  return (
    <article className="card camera" aria-label={cameraName(camera.camera_id)} role="region">
      <div className="card-top">
        <div>
          <h3>{cameraName(camera.camera_id)}</h3>
          <code>{camera.camera_id}</code>
        </div>
        <span className={`badge ${camera.online ? 'good' : 'muted'}`}>
          <span className="dot" />{camera.online ? 'Online' : 'Offline'}
        </span>
      </div>
      <dl className="camera-facts">
        <div>
          <dt>{camera.online ? 'Tryb pracy' : 'Ostatni zgłoszony tryb'}</dt>
          <dd className={camera.mode === 'replay' ? 'replay-text' : ''}>
            {camera.mode ? operation[camera.mode] : '—'}{camera.scenario_id && ` · ${camera.scenario_id}`}
          </dd>
        </div>
        <div><dt>Ostatni heartbeat (UTC)</dt><dd>{timestamp(camera.last_heartbeat_at)}</dd></div>
      </dl>
      <div className="camera-actions">
        <label>
          Scenariusz REPLAY
          <select value={selected?.scenario_id ?? ''} onChange={(e) => setScenarioId(e.target.value)}>
            <option value="">{available.length ? 'Wybierz scenariusz' : 'Brak scenariuszy'}</option>
            {available.map((item) => <option key={item.scenario_id} value={item.scenario_id}>
              {item.scenario_id}{item.synthetic ? ' · syntetyczny' : ''}
            </option>)}
          </select>
        </label>
        {selected?.description && <p className="scenario-note">{selected.description}</p>}
        <div className="button-row">
          <button className="primary" disabled={locked} onClick={() => void send({ command: 'start_live' })}>Uruchom LIVE</button>
          <button className="replay-button" disabled={locked || !selected} onClick={() => {
            if (selected) void send({ command: 'start_replay', scenario_id: selected.scenario_id });
          }}>Uruchom REPLAY</button>
          <button disabled={locked} onClick={() => void send({ command: 'stop' })}>Zatrzymaj</button>
        </div>
      </div>
      <div className="command-result" aria-live="polite">
        {sending && <span>Wysyłanie polecenia…</span>}
        {error && <p className="error-text" role="alert">Błąd polecenia: {error}</p>}
        {!sending && command && <>
          <span>{actionName[command.command]} · </span>
          <strong className={`command-${command.status}`}>{commandLabel[command.status]}</strong>
          {command.late && <span> · spóźnione ACK</span>}
          {command.ack?.message && <p>{command.ack.message}</p>}
        </>}
      </div>
    </article>
  );
}
