from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

import numpy as np
import sounddevice as sd

from src.audio import AudioConfig, MicrophoneStream
from src.speech import CaptureConfig, SpeechCapture, save_wave_file
from src.stt import SpeechRecognizer, SpeechRecognizerConfig
from src.vad import VoiceActivityConfig, VoiceActivityDetector
from src.wakeword import WakeWordConfig, WakeWordDetector


def parse_device(value: str) -> int | str:
    value = value.strip()
    return int(value) if value.isdigit() else value


def parse_language(value: str) -> str | None:
    value = value.strip()
    return None if value.casefold() == "auto" else value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Detect Hey Jarvis, capture a command, and transcribe it "
            "locally with Faster-Whisper."
        )
    )
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--device", type=parse_device, default=None)
    parser.add_argument(
        "--prefer-device",
        default="BlackShark",
        help="Preferred microphone name substring. Default: BlackShark.",
    )
    parser.add_argument(
        "--wake-threshold",
        "--threshold",
        dest="wake_threshold",
        type=float,
        default=0.45,
        help="Wake-word threshold. Default: 0.45.",
    )
    parser.add_argument("--cooldown", type=float, default=2.0)
    parser.add_argument(
        "--vad-threshold",
        type=float,
        default=0.50,
        help="Silero speech threshold. Default: 0.50.",
    )
    parser.add_argument(
        "--start-timeout",
        type=float,
        default=4.0,
        help="Seconds to wait for speech after wake-word detection.",
    )
    parser.add_argument(
        "--end-silence",
        type=float,
        default=0.8,
        help="Silence duration that ends a command.",
    )
    parser.add_argument(
        "--max-command-seconds",
        type=float,
        default=15.0,
        help="Maximum captured command length.",
    )
    parser.add_argument(
        "--save-dir",
        type=Path,
        default=Path("recordings"),
        help="Directory for captured WAV files.",
    )
    parser.add_argument(
        "--no-save-audio",
        action="store_true",
        help="Do not keep captured command WAV files.",
    )
    parser.add_argument(
        "--stt-model",
        default="turbo",
        help="Faster-Whisper model name or local path. Default: turbo.",
    )
    parser.add_argument(
        "--stt-language",
        type=parse_language,
        default="ko",
        help="Language code, or auto. Default: ko.",
    )
    parser.add_argument(
        "--stt-device",
        choices=("auto", "cuda", "cpu"),
        default="auto",
        help="STT inference device. Default: auto.",
    )
    parser.add_argument(
        "--stt-compute-type",
        default="auto",
        help=(
            "CTranslate2 compute type. Default: auto "
            "(float16 on CUDA, int8 on CPU)."
        ),
    )
    parser.add_argument(
        "--stt-beam-size",
        type=int,
        default=5,
        help="Whisper beam size. Default: 5.",
    )
    parser.add_argument(
        "--stt-model-dir",
        type=Path,
        default=Path("models/faster-whisper"),
        help="Model download/cache directory.",
    )
    parser.add_argument(
        "--stt-cpu-threads",
        type=int,
        default=8,
        help="CPU threads used by CTranslate2. Default: 8.",
    )
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

        print("Loading Hey Jarvis...")
        wakeword = WakeWordDetector(
            WakeWordConfig(
                threshold=args.wake_threshold,
                cooldown_seconds=args.cooldown,
            )
        )

        print("Loading Silero VAD...")
        vad = VoiceActivityDetector(
            VoiceActivityConfig(threshold=args.vad_threshold)
        )
        speech_capture = SpeechCapture(
            CaptureConfig(
                start_timeout_seconds=args.start_timeout,
                end_silence_seconds=args.end_silence,
                max_utterance_seconds=args.max_command_seconds,
            ),
            detector=vad,
        )

        print(
            f"Loading Faster-Whisper '{args.stt_model}' "
            "(the first run may download the model)..."
        )
        recognizer = SpeechRecognizer(
            SpeechRecognizerConfig(
                model_size=args.stt_model,
                language=args.stt_language,
                device=args.stt_device,
                compute_type=args.stt_compute_type,
                beam_size=args.stt_beam_size,
                download_root=args.stt_model_dir,
                cpu_threads=args.stt_cpu_threads,
            )
        )

        language_text = recognizer.language or "auto"
        print(f"Input device   : [{microphone.device}] {info['name']}")
        print(f"Capture rate   : {microphone.input_sample_rate} Hz")
        print("Pipeline audio : 16000 Hz / mono / int16 / 80 ms")
        print(f"Wake threshold : {args.wake_threshold:.2f}")
        print(f"VAD threshold  : {args.vad_threshold:.2f}")
        print(f"End silence    : {args.end_silence:.2f} s")
        print(f"STT model      : {recognizer.model_name}")
        print(
            f"STT runtime    : {recognizer.device} / "
            f"{recognizer.compute_type}"
        )
        print(f"STT language   : {language_text}")
        print('Say "Hey Jarvis". Press Ctrl+C to stop.\n')

        with microphone:
            while True:
                frame = microphone.read(timeout=2.0)
                result = wakeword.predict(frame.samples)
                rms = normalized_rms(frame.samples)

                print(
                    f"\rLISTENING wake={result.score:.3f} "
                    f"rms={rms:.4f} device={microphone.device}      ",
                    end="",
                    flush=True,
                )

                if not result.detected:
                    continue

                timestamp = datetime.now().strftime("%H:%M:%S")
                print(
                    f"\n[{timestamp}] WAKE WORD DETECTED | "
                    f"phrase={result.model_name} | score={result.score:.3f}"
                )
                play_detection_sound()
                microphone.clear_pending()
                print("COMMAND: waiting for speech...")

                capture = speech_capture.capture(microphone)

                if not capture.speech_detected:
                    print(
                        "COMMAND: no speech detected "
                        f"(peak VAD={capture.peak_probability:.3f})."
                    )
                else:
                    print(
                        "COMMAND CAPTURED | "
                        f"duration={capture.duration_seconds:.2f}s | "
                        f"peak VAD={capture.peak_probability:.3f} | "
                        f"end={capture.end_reason}"
                    )

                    if not args.no_save_audio:
                        output_path = save_wave_file(
                            capture.samples,
                            directory=args.save_dir,
                        )
                        print(f"Saved: {output_path}")

                    print("TRANSCRIBING...", flush=True)
                    transcription = recognizer.transcribe(capture.samples)
                    confidence = (
                        transcription.language_probability * 100.0
                    )
                    transcript_text = transcription.text or "<empty>"
                    print(
                        f"TRANSCRIPT [{transcription.language} "
                        f"{confidence:.1f}% | "
                        f"{transcription.inference_seconds:.2f}s]: "
                        f"{transcript_text}"
                    )

                wakeword.reset()
                microphone.clear_pending()
                print('\nSay "Hey Jarvis" for another command.\n')

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
