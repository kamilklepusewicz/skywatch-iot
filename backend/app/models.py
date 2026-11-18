from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

CameraId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]+$")]
ReplayId = Annotated[str, Field(min_length=1, pattern=r"\S")]
Mode = Literal["live", "replay"]
OperatingMode = Literal["idle", "live", "replay"]
CommandName = Literal["start_live", "start_replay", "stop"]
PublishStatus = Literal["pending", "delivery_uncertain", "publish_failed"]
UnitInterval = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
MatchStatus = Literal["skipped", "unavailable", "stale", "none", "one", "multiple"]
FeedState = Literal["unavailable", "stale", "available"]


class Coordinates(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class Observation(BaseModel):
    schema_version: Literal[1] = 1
    observation_id: str
    camera_id: CameraId
    captured_at: AwareDatetime
    object_type: Literal["airplane", "bird", "unknown"]
    confidence: UnitInterval
    bbox: tuple[UnitInterval, UnitInterval, UnitInterval, UnitInterval]
    mode: Mode
    scenario_id: str | None = None
    track_id: str | None = None


class StoredObservation(Observation):
    received_at: AwareDatetime


class CameraStatus(BaseModel):
    schema_version: Literal[1]
    camera_id: CameraId
    reported_at: AwareDatetime
    online: bool
    mode: OperatingMode
    scenario_id: str | None = None


class CommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: CommandName
    scenario_id: ReplayId | None = None

    @model_validator(mode="after")
    def check_scenario(self) -> "CommandRequest":
        if (self.command == "start_replay") != (self.scenario_id is not None):
            raise ValueError("Only start_replay requires a scenario_id")
        return self


class Command(CommandRequest):
    schema_version: Literal[1] = 1
    command_id: str
    camera_id: CameraId
    issued_at: AwareDatetime


class Ack(BaseModel):
    schema_version: Literal[1]
    command_id: str
    camera_id: CameraId
    reported_at: AwareDatetime
    accepted: bool
    message: str | None = None


class CommandResult(Command):
    status: PublishStatus | Literal["accepted", "rejected", "timed_out"]
    deadline_at: AwareDatetime
    ack: Ack | None = None
    ack_received_at: AwareDatetime | None = None
    late: bool = False


class Camera(BaseModel):
    camera_id: CameraId
    online: bool
    mode: OperatingMode | None = None
    scenario_id: str | None = None
    last_heartbeat_at: AwareDatetime | None = None
    status_received_at: AwareDatetime | None = None
    location: Coordinates | None = None
    latest_command: CommandResult | None = None


class Aircraft(Coordinates):
    address: str
    callsign: str | None = None
    aircraft_type: str | None = None
    altitude_baro_ft: float | None = None
    altitude_geom_ft: float | None = None
    ground_speed_kt: float | None = None
    track_deg: float | None = None
    on_ground: bool | None = None
    position_age_seconds: float | None = None
    position_at: AwareDatetime | None = None


class Snapshot(BaseModel):
    source_at: AwareDatetime
    retrieved_at: AwareDatetime | None
    scenario_id: str | None = None
    missing_positions: int = 0
    aircraft: list[Aircraft]


class Scenario(BaseModel):
    scenario_id: ReplayId
    description: str = ""
    synthetic: bool
    cameras: dict[CameraId, Coordinates | None] = Field(default_factory=dict)
    origin: Coordinates | None = None
    first_snapshot_at: AwareDatetime | None = None
    last_snapshot_at: AwareDatetime | None = None


class Candidate(BaseModel):
    aircraft: Aircraft
    distance_km: float
    time_delta_seconds: float
    snapshot_at: AwareDatetime


class AircraftIdentifier(BaseModel):
    address: str
    callsign: str | None = None


class MatchState(BaseModel):
    status: MatchStatus
    synthetic: bool = False
    reason: str
    candidate_count: int = 0


class MatchSummary(MatchState):
    leading_candidate: AircraftIdentifier | None = None


class Match(MatchState):
    candidates: list[Candidate] = Field(default_factory=list)

    def summary(self) -> MatchSummary:
        aircraft = self.candidates[0].aircraft if self.candidates else None
        return MatchSummary(
            **self.model_dump(exclude={"candidates"}),
            leading_candidate=(
                AircraftIdentifier(address=aircraft.address, callsign=aircraft.callsign)
                if aircraft is not None
                else None
            ),
        )


class ObservationRow(StoredObservation):
    match: MatchSummary


class ObservationTiming(BaseModel):
    receipt_minus_capture_seconds: float
    warning: bool


class ObservationDetail(StoredObservation):
    match: Match
    timing: ObservationTiming | None = None


class AircraftView(BaseModel):
    mode: Mode
    scenario_id: str | None
    synthetic: bool
    status: FeedState
    origin: Coordinates | None = None
    snapshot: Snapshot | None = None


class TimingSettings(BaseModel):
    poll_interval_seconds: float
    match_window_seconds: float
    max_position_age_seconds: float
    clock_warning_seconds: float


class AdsbTiming(BaseModel):
    source_at: AwareDatetime
    retrieved_at: AwareDatetime
    retrieval_minus_source_seconds: float
    warning: bool


class Health(BaseModel):
    mqtt_connected: bool
    mqtt_subscribed: bool
    adsb_polling_enabled: bool
    adsb_last_error: str | None = None
    timing: TimingSettings
    adsb_timing: AdsbTiming | None = None
