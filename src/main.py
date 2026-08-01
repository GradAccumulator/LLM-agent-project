from __future__ import annotations

import sys

from src.app.cli import parse_args, print_effective_config
from src.settings import ConfigError


def main() -> int:
    try:
        args, loaded = parse_args()
    except (ConfigError, ValueError) as exc:
        print(f"Startup failed: {exc}", file=sys.stderr)
        return 1

    if args.print_config:
        print_effective_config(args, loaded)
        return 0

    if args.list_browsers:
        from src.browser import format_installed_browsers

        print(format_installed_browsers())
        return 0

    if args.list_memories:
        from src.memory import (
            LocalMemoryStore,
            MemoryStoreConfig,
        )

        with LocalMemoryStore(
            MemoryStoreConfig(
                enabled=True,
                database=args.memory_database,
                context_limit=args.memory_context_limit,
                max_context_characters=(
                    args.memory_context_characters
                ),
                max_entries=args.memory_max_entries,
                max_value_characters=(
                    args.memory_max_value_characters
                ),
            )
        ) as store:
            records = store.list_memories("all", 500)
            if not records:
                print("No saved memories.")
            for record in records:
                print(
                    f"[{record.kind}] {record.name} "
                    f"({record.value_type}) = {record.value}"
                )
        return 0

    try:
        import sounddevice as sd

        from src.app.bootstrap import (
            build_runtime,
            print_input_devices,
            print_tts_voices,
        )
    except ImportError as exc:
        print(
            "Startup failed: a required package is missing. "
            "Run `python -m pip install -r requirements.txt`. "
            f"Details: {exc}",
            file=sys.stderr,
        )
        return 1

    try:
        if args.list_devices:
            return print_input_devices()
        if args.list_tts_voices:
            return print_tts_voices(args)

        if loaded.loaded_files:
            print("Config files:")
            for path in loaded.loaded_files:
                print(f"  - {path}")

        runtime = build_runtime(args)
        return runtime.run()
    except (
        RuntimeError,
        ValueError,
        sd.PortAudioError,
    ) as exc:
        print(f"Startup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
