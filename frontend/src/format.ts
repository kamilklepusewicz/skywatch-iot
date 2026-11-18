import type { AircraftIdentifier, CommandResult, MatchStatus, MatchSummary } from './types';

const dateTime = new Intl.DateTimeFormat('pl-PL', {
  dateStyle: 'short', timeStyle: 'medium', timeZone: 'UTC',
});
const decimal = new Intl.NumberFormat('pl-PL', { maximumFractionDigits: 1 });

export const timestamp = (value: string | null) => value ? dateTime.format(new Date(value)) : '—';
export const metric = (value: number | null, unit: string) => value === null ? '—' : `${decimal.format(value)} ${unit}`;
export const cameraName = (id: string) => /^camera_\d+$/.test(id) ? `Kamera ${id.slice(7)}` : id;
export const aircraftIdentifier = (aircraft?: AircraftIdentifier | null) =>
  aircraft?.callsign?.trim() || aircraft?.address?.trim() || null;

export const objectLabel = { airplane: 'Samolot', bird: 'Ptak', unknown: 'Nieznany' };

export const matchLabel: Record<MatchStatus, string> = {
  skipped: 'Pominięto',
  unavailable: 'Brak danych ADS-B',
  stale: 'Dane poza oknem czasowym',
  none: 'Brak kandydatów',
  one: '1 kandydat ADS-B',
  multiple: 'Wielu kandydatów',
};

const shortMatchReason: Record<string, string> = {
  scenario_not_registered: 'Brak scenariusza REPLAY',
  camera_location_missing: 'Brak lokalizacji kamery',
  no_snapshot_near_frame: 'Migawki poza oknem czasowym',
  no_position_near_frame: 'Pozycje poza oknem czasowym',
  positions_missing: 'Niepełne pozycje ADS-B',
};

export function matchSummaryLabel(match: MatchSummary) {
  const identifier = aircraftIdentifier(match.leading_candidate);
  if (match.status === 'one' && identifier) return `Kandydat ADS-B: ${identifier}`;
  if (match.status === 'multiple') {
    const count = match.candidate_count > 1 ? `${match.candidate_count} kandydatów` : matchLabel.multiple;
    return identifier ? `${count} · pierwszy: ${identifier}` : count;
  }
  return shortMatchReason[match.reason] ?? matchLabel[match.status];
}

export const matchReason: Record<string, string> = {
  non_airplane: 'Dopasowanie ADS-B jest dostępne dla obserwacji samolotów.',
  scenario_not_registered: 'Brakuje zarejestrowanego scenariusza dla tej obserwacji.',
  camera_location_missing: 'Brakuje współrzędnych potrzebnych do filtrowania odległości.',
  no_snapshots: 'Brak snapshotów ADS-B dla tego źródła.',
  no_snapshot_near_frame: 'Brak snapshotu w pobliżu czasu klatki.',
  no_position_near_frame: 'Dostępne pozycje wykraczają poza okno czasowe lub limit wieku.',
  positions_missing: 'Odebrane rekordy nie mają wystarczających danych o pozycji i czasie.',
  no_aircraft_in_range: 'Brak pozycji samolotów spełniających kryteria czasu i odległości.',
  temporal_geographic: 'Kandydaci są uporządkowani według różnicy czasu, a następnie odległości.',
};

export const commandLabel: Record<CommandResult['status'], string> = {
  pending: 'Oczekuje na ACK',
  delivery_uncertain: 'Dostarczenie niepewne · oczekuje na ACK',
  accepted: 'Zaakceptowana',
  rejected: 'Odrzucona',
  timed_out: 'Brak ACK w terminie · wynik nieznany',
  publish_failed: 'Błąd publikacji MQTT',
};
