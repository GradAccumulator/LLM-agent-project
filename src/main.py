from __future__ import annotations

import sys

import sounddevice as sd

from src.app import (
    build_parser,
    build_runtime,
    print_input_devices,
    print_tts_voices,
)


def main() -> int:
    args = build_parser().parse_args()

    try:
        if args.list_devices:
            return print_input_devices()
        if args.list_tts_voices:
            return print_tts_voices(args)

        runtime = build_runtime(args)
        return runtime.run()
    except (RuntimeError, ValueError, sd.PortAudioError) as exc:
        print(f"Startup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
