from __future__ import annotations

import argparse
import sys

import sounddevice as sd

from src.audio import AudioConfig, MicrophoneMonitor


def parse_device(value: str) -> int | str:
    stripped = value.strip()
    return int(stripped) if stripped.isdigit() else stripped


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Step 1: verify a stable local microphone stream."
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="Print available audio devices and exit.",
    )
    parser.add_argument(
        "--device",
        type=parse_device,
        default=None,
        help="Input device index or a unique part of its name.",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=16_000,
        help="Input sample rate. Default: 16000.",
    )
    parser.add_argument(
        "--block-ms",
        type=int,
        default=80,
        help="Audio block duration in milliseconds. Default: 80.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.list_devices:
        print(MicrophoneMonitor.list_devices())
        return 0

    config = AudioConfig(
        sample_rate=args.sample_rate,
        block_duration_ms=args.block_ms,
        device=args.device,
    )
    monitor = MicrophoneMonitor(config)

    try:
        device = monitor.selected_device_info()
        print(f"Input device : {device['name']}")
        print(f"Sample rate : {config.sample_rate} Hz")
        print(f"Block size  : {config.block_size} frames")
        print("Speak into the microphone. Press Ctrl+C to stop.\n")
        monitor.run()
    except KeyboardInterrupt:
        monitor.stop()
        print("\nInterrupted by user.")
    except (sd.PortAudioError, ValueError) as exc:
        print(f"\nAudio setup failed: {exc}", file=sys.stderr)
        print(
            "Run `python -m src.main --list-devices` and retry with "
            "`--device <index>`.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
