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
let status: Omit<typeof live, 'error'> & { error: string | null };
let unavailable: boolean;

beforeEach(() => {
  vi.useFakeTimers();
  status = { ...live };
  unavailable = false;
  vi.stubGlobal('fetch', vi.fn(async () => unavailable
    ? Response.json({}, { status: 503 }) : Response.json(status)));
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

async function poll() {
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
}

it('shows LIVE and REPLAY in the card and removes the image immediately after STOP', async () => {
  const view = render(<CameraPreview camera={camera} />);
  await poll();
  expect(screen.getByRole('img').getAttribute('src')).toContain('/preview/camera_1/stream.mjpg');
  expect(screen.getByText('640 × 480')).toBeTruthy();
  expect(screen.getByText('LIVE')).toBeTruthy();
  status = { ...live, mode: 'replay' };
  view.rerender(<CameraPreview camera={{ ...camera, mode: 'replay' }} />);
  await poll();
  expect(screen.getByText('REPLAY')).toBeTruthy();
  // Hide even before the separate preview poll catches up to the STOP command.
  view.rerender(<CameraPreview camera={{ ...camera, mode: 'idle' }} />);
  expect(screen.queryByRole('img')).toBeNull();
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
  await poll();
  expect(screen.getByRole('img')).toBeTruthy();
});

it('does not show another camera feed or an offline camera as live', async () => {
  status = { ...live, camera_id: 'camera_2' };
  const view = render(<CameraPreview camera={camera} />);
  await poll();
  expect(screen.queryByRole('img')).toBeNull();
  status = { ...live };
  await poll();
  expect(screen.getByRole('img')).toBeTruthy();
  view.rerender(<CameraPreview camera={{ ...camera, online: false }} />);
  expect(screen.queryByRole('img')).toBeNull();
  expect(screen.getByRole('status').textContent).toContain('Kamera offline');
});

it('reconnects a failed image stream while the status endpoint remains available', async () => {
  render(<CameraPreview camera={camera} />);
  await poll();
  const previous = screen.getByRole('img').getAttribute('src');
  fireEvent.error(screen.getByRole('img'));
  expect(screen.queryByRole('img')).toBeNull();
  expect(screen.getByRole('status').textContent).toContain('Ponawiam połączenie');
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  expect(screen.getByRole('img').getAttribute('src')).not.toBe(previous);
});
