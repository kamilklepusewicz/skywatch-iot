from dataclasses import replace

from skywatch_agent.cameras import camera_device, list_cameras


def test_lists_camera_names_and_stable_paths_without_capture(tmp_path):
    devices = tmp_path / "sys"
    aliases = tmp_path / "by-id"
    aliases.mkdir()
    for index, name in ((2, "C270 HD WEBCAM"), (0, "Integrated Camera")):
        directory = devices / f"video{index}"
        directory.mkdir(parents=True)
        (directory / "name").write_text(name)
    stable = aliases / "usb-Logitech-video-index0"
    stable.symlink_to(devices / "video2")
    cameras = list_cameras(devices, aliases)
    assert [camera["index"] for camera in cameras] == [0, 2]
    assert cameras[1]["name"] == "C270 HD WEBCAM"
    assert cameras[1]["stable_paths"] == [str(stable)]


def test_live_device_accepts_usb_persistent_path_and_numeric_override(config):
    path = "/dev/v4l/by-id/usb-Logitech-video-index0"
    assert replace(config, live_device=path).live_device == path
    assert camera_device("2") == 2
    assert camera_device(path) == path
