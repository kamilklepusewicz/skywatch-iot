import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .models import Ack, CameraStatus, CommandResult, Mode, Scenario, Snapshot, StoredObservation

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY,
    camera_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    scenario_id TEXT,
    received REAL NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS observations_received ON observations(received DESC, id DESC);
CREATE TABLE IF NOT EXISTS camera_status (
    camera_id TEXT PRIMARY KEY,
    received REAL NOT NULL,
    heartbeat REAL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS commands (
    id TEXT PRIMARY KEY,
    camera_id TEXT NOT NULL,
    issued REAL NOT NULL,
    deadline REAL NOT NULL,
    status TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS camera_commands ON commands(camera_id, issued DESC);
CREATE INDEX IF NOT EXISTS command_deadline ON commands(status, deadline);
CREATE TABLE IF NOT EXISTS scenarios (
    id TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
    scenario_key TEXT NOT NULL,
    source REAL NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (scenario_key, source)
);
"""


def sqlite_busy(exc: sqlite3.Error) -> bool:
    return getattr(exc, "sqlite_errorcode", 0) & 0xFF in (
        sqlite3.SQLITE_BUSY,
        sqlite3.SQLITE_LOCKED,
    )


def command_at(result: CommandResult | None, now: datetime) -> CommandResult | None:
    if result and result.status in ("pending", "delivery_uncertain") and result.deadline_at <= now:
        return result.model_copy(update={"status": "timed_out"})
    return result


class Store:
    """The application event loop owns this connection. MQTT callbacks only enqueue."""

    def __init__(self, path: Path, *, busy_timeout_ms: int = 2000) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=2)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        self.db.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")

    def close(self) -> None:
        self.db.close()

    def add_observation(self, item: StoredObservation) -> bool:
        with self.db:
            result = self.db.execute(
                """INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO NOTHING""",
                (
                    item.observation_id,
                    item.camera_id,
                    item.mode,
                    item.scenario_id,
                    item.received_at.timestamp(),
                    item.model_dump_json(),
                ),
            )
        return result.rowcount == 1

    def observations(
        self,
        limit: int,
        offset: int,
        mode: Mode | None,
        camera_id: str | None,
        scenario_id: str | None,
        before: str | None = None,
    ) -> list[StoredObservation]:
        args: list[str | int] = []
        # Older producers could serialize non-finite bbox values as null.
        clauses = [f"json_type(payload, '$.bbox[{index}]') IS NOT 'null'" for index in range(4)]
        if before is not None:
            clauses.append("(received, id) < (SELECT received, id FROM observations WHERE id=?)")
            args.append(before)
        for column, value in (
            ("mode", mode),
            ("camera_id", camera_id),
            ("scenario_id", scenario_id),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                args.append(value)
        where = " AND ".join(clauses)
        rows = self.db.execute(
            f"""SELECT payload FROM observations WHERE {where}
                ORDER BY received DESC, id DESC LIMIT ? OFFSET ?""",
            (*args, limit, offset),
        )
        return [StoredObservation.model_validate_json(row["payload"]) for row in rows]

    def has_observation(self, item_id: str) -> bool:
        row = self.db.execute("SELECT 1 FROM observations WHERE id = ?", (item_id,)).fetchone()
        return row is not None

    def observation(self, item_id: str) -> StoredObservation | None:
        row = self.db.execute(
            "SELECT payload FROM observations WHERE id = ?", (item_id,)
        ).fetchone()
        return StoredObservation.model_validate_json(row["payload"]) if row else None

    def camera_ids(self) -> list[str]:
        rows = self.db.execute(
            "SELECT camera_id FROM camera_status UNION SELECT DISTINCT camera_id FROM observations"
        )
        return [row[0] for row in rows]

    def camera_status(
        self, camera_id: str
    ) -> tuple[CameraStatus, datetime, datetime | None] | None:
        row = self.db.execute(
            "SELECT * FROM camera_status WHERE camera_id = ?", (camera_id,)
        ).fetchone()
        if row is None:
            return None
        heartbeat = row["heartbeat"]
        return (
            CameraStatus.model_validate_json(row["payload"]),
            datetime.fromtimestamp(row["received"], UTC),
            datetime.fromtimestamp(heartbeat, UTC) if heartbeat is not None else None,
        )

    def save_status(
        self,
        status: CameraStatus,
        received: datetime,
        heartbeat: datetime | None,
    ) -> None:
        with self.db:
            self.db.execute(
                """INSERT INTO camera_status VALUES (?, ?, ?, ?)
                   ON CONFLICT(camera_id) DO UPDATE SET received=excluded.received,
                   heartbeat=excluded.heartbeat, payload=excluded.payload""",
                (
                    status.camera_id,
                    received.timestamp(),
                    heartbeat.timestamp() if heartbeat else None,
                    status.model_dump_json(),
                ),
            )

    def save_command(self, result: CommandResult) -> None:
        with self.db:
            self.db.execute(
                """INSERT INTO commands VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                   status=excluded.status, payload=excluded.payload""",
                (
                    result.command_id,
                    result.camera_id,
                    result.issued_at.timestamp(),
                    result.deadline_at.timestamp(),
                    result.status,
                    result.model_dump_json(),
                ),
            )

    def command(self, command_id: str) -> CommandResult | None:
        row = self.db.execute("SELECT payload FROM commands WHERE id = ?", (command_id,)).fetchone()
        return CommandResult.model_validate_json(row["payload"]) if row else None

    def latest_command(self, camera_id: str) -> CommandResult | None:
        row = self.db.execute(
            "SELECT payload FROM commands WHERE camera_id = ? ORDER BY issued DESC LIMIT 1",
            (camera_id,),
        ).fetchone()
        return CommandResult.model_validate_json(row["payload"]) if row else None

    def acknowledge(self, ack: Ack, received: datetime) -> bool:
        result = self.command(ack.command_id)
        if result is None or result.camera_id != ack.camera_id or result.ack is not None:
            return False
        self.save_command(
            result.model_copy(
                update={
                    "status": "accepted" if ack.accepted else "rejected",
                    "ack": ack,
                    "ack_received_at": received,
                    "late": received >= result.deadline_at,
                }
            )
        )
        return True

    def expire_commands(self, now: datetime) -> bool:
        due = "status IN ('pending', 'delivery_uncertain') AND deadline <= ?"
        params = (now.timestamp(),)
        if (
            self.db.execute(f"SELECT 1 FROM commands WHERE {due} LIMIT 1", params).fetchone()
            is None
        ):
            return False
        with self.db:
            result = self.db.execute(
                f"""UPDATE commands SET status='timed_out',
                    payload=json_set(payload, '$.status', 'timed_out') WHERE {due}""",
                params,
            )
        return result.rowcount > 0

    def scenarios(self) -> list[Scenario]:
        rows = self.db.execute("SELECT payload FROM scenarios ORDER BY id")
        return [Scenario.model_validate_json(row[0]) for row in rows]

    def scenario(self, scenario_id: str) -> Scenario | None:
        row = self.db.execute(
            "SELECT payload FROM scenarios WHERE id = ?", (scenario_id,)
        ).fetchone()
        return Scenario.model_validate_json(row[0]) if row else None

    def import_scenario(self, scenario: Scenario, snapshots: list[Snapshot]) -> None:
        times = [snapshot.source_at for snapshot in snapshots]
        if any(snapshot.scenario_id != scenario.scenario_id for snapshot in snapshots):
            raise ValueError("All snapshots must belong to the imported scenario")
        if len(set(times)) != len(times):
            raise ValueError("Duplicate snapshot timestamps in scenario")
        metadata = scenario.model_copy(
            update={
                "first_snapshot_at": min(times, default=None),
                "last_snapshot_at": max(times, default=None),
            }
        )
        with self.db:
            self.db.execute(
                """INSERT INTO scenarios VALUES (?, ?)
                   ON CONFLICT(id) DO UPDATE SET payload=excluded.payload""",
                (metadata.scenario_id, metadata.model_dump_json()),
            )
            self.db.execute("DELETE FROM snapshots WHERE scenario_key = ?", (metadata.scenario_id,))
            self.db.executemany(
                "INSERT INTO snapshots VALUES (?, ?, ?)",
                (
                    (metadata.scenario_id, item.source_at.timestamp(), item.model_dump_json())
                    for item in snapshots
                ),
            )

    def save_snapshot(self, item: Snapshot, keep_since: datetime | None = None) -> None:
        if item.scenario_id is not None:
            raise ValueError("Import historical snapshots with their scenario")
        with self.db:
            self.db.execute(
                """INSERT INTO snapshots VALUES ('', ?, ?)
                   ON CONFLICT(scenario_key, source) DO UPDATE SET payload=excluded.payload""",
                (item.source_at.timestamp(), item.model_dump_json()),
            )
            if keep_since is not None:
                self.db.execute(
                    "DELETE FROM snapshots WHERE scenario_key='' AND source < ?",
                    (keep_since.timestamp(),),
                )

    def snapshots_between(self, key: str, start: float, end: float) -> list[Snapshot]:
        return [
            Snapshot.model_validate_json(row[0])
            for row in self.db.execute(
                """SELECT payload FROM snapshots WHERE scenario_key=? AND source BETWEEN ? AND ?
                   ORDER BY source""",
                (key, start, end),
            )
        ]

    def has_snapshots(self, key: str) -> bool:
        return (
            self.db.execute(
                "SELECT 1 FROM snapshots WHERE scenario_key=? LIMIT 1",
                (key,),
            ).fetchone()
            is not None
        )

    def live_source_timestamp(self) -> float | None:
        row = self.db.execute(
            "SELECT source FROM snapshots WHERE scenario_key='' ORDER BY source DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None

    def nearest_snapshot(self, key: str, at: datetime | None) -> Snapshot | None:
        if at is None:
            row = self.db.execute(
                "SELECT payload FROM snapshots WHERE scenario_key=? ORDER BY source DESC LIMIT 1",
                (key,),
            ).fetchone()
        else:
            timestamp = at.timestamp()
            rows = [
                self.db.execute(
                    f"""SELECT source, payload FROM snapshots WHERE scenario_key=? AND source {op} ?
                        ORDER BY source {order} LIMIT 1""",
                    (key, timestamp),
                ).fetchone()
                for op, order in (("<=", "DESC"), (">", "ASC"))
            ]
            row = min(
                (row for row in rows if row is not None),
                key=lambda row: abs(row["source"] - timestamp),
                default=None,
            )
        return Snapshot.model_validate_json(row["payload"]) if row else None
