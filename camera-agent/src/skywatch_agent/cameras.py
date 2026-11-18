"""Discover Linux video devices without opening a camera."""

from pathlib import Path


def camera_device(value: str) -> int | str:
    return int(value) if value.isdecimal() else value


def list_cameras(sys_root=Path("/sys/class/video4linux"), by_id=Path("/dev/v4l/by-id")):
    aliases = {}
    for path in sorted(by_id.glob("*")):
        aliases.setdefault(path.resolve().name, []).append(str(path))
    result = []
    for path in sorted(sys_root.glob("video*"), key=lambda p: int(p.name.removeprefix("video"))):
        result.append(
            {
                "index": int(path.name.removeprefix("video")),
                "device": f"/dev/{path.name}",
                "name": (path / "name").read_text().strip(),
                "stable_paths": aliases.get(path.name, []),
            }
        )
    return result
