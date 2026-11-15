import type { CommandResult, MatchStatus } from './types';

const dateTime = new Intl.DateTimeFormat('pl-PL', {
  dateStyle: 'short', timeStyle: 'medium', timeZone: 'UTC',
});
const decimal = new Intl.NumberFormat('pl-PL', { maximumFractionDigits: 1 });

export const timestamp = (value: string | null) => value ? dateTime.format(new Date(value)) : '—';
export const metric = (value: number | null, unit: string) => value === null ? '—' : `${decimal.format(value)} ${unit}`;
export const cameraName = (id: string) => /^camera_\d+$/.test(id) ? `Kamera ${id.slice(7)}` : id;

export const objectLabel = { airplane: 'Samolot', bird: 'Ptak', unknown: 'Nieznany' };

export const matchLabel: Record<MatchStatus, string> = {
  skipped: 'Pominięto',
  unavailable: 'Brak danych',
  stale: 'Dane poza oknem',
  none: 'Brak kandydatów',
  one: '1 kandydat',
  multiple: 'Wielu kandydatów',
};

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
