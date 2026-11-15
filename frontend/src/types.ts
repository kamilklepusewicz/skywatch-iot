export type Mode = 'live' | 'replay';

export interface Coordinates {
  latitude: number;
  longitude: number;
}

export interface Health {
  mqtt_connected: boolean;
  mqtt_subscribed: boolean;
  adsb_polling_enabled: boolean;
  adsb_last_error: string | null;
  timing: {
    poll_interval_seconds: number;
    match_window_seconds: number;
    max_position_age_seconds: number;
    clock_warning_seconds: number;
  };
  adsb_timing: {
    source_at: string;
    retrieved_at: string;
    retrieval_minus_source_seconds: number;
    warning: boolean;
  } | null;
}

export interface Camera {
  camera_id: string;
  online: boolean;
  mode: Mode | 'idle' | null;
  scenario_id: string | null;
  last_heartbeat_at: string | null;
  status_received_at: string | null;
  location: Coordinates | null;
  latest_command: CommandResult | null;
}

export interface Scenario {
  scenario_id: string;
  description: string;
  synthetic: boolean;
  cameras: Record<string, Coordinates | null>;
  origin: Coordinates | null;
  first_snapshot_at: string | null;
  last_snapshot_at: string | null;
}

export type CommandRequest =
  | { command: 'start_live' | 'stop' }
  | { command: 'start_replay'; scenario_id: string };

export interface CommandResult {
  command_id: string;
  command: CommandRequest['command'];
  camera_id: string;
  issued_at: string;
  deadline_at: string;
  scenario_id: string | null;
  status: 'pending' | 'delivery_uncertain' | 'accepted' | 'rejected' | 'timed_out' | 'publish_failed';
  late: boolean;
  ack: { accepted: boolean; reported_at: string; message: string | null } | null;
  ack_received_at: string | null;
}

export type MatchStatus = 'skipped' | 'unavailable' | 'stale' | 'none' | 'one' | 'multiple';

export interface MatchSummary {
  status: MatchStatus;
  reason: string;
  synthetic: boolean;
  candidate_count: number;
}

export interface Observation {
  observation_id: string;
  camera_id: string;
  captured_at: string;
  received_at: string;
  object_type: 'airplane' | 'bird' | 'unknown';
  confidence: number;
  bbox: [number, number, number, number];
  mode: Mode;
  scenario_id: string | null;
  track_id: string | null;
  match: MatchSummary;
}

export interface Aircraft extends Coordinates {
  address: string;
  callsign: string | null;
  aircraft_type: string | null;
  altitude_baro_ft: number | null;
  altitude_geom_ft: number | null;
  ground_speed_kt: number | null;
  track_deg: number | null;
  on_ground: boolean | null;
  position_age_seconds: number | null;
  position_at: string | null;
}

export interface Candidate {
  aircraft: Aircraft;
  distance_km: number;
  time_delta_seconds: number;
  snapshot_at: string;
}

export interface ObservationDetail extends Observation {
  match: MatchSummary & { candidates: Candidate[] };
  timing: { receipt_minus_capture_seconds: number; warning: boolean } | null;
}

export interface AircraftView {
  mode: Mode;
  scenario_id: string | null;
  status: 'available' | 'stale' | 'unavailable';
  synthetic: boolean;
  origin: Coordinates | null;
  snapshot: {
    source_at: string;
    retrieved_at: string | null;
    aircraft: Aircraft[];
    missing_positions: number;
  } | null;
}
