import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import { CameraPreview } from './CameraPreview';
import type { Camera } from './types';

const camera: Camera = {
  camera_id: 'camera_1', online: true, mode: 'live', scenario_id: null,
  last_heartbeat_at: null, status_received_at: null, latest_command: null, location: null,
};
const live = {
  camera_id: 'camera_1', mode: 'live', scenario_id: null, captured_at: '2026-11-18T18:00:00Z',
  width: 640, height: 480, frame_age_seconds: 0.1, detector: 'motion', error: null,
};
const secondLive = { ...live, camera_id: 'camera_2', width: 1280, height: 720 };
let status: Omit<typeof live, 'captured_at' | 'error'> & { captured_at: string | null; error: string | null };
let unavailable: boolean;

beforeEach(() => {
  vi.useFakeTimers();
  status = { ...live };
  unavailable = false;
  vi.stubGlobal('fetch', vi.fn(async (url: string) => unavailable
    ? Response.json({}, { status: 503 })
    : Response.json(url === '/preview/camera_2/status.json' ? secondLive : status)));
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

async function poll(ms = 1000) {
  await act(async () => { await vi.advanceTimersByTimeAsync(ms); });
}

function loadFrame() {
  const image = screen.getByAltText(/Podgląd obrazu/);
  fireEvent.load(image);
  return image;
}

it('uses separate preview routes and displays each feed after a frame arrives', async () => {
  render(<>
    <CameraPreview camera={camera} />
    <CameraPreview camera={{ ...camera, camera_id: 'camera_2' }} />
  </>);
  await poll();
  const first = screen.getByAltText(/Podgląd obrazu.*Kamera 1/);
  const second = screen.getByAltText(/Podgląd obrazu.*Kamera 2/);
  expect(first.getAttribute('src')).toContain('/preview/camera_1/stream.mjpg');
  expect(second.getAttribute('src')).toContain('/preview/camera_2/stream.mjpg');
  expect(screen.queryAllByRole('img')).toHaveLength(0);
  expect(screen.getAllByRole('status')).toHaveLength(2);
  fireEvent.load(first);
  expect(screen.getByRole('img')).toBe(first);
  fireEvent.load(second);
  expect(screen.getAllByRole('img')).toHaveLength(2);
  expect(screen.getByText('1280 × 720')).toBeTruthy();
});

it('shows the stopped and offline states without polling an unavailable preview', async () => {
  unavailable = true;
  const view = render(<CameraPreview camera={camera} />);
  await poll();
  expect(screen.getByRole('status').textContent).toContain('Podgląd niedostępny');

  view.rerender(<CameraPreview camera={{ ...camera, mode: 'idle' }} />);
  expect(screen.getByRole('status').textContent).toContain('Kamera zatrzymana');
  const requests = vi.mocked(fetch).mock.calls.length;
  await poll(30_000);
  expect(vi.mocked(fetch)).toHaveBeenCalledTimes(requests);

  view.rerender(<CameraPreview camera={{ ...camera, online: false }} />);
  expect(screen.getByRole('status').textContent).toContain('Kamera offline');
  await poll(30_000);
  expect(vi.mocked(fetch)).toHaveBeenCalledTimes(requests);
});

it('backs off status polling during an outage and resumes when the preview responds', async () => {
  unavailable = true;
  render(<CameraPreview camera={camera} />);
  await poll(5000);
  expect(vi.mocked(fetch).mock.calls.length).toBeLessThan(4);

  unavailable = false;
  await poll(15_000);
  expect(screen.getByAltText(/Podgląd obrazu/)).toBeTruthy();
});

it('shows LIVE and REPLAY in the card and removes the image immediately after STOP', async () => {
  const view = render(<CameraPreview camera={camera} />);
  await poll();
  const image = loadFrame();
  expect(image.getAttribute('src')).toContain('/preview/camera_1/stream.mjpg');
  expect(screen.getByText('640 × 480')).toBeTruthy();
  expect(screen.getByText('LIVE')).toBeTruthy();
  status = { ...live, mode: 'replay' };
  view.rerender(<CameraPreview camera={{ ...camera, mode: 'replay' }} />);
  await poll();
  expect(screen.getByText('REPLAY')).toBeTruthy();
  // Hide even before the separate preview poll catches up to the STOP command.
  view.rerender(<CameraPreview camera={{ ...camera, mode: 'idle' }} />);
  expect(screen.queryByAltText(/Podgląd obrazu/)).toBeNull();
  expect(image.getAttribute('src')).toBeNull();
  expect(screen.getByRole('status').textContent).toContain('Kamera zatrzymana');
});

it('hides stale frames and camera errors, and recovers after a temporary outage', async () => {
  render(<CameraPreview camera={camera} />);
  await poll();
  status = { ...live, frame_age_seconds: 6 };
  await poll();
  expect(screen.queryByRole('img')).toBeNull();
  expect(screen.getByRole('status').textContent).toContain('Brak nowych klatek');
  status = { ...live, error: 'Camera disconnected' };
  await poll();
  expect(screen.getByRole('status').textContent).toContain('Camera disconnected');
  unavailable = true;
  await poll();
  expect(screen.queryByRole('img')).toBeNull();
  expect(screen.getByRole('status').textContent).toContain('Podgląd niedostępny');
  unavailable = false;
  status = { ...live };
  await poll(2000);
  const recovered = loadFrame();
  expect(screen.getByRole('img')).toBe(recovered);
});

it('shows the preview error after a failed capture returns the camera to idle', async () => {
  const view = render(<CameraPreview camera={camera} />);
  await poll();
  loadFrame();

  status = { ...live, mode: 'idle', captured_at: null, error: 'Camera disconnected' };
  view.rerender(<CameraPreview camera={{ ...camera, mode: 'idle' }} />);
  expect(screen.queryByAltText(/Podgląd obrazu/)).toBeNull();
  await poll();
  expect(screen.getByRole('status').textContent).toContain('Camera disconnected');
});

it('does not show another camera feed or an offline camera as live', async () => {
  status = { ...live, camera_id: 'camera_2' };
  const view = render(<CameraPreview camera={camera} />);
  await poll();
  expect(screen.queryByRole('img')).toBeNull();
  status = { ...live };
  await poll();
  const image = loadFrame();
  expect(screen.getByRole('img')).toBe(image);
  view.rerender(<CameraPreview camera={{ ...camera, online: false }} />);
  expect(screen.queryByAltText(/Podgląd obrazu/)).toBeNull();
  expect(image.getAttribute('src')).toBeNull();
  expect(screen.getByRole('status').textContent).toContain('Kamera offline');
});

it('reconnects a failed image stream while the status endpoint remains available', async () => {
  render(<CameraPreview camera={camera} />);
  await poll();
  const image = screen.getByAltText(/Podgląd obrazu/);
  const previous = image.getAttribute('src');
  fireEvent.error(image);
  expect(screen.queryByAltText(/Podgląd obrazu/)).toBeNull();
  expect(screen.getByRole('status').textContent).toContain('Ponawiam połączenie');
  await poll(2000);
  const retry = screen.getByAltText(/Podgląd obrazu/);
  expect(retry.getAttribute('src')).not.toBe(previous);
  fireEvent.error(retry);
  await poll(2000);
  expect(screen.getByRole('status').textContent).toContain('Ponawiam połączenie');
  await poll(2000);
  const recovered = loadFrame();
  expect(screen.getByRole('img')).toBe(recovered);
});
