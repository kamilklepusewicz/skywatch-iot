"""Run in a separate export environment; runtime needs only OpenCV and the ONNX file."""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Download official YOLO11 and export CPU ONNX")
    parser.add_argument(
        "--directory", type=Path, default=Path(__file__).resolve().parents[1] / "models"
    )
    parser.add_argument("--model", choices=("yolo11n.pt", "yolo11s.pt"), default="yolo11n.pt")
    parser.add_argument("--image-size", type=int, default=640)
    args = parser.parse_args()
    from ultralytics import YOLO

    args.directory.mkdir(parents=True, exist_ok=True)
    model = YOLO(str(args.directory.resolve() / args.model))
    path = model.export(
        format="onnx",
        imgsz=args.image_size,
        opset=12,
        simplify=True,
        dynamic=False,
        nms=False,
        batch=1,
        device="cpu",
    )
    print(f"Set detector.model to: {path}")


if __name__ == "__main__":
    main()
