import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';

import { History } from './Observations';
import type { MatchSummary, Observation } from './types';

const observation: Observation = {
  observation_id: 'first', camera_id: 'camera_1', captured_at: '2026-01-02T12:00:00Z',
  received_at: '2026-01-02T12:00:00Z', object_type: 'airplane', confidence: 0.87,
  bbox: [0, 0, 0.2, 0.1], mode: 'live', scenario_id: null, track_id: null,
  match: { status: 'one', candidate_count: 1, reason: 'temporal_geographic', synthetic: false },
};

function renderMatch(match: Partial<MatchSummary>, fields?: Partial<Observation>) {
  render(<History observations={[{ ...observation, ...fields, match: { ...observation.match, ...match } }]}
    selected={null} open={() => {}} />);
}

afterEach(cleanup);

it('shows a single potential candidate by its trimmed callsign', () => {
  renderMatch({ leading_candidate: { callsign: ' RYR1234 ', address: 'abc123' } });
  expect(screen.getByText('Kandydat ADS-B: RYR1234')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Otwórz obserwację first' })).toBeTruthy();
});

it.each([null, '   '])('uses ICAO when the callsign is %j', (callsign) => {
  renderMatch({ leading_candidate: { callsign, address: 'abc123' } });
  expect(screen.getByText('Kandydat ADS-B: abc123')).toBeTruthy();
});

it('shows a candidate count and identifies the first aircraft when there are multiple candidates', () => {
  renderMatch({ status: 'multiple', candidate_count: 3,
    leading_candidate: { callsign: 'RYR1234', address: 'abc123' } });
  expect(screen.getByText('3 kandydatów · pierwszy: RYR1234')).toBeTruthy();
});

it.each([undefined, null, { callsign: '   ', address: '   ' }])(
  'keeps a candidate count when the identifier is unavailable (%j)', (leading_candidate) => {
    renderMatch({ leading_candidate });
    expect(screen.getByText('1 kandydat ADS-B')).toBeTruthy();
  },
);

it.each([
  ['unavailable', 'no_snapshots', 'Brak danych ADS-B'],
  ['unavailable', 'camera_location_missing', 'Brak lokalizacji kamery'],
  ['stale', 'no_position_near_frame', 'Pozycje poza oknem czasowym'],
  ['none', 'no_aircraft_in_range', 'Brak kandydatów'],
  ['skipped', 'non_airplane', 'Pominięto'],
] as const)('shows a distinct match state for %s (%s)', (status, reason, label) => {
  renderMatch({ status, reason, candidate_count: 0, leading_candidate: null });
  expect(screen.getByText(label)).toBeTruthy();
});

it('keeps the synthetic REPLAY marker next to a displayed candidate', () => {
  renderMatch({ synthetic: true, leading_candidate: { callsign: 'SYNTH01', address: 'abc123' } }, {
    mode: 'replay', scenario_id: 'fixture',
  });
  expect(screen.getByText('REPLAY')).toBeTruthy();
  expect(screen.getByText('Syntetyczne')).toBeTruthy();
  expect(screen.getByText('Kandydat ADS-B: SYNTH01')).toBeTruthy();
});
