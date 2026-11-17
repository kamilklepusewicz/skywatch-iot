from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .models import CameraId, Coordinates

BACKEND = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", allow_inf_nan=False)

    database_path: Path | None = None
    database_url: str | None = None
    mqtt_enabled: bool = True
    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = Field(1883, ge=1, le=65535)
    mqtt_username: str = "skywatch"
    mqtt_password: SecretStr | None = None
    heartbeat_timeout_seconds: float = Field(45, gt=0)
    command_timeout_seconds: float = Field(15, gt=0)
    camera_ids: list[CameraId] = Field(default_factory=lambda: ["camera_1", "camera_2"])
    camera_locations: dict[CameraId, Coordinates] = Field(default_factory=dict)
    adsb_enabled: bool = True
    adsb_latitude: float | None = Field(None, ge=-90, le=90)
    adsb_longitude: float | None = Field(None, ge=-180, le=180)
    adsb_radius_nm: int = Field(30, ge=1, le=250)
    adsb_poll_seconds: float = Field(180, ge=5)
    adsb_timeout_seconds: float = Field(8, gt=0)
    adsb_api_key: SecretStr | None = None
    match_radius_km: float = Field(20, gt=0)
    clock_warning_seconds: float = Field(30, gt=0)
    match_window_seconds: float = Field(35, gt=0, le=600)
    adsb_max_position_age_seconds: float = Field(30, gt=0, le=300)
    adsb_live_retention_hours: int = Field(48, ge=1)
    web_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"],
    )

    @model_validator(mode="after")
    def validate_settings(self) -> "Settings":
        if (self.adsb_latitude is None) != (self.adsb_longitude is None):
            raise ValueError("Set both ADSB_LATITUDE and ADSB_LONGITUDE")
        if self.database_url is not None and not self.database_url.startswith("sqlite:///"):
            raise ValueError("DATABASE_URL must use sqlite:///")
        return self

    @property
    def poll_interval(self) -> float:
        return self.adsb_poll_seconds if self.adsb_api_key else max(180, self.adsb_poll_seconds)

    @property
    def db_path(self) -> Path:
        if self.database_path is not None:
            return self.database_path
        if self.database_url:
            return Path(self.database_url.removeprefix("sqlite:///"))
        return BACKEND / "skywatch.sqlite3"

    @property
    def origin(self) -> Coordinates | None:
        if self.adsb_latitude is None or self.adsb_longitude is None:
            return None
        return Coordinates(latitude=self.adsb_latitude, longitude=self.adsb_longitude)
