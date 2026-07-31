from __future__ import annotations

import argparse
from datetime import datetime
import sys

import numpy as np
import sounddevice as sd

from src.audio import AudioConfig, MicrophoneStream
from src.wakeword import WakeWordConfig, WakeWordDetector


def parse_device(value: str) -> int | str:
    value = value.strip()
    return int(value) if value.isdigit() else value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect the local 'Hey Jarvis' wake word."
    )
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--device", type=parse_device, default=None)
    parser.add_argument(
        "--prefer-device",
        default="BlackShark",
        help="Preferred microphone name substring. Default: BlackShark.",
    )
    parser.add_argument("--threshold", type=float, default=0.45)
    parser.add_argument("--cooldown", type=float, default=2.0)
    return parser


def normalized_rms(samples: np.ndarray) -> float:
    scaled = samples.astype(np.float32) / np.iinfo(np.int16).max
    return float(np.sqrt(np.mean(np.square(scaled, dtype=np.float32))))


def play_detection_sound() -> None:
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_OK)
    except (ImportError, RuntimeError):
        print("\a", end="", flush=True)


def run(args: argparse.Namespace) -> int:
    try:
        microphone = MicrophoneStream(
            AudioConfig(
                device=args.device,
                preferred_device_name=args.prefer_device,
            )
        )
        info = microphone.selected_device_info()

        print("Loading the local Hey Jarvis model...")
        detector = WakeWordDetector(
            WakeWordConfig(
                threshold=args.threshold,
                cooldown_seconds=args.cooldown,
            )
        )

        print(f"Input device : [{microphone.device}] {info['name']}")
        print(f"Capture rate : {microphone.input_sample_rate} Hz")
        print("Model input  : 16000 Hz / mono / int16 / 80 ms")
        print(f"Threshold    : {args.threshold:.2f}")
        print('Say "Hey Jarvis". Press Ctrl+C to stop.\n')

        with microphone:
            while True:
                frame = microphone.read(timeout=2.0)
                result = detector.predict(frame.samples)
                rms = normalized_rms(frame.samples)

                print(
                    f"\rLISTENING score={result.score:.3f} "
                    f"rms={rms:.4f} device={microphone.device}      ",
                    end="",
                    flush=True,
                )

                if result.detected:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(
                        f"\n[{timestamp}] WAKE WORD DETECTED | "
                        f"phrase={result.model_name} | score={result.score:.3f}"
                    )
                    play_detection_sound()

    except KeyboardInterrupt:
        print("\nStopped by user.")
        return 0
    except TimeoutError as exc:
        print(f"\nAudio timeout: {exc}", file=sys.stderr)
        return 1
    except (RuntimeError, ValueError, sd.PortAudioError) as exc:
        print(f"\nStartup failed: {exc}", file=sys.stderr)
        return 1


def main() -> int:
    args = build_parser().parse_args()
    if args.list_devices:
        print(MicrophoneStream.list_devices())
        return 0
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
