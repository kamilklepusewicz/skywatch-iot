import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { App } from './App';
import type { Camera, CommandResult, ObservationDetail } from './types';

const time = '2026-01-02T12:00:00Z';
const camera: Camera = {
  camera_id: 'camera_1', online: true, mode: 'live', scenario_id: null,
  last_heartbeat_at: time, status_received_at: time, latest_command: null, location: null,
};
const observation: ObservationDetail = {
  observation_id: 'first', camera_id: camera.camera_id, captured_at: time, received_at: time,
  object_type: 'airplane', bbox: [0, 0, 0.2, 0.1], track_id: 'track-123',
  confidence: 0.87, mode: 'replay', scenario_id: 'fixture',
  timing: null,
  match: { status: 'one', reason: 'temporal_geographic', synthetic: true, candidate_count: 1,
    candidates: [{
      aircraft: {
        address: 'abc123', callsign: 'SYNTH01', aircraft_type: 'C172', latitude: 52, longitude: 21,
        altitude_baro_ft: 2000, altitude_geom_ft: 2300, ground_speed_kt: 95, track_deg: 10,
        position_at: time, position_age_seconds: 0, on_ground: false,
      },
      snapshot_at: time, time_delta_seconds: 0, distance_km: 3,
    }],
  },
};

const command: CommandResult = {
  command_id: 'cmd-1', command: 'start_replay', camera_id: 'camera_1', issued_at: time,
  deadline_at: time, scenario_id: 'fixture', status: 'pending', late: false,
  ack_received_at: null, ack: null,
};

class TestSocket extends EventTarget {
  static latest: TestSocket;
  constructor() {
    super();
    TestSocket.latest = this;
  }
  sendUpdate(type: string, resources?: string[]) {
    this.dispatchEvent(new MessageEvent('message', { data: JSON.stringify({ type, resources }) }));
  }
  close() {}
}

let cameras: Camera[];
let observations: ObservationDetail[];
let apiFailure: boolean;
let detailFailure: boolean;
let request: ReturnType<typeof vi.fn<typeof fetch>>;

beforeEach(() => {
  cameras = [camera, { ...camera, camera_id: 'camera_2', online: false, mode: null }];
  observations = [observation];
  apiFailure = false;
  detailFailure = false;
  request = vi.fn(async (input, init) => {
    const url = new URL(String(input), 'http://localhost');
    if (apiFailure) return Response.json({}, { status: 503 });
    switch (url.pathname) {
      case '/api/cameras':
        return Response.json(cameras);
      case '/api/health':
        return Response.json({ mqtt_connected: true, mqtt_subscribed: true, adsb_polling_enabled: false });
      case '/api/scenarios':
        return Response.json([{ scenario_id: 'fixture', description: 'Dane testowe', synthetic: true, cameras: {} }]);
      case '/api/aircraft':
        return Response.json({ mode: url.searchParams.get('mode') ?? 'live', status: 'unavailable',
          snapshot: null, origin: null, synthetic: false, scenario_id: null });
      case '/api/observations':
        return Response.json(url.searchParams.has('before') ? [] : observations);
      case '/api/observations/first':
        return detailFailure ? Response.json({}, { status: 503 }) : Response.json(observation);
      case '/api/cameras/camera_1/commands':
        expect(JSON.parse(String(init?.body))).toEqual({ command: 'start_replay', scenario_id: 'fixture' });
        cameras = [{ ...camera, latest_command: command }, ...cameras.slice(1)];
        return Response.json(command, { status: 202 });
      default:
        throw new Error(url.pathname);
    }
  });
  vi.stubGlobal('fetch', request);
  vi.stubGlobal('WebSocket', TestSocket);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('dashboard', () => {
  it('shows both camera states and opens synthetic candidate details', async () => {
    render(<App />);
    const first = await screen.findByRole('region', { name: 'Kamera 1' });
    const second = screen.getByRole('region', { name: 'Kamera 2' });
    expect(within(first).getByText('Online')).toBeTruthy();
    expect(within(second).getByText('Offline')).toBeTruthy();
    expect(await screen.findByText('87%')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Otwórz obserwację first' }));
    const detail = await screen.findByRole('region', { name: 'Szczegóły obserwacji' });
    expect(await within(detail).findByText('SYNTH01')).toBeTruthy();
    expect(within(detail).getByText('Dane syntetyczne')).toBeTruthy();
  });

  it('posts a replay command and refreshes its outcome after a socket event', async () => {
    render(<App />);
    const first = await screen.findByRole('region', { name: 'Kamera 1' });
    fireEvent.change(within(first).getByLabelText('Scenariusz REPLAY'), { target: { value: 'fixture' } });
    fireEvent.click(within(first).getByRole('button', { name: 'Uruchom REPLAY' }));
    expect(await within(first).findByText('Oczekuje na ACK')).toBeTruthy();
    cameras[0] = { ...camera, latest_command: { ...command, status: 'rejected' } };
    await act(async () => TestSocket.latest.sendUpdate('changed'));
    expect(await within(first).findByText('Odrzucona')).toBeTruthy();
  });

  it('recovers REST state on reconnect without duplicating observations', async () => {
    render(<App />);
    await screen.findByRole('button', { name: 'Otwórz obserwację first' });
    const oldSocket = TestSocket.latest;
    observations = [observation, observation];
    await act(async () => oldSocket.dispatchEvent(new CloseEvent('close')));
    expect(await screen.findByText('Ponowne łączenie')).toBeTruthy();
    await vi.waitFor(() => expect(TestSocket.latest).not.toBe(oldSocket), { timeout: 1800 });
    await act(async () => TestSocket.latest.sendUpdate('ready'));
    expect(await screen.findByText('Połączono')).toBeTruthy();
    expect(screen.getAllByRole('button', { name: 'Otwórz obserwację first' })).toHaveLength(1);
  });

  it('renders an empty history and exposes an API error with retry', async () => {
    observations = [];
    apiFailure = true;
    render(<App />);
    expect(await screen.findByText('Błąd pobierania danych: HTTP 503')).toBeTruthy();
    apiFailure = false;
    fireEvent.click(screen.getByRole('button', { name: 'Spróbuj ponownie' }));
    expect(await screen.findByText('Brak obserwacji.')).toBeTruthy();
  });
});


it('refreshes camera state on a heartbeat without reloading observations or ADS-B', async () => {
  render(<App />);
  await screen.findByRole('button', { name: 'Otwórz obserwację first' });
  request.mockClear();
  cameras[0] = { ...camera, online: false };
  await act(async () => TestSocket.latest.sendUpdate('changed', ['cameras']));
  const first = screen.getByRole('region', { name: 'Kamera 1' });
  expect(await within(first).findByText('Offline')).toBeTruthy();
  expect(request.mock.calls.map(([path]) => path)).toEqual(['/api/cameras']);
});

it('retains details with a visible error and excludes LIVE camera coordinates from REPLAY', async () => {
  cameras[0] = { ...camera, location: { latitude: 52, longitude: 21 } };
  render(<App />);
  fireEvent.click(await screen.findByRole('button', { name: 'Otwórz obserwację first' }));
  const map = screen.getByRole('region', { name: 'Mapa lotnicza' });
  await within(map).findByRole('button', { name: 'SYNTH01' });
  expect(within(map).queryByRole('button', { name: 'Kamera 1' })).toBeNull();
  detailFailure = true;
  await act(async () => TestSocket.latest.sendUpdate('changed', ['observations']));
  const detail = screen.getByRole('region', { name: 'Szczegóły obserwacji' });
  expect(await within(detail).findByRole('alert')).toBeTruthy();
  expect(within(detail).getByText('SYNTH01')).toBeTruthy();
});

it('uses the last observation as the next-page cursor and filters by scenario', async () => {
  observations = Array.from({ length: 31 }, (_, i) => ({ ...observation, observation_id: String(i) }));
  render(<App />);
  const scenario = await screen.findByLabelText('Filtr scenariusza');
  fireEvent.change(scenario, { target: { value: 'fixture' } });
  fireEvent.click(await screen.findByRole('button', { name: 'Starsze' }));
  expect(await screen.findByText('Brak obserwacji.')).toBeTruthy();
  expect(request.mock.calls.some(([path]) => {
    const url = new URL(String(path), 'http://localhost');
    return url.searchParams.get('before') === '29' && url.searchParams.get('scenario_id') === 'fixture';
  })).toBe(true);
});
