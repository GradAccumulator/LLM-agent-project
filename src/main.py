from __future__ import annotations

import argparse
from datetime import datetime
import sys

import numpy as np
import sounddevice as sd

from src.audio import AudioConfig, MicrophoneStream
from src.wakeword import WakeWordConfig, WakeWordDetector


def parse_device(value: str) -> int | str:
    stripped = value.strip()
    return int(stripped) if stripped.isdigit() else stripped


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Step 2: detect the local 'Hey Jarvis' wake word."
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
        "--threshold",
        type=float,
        default=0.5,
        help="Wake-word score threshold between 0 and 1. Default: 0.5.",
    )
    parser.add_argument(
        "--cooldown",
        type=float,
        default=2.0,
        help="Minimum seconds between detections. Default: 2.0.",
    )
    return parser


def play_detection_sound() -> None:
    try:
        import winsound

        winsound.MessageBeep(winsound.MB_OK)
    except (ImportError, RuntimeError):
        print("\a", end="", flush=True)


def normalized_rms(samples: np.ndarray) -> float:
    scaled = samples.astype(np.float32) / np.iinfo(np.int16).max
    return float(np.sqrt(np.mean(np.square(scaled, dtype=np.float32))))


def print_status(
    *,
    score: float,
    rms: float,
    threshold: float,
    warmed_up: bool,
    input_overflow: bool,
    dropped_frames: int,
    width: int = 30,
) -> None:
    score_width = round(min(max(score, 0.0), 1.0) * width)
    score_bar = "█" * score_width + "·" * (width - score_width)

    state = "LISTENING" if warmed_up else "WARMING UP"
    warnings: list[str] = []
    if input_overflow:
        warnings.append("INPUT OVERFLOW")
    if dropped_frames:
        warnings.append(f"DROPPED={dropped_frames}")

    warning_text = f"  [{' | '.join(warnings)}]" if warnings else ""

    print(
        f"\r{state:<10} [{score_bar}] "
        f"score={score:0.3f} threshold={threshold:0.2f} "
        f"rms={rms:0.4f}{warning_text}      ",
        end="",
        flush=True,
    )


def run(args: argparse.Namespace) -> int:
    audio_config = AudioConfig(device=args.device)
    microphone = MicrophoneStream(audio_config)

    try:
        device = microphone.selected_device_info()
        print("Loading the local Hey Jarvis model...")
        detector = WakeWordDetector(
            WakeWordConfig(
                threshold=args.threshold,
                cooldown_seconds=args.cooldown,
            )
        )

        print(f"Input device : {device['name']}")
        print(f"Audio format : 16000 Hz / mono / int16 / 80 ms")
        print(f"Model        : {detector.loaded_model_name}")
        print(f"Threshold    : {args.threshold:0.2f}")
        print('Say "Hey Jarvis". Press Ctrl+C to stop.\n')

        with microphone:
            while True:
                try:
                    frame = microphone.read(timeout=2.0)
                except TimeoutError:
                    print(
                        "\nNo audio arrived for 2 seconds. "
                        "Check the selected input device.",
                        file=sys.stderr,
                    )
                    return 1

                result = detector.predict(frame.samples)
                rms = normalized_rms(frame.samples)

                print_status(
                    score=result.score,
                    rms=rms,
                    threshold=args.threshold,
                    warmed_up=result.warmed_up,
                    input_overflow=frame.input_overflow,
                    dropped_frames=microphone.dropped_frames,
                )

                if result.detected:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(
                        f"\n[{timestamp}] WAKE WORD DETECTED | "
                        f"phrase={result.model_name} | score={result.score:0.3f}"
                    )
                    play_detection_sound()

    except KeyboardInterrupt:
        print("\nStopped by user.")
        return 0
    except (
        RuntimeError,
        ValueError,
        sd.PortAudioError,
    ) as exc:
        print(f"\nStartup failed: {exc}", file=sys.stderr)
        print(
            "For microphone problems, run "
            "`python -m src.main --list-devices` and retry with "
            "`--device <index>`.",
            file=sys.stderr,
        )
        return 1


def main() -> int:
    args = build_parser().parse_args()

    if args.list_devices:
        print(MicrophoneStream.list_devices())
        return 0

    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
