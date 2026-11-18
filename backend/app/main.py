import asyncio
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated

from anyio import create_task_group
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import AwareDatetime, BaseModel, ValidationError

from .config import Settings
from .database import Store, command_at, sqlite_busy
from .matching import match
from .models import (
    AircraftView,
    Camera,
    CameraId,
    CommandRequest,
    CommandResult,
    Health,
    Mode,
    ObservationDetail,
    ObservationRow,
    Scenario,
)
from .mqtt import Broker
from .service import EventKind, Resource, Service


class Update(BaseModel):
    type: EventKind
    resources: list[Resource] | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = Store(config.db_path, busy_timeout_ms=0)
        broker = Broker(config)
        try:
            service = Service(config, store, broker)
            app.state.service = service
            if config.mqtt_enabled:
                broker.start()
            async with asyncio.TaskGroup() as group:
                tasks = [
                    group.create_task(service.process()),
                    group.create_task(service.poll_flights()),
                ]
                try:
                    yield
                finally:
                    for task in tasks:
                        task.cancel()
        finally:
            if config.mqtt_enabled:
                await asyncio.to_thread(broker.stop)
            store.close()

    app = FastAPI(title="SkyWatch IoT", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.web_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    def get_service(request: Request) -> Service:
        return request.app.state.service

    @app.get("/api/health")
    async def health(request: Request) -> Health:
        return get_service(request).health()

    @app.get("/api/cameras")
    async def cameras(request: Request) -> list[Camera]:
        service = get_service(request)
        return service.cameras(datetime.now(UTC))

    @app.get("/api/scenarios")
    async def scenarios(request: Request) -> list[Scenario]:
        return get_service(request).store.scenarios()

    @app.get("/api/observations")
    async def observations(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        mode: Mode | None = None,
        camera_id: CameraId | None = None,
        scenario_id: str | None = None,
        before: Annotated[str | None, Query(min_length=1)] = None,
    ) -> list[ObservationRow]:
        service = get_service(request)
        if before is not None:
            if offset:
                raise HTTPException(422, "Use before or offset")
            if not service.store.has_observation(before):
                raise HTTPException(404, "Observation cursor not found")
        return [
            ObservationRow(
                **item.model_dump(),
                match=match(service.store, config, item).summary(),
            )
            for item in service.store.observations(
                limit, offset, mode, camera_id, scenario_id, before
            )
        ]

    @app.get("/api/observations/{observation_id:path}")
    async def observation(request: Request, observation_id: str) -> ObservationDetail:
        service = get_service(request)
        try:
            item = service.store.observation(observation_id)
        except ValidationError as exc:
            raise HTTPException(409, "Stored observation has invalid metadata") from exc
        if item is None:
            raise HTTPException(404, "Observation not found")
        return ObservationDetail(
            **item.model_dump(),
            match=match(service.store, config, item),
            timing=service.observation_timing(item),
        )

    @app.get("/api/aircraft")
    async def aircraft(
        request: Request,
        mode: Mode = "live",
        scenario_id: str | None = None,
        at: AwareDatetime | None = None,
    ) -> AircraftView:
        if (mode == "replay") != bool(scenario_id):
            raise HTTPException(422, "Provide scenario_id for replay only")
        return get_service(request).aircraft(mode, scenario_id, at)

    @app.post("/api/cameras/{camera_id}/commands", status_code=202)
    async def issue_command(
        request: Request, camera_id: CameraId, body: CommandRequest
    ) -> CommandResult:
        origin = request.headers.get("origin")
        if origin and origin not in config.web_origins:
            raise HTTPException(403, "Origin is not allowed")
        service = get_service(request)
        if camera_id not in set(config.camera_ids) | set(service.store.camera_ids()):
            raise HTTPException(404, "Camera not found")
        if body.scenario_id:
            scenario = service.store.scenario(body.scenario_id)
            if scenario is None or (scenario.cameras and camera_id not in scenario.cameras):
                raise HTTPException(422, "Replay scenario is not registered for this camera")
        try:
            return service.issue(camera_id, body, datetime.now(UTC))
        except sqlite3.Error as exc:
            if not sqlite_busy(exc):
                raise
            raise HTTPException(503, "Database is busy. Command was not submitted.") from exc

    @app.get("/api/commands/{command_id}")
    async def command(request: Request, command_id: str) -> CommandResult:
        service = get_service(request)
        result = command_at(service.store.command(command_id), datetime.now(UTC))
        if result is None:
            raise HTTPException(404, "Command not found")
        return result

    @app.websocket("/ws")
    async def updates(socket: WebSocket) -> None:
        origin = socket.headers.get("origin")
        if origin and origin not in config.web_origins:
            await socket.close(code=1008)
            return
        service: Service = socket.app.state.service
        listener: asyncio.Queue[set[Resource]] = asyncio.Queue(maxsize=1)
        service.listeners.add(listener)
        try:
            await socket.accept()
            await socket.send_json(Update(type="ready").model_dump(exclude_none=True))
            async with create_task_group() as group:

                async def send_updates() -> None:
                    try:
                        while True:
                            try:
                                resources = await asyncio.wait_for(listener.get(), timeout=15)
                                update = Update(type="changed", resources=sorted(resources))
                            except TimeoutError:
                                update = Update(type="heartbeat")
                            await socket.send_json(update.model_dump(exclude_none=True))
                    except WebSocketDisconnect:
                        group.cancel_scope.cancel()

                group.start_soon(send_updates)
                async for _ in socket.iter_text():
                    continue
                group.cancel_scope.cancel()
        except WebSocketDisconnect:
            pass
        finally:
            service.listeners.discard(listener)

    return app


app = create_app()
