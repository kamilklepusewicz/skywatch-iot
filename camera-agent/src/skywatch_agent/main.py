import argparse
import json
import logging
import signal
from collections import Counter
from pathlib import Path

from .agent import Agent
from .config import load_config
from .contracts import timestamp
from .demo import generate_demo
from .detector import make_detector
from .mqtt_client import MqttClient
from .pipeline import Pipeline
from .replay import load_scenarios
from .source import VideoSource

LOG = logging.getLogger(__name__)


def evaluate(config, scenarios, scenario_id, output, expectation):
    if scenario_id not in scenarios:
        raise ValueError(f"Unknown scenario_id: {scenario_id}")
    scenario = scenarios[scenario_id]
    if config.camera_id not in scenario.recordings:
        raise ValueError("Scenario has no recording for this camera_id")
    recording = scenario.recordings[config.camera_id]
    pipeline = Pipeline(
        config.camera_id,
        make_detector(config.detector),
        config.tracker,
        config.observation_interval,
    )
    source = VideoSource(recording=recording)
    frames = 0
    counts, tracks, samples = Counter(), set(), []
    first = last = None
    try:
        while (frame := source.read()) is not None:
            frames += 1
            first = first or frame.captured_at
            last = frame.captured_at
            for observation in pipeline.process(frame, "replay", scenario_id):
                counts[observation["object_type"]] += 1
                tracks.add(observation["track_id"])
                if len(samples) < 100:
                    samples.append(observation)
    finally:
        source.close()
    if frames == 0:
        raise ValueError("No frames decoded; cannot evaluate an empty/corrupt recording")
    passed = (
        (expectation == "empty" and not counts)
        or (expectation == "airplane" and counts["airplane"] > 0)
        or (expectation == "any" and bool(counts))
        or expectation is None
    )
    report = {
        "scenario_id": scenario_id,
        "camera_id": config.camera_id,
        "material": "SIMULATED" if scenario.synthetic else "REPLAY",
        "video": str(recording.path),
        "detector": config.detector.kind,
        "model": str(config.detector.model) if config.detector.model else None,
        "confidence_threshold": config.detector.confidence,
        "frames": frames,
        "first_captured_at": timestamp(first),
        "last_captured_at": timestamp(last),
        "observations_by_type": dict(counts),
        "track_count": len(tracks),
        "expectation": expectation,
        "passed": passed,
        "observation_samples": samples,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{report['material']}: {frames} frames, {dict(counts)}, report: {output}")
    return 0 if passed else 3


def main(argv=None):
    parser = argparse.ArgumentParser(description="SkyWatch camera-agent (Osoba 1)")
    parser.add_argument("--verbose", action="store_true")
    commands = parser.add_subparsers(dest="action", required=True)
    run = commands.add_parser("run", help="Connect to MQTT and handle camera commands")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--mode", choices=("idle", "live", "replay"), default="idle")
    run.add_argument("--scenario")
    evaluation = commands.add_parser("evaluate", help="Evaluate a local recording without MQTT")
    evaluation.add_argument("--config", type=Path, required=True)
    evaluation.add_argument("--scenario", required=True)
    evaluation.add_argument("--output", type=Path, required=True)
    evaluation.add_argument("--expect", choices=("airplane", "empty", "any"))
    demo = commands.add_parser("generate-demo", help="Generate explicitly synthetic MP4 fixtures")
    demo.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        if args.action == "generate-demo":
            print(generate_demo(args.directory))
            return 0
        config = load_config(args.config)
        scenarios = load_scenarios(config.scenario_files)
        if args.action == "evaluate":
            return evaluate(config, scenarios, args.scenario, args.output, args.expect)
        if args.mode == "replay" and not args.scenario:
            raise ValueError("--mode replay requires --scenario")
        agent = Agent(config, MqttClient(config.camera_id, config.mqtt), scenarios)
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, lambda *_: agent.shutdown.set())
        agent.run(args.mode, args.scenario)
        return 0
    except Exception as exc:
        LOG.error("%s: %s", type(exc).__name__, exc, exc_info=args.verbose)
        return 2
