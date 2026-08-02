from __future__ import annotations

import json
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

    if args.gmail_auth or args.gmail_status:
        from src.gmail import (
            GmailClient,
            GmailConfig,
        )

        client = GmailClient(
            GmailConfig(
                enabled=True,
                credentials_file=args.gmail_credentials,
                token_file=args.gmail_token,
                user_id=args.gmail_user_id,
                max_results=args.gmail_max_results,
                max_body_characters=(
                    args.gmail_max_body_characters
                ),
                oauth_port=args.gmail_oauth_port,
                open_browser_for_auth=(
                    args.gmail_open_browser
                ),
            )
        )
        try:
            result = (
                client.authorize_interactively()
                if args.gmail_auth
                else client.status()
            )
            print(
                json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        finally:
            client.close()

    if args.google_calendar_auth or args.google_calendar_status:
        from src.google_calendar import (
            GoogleCalendarClient,
            GoogleCalendarConfig,
        )
        client = GoogleCalendarClient(
            GoogleCalendarConfig(
                enabled=True,
                credentials_file=args.google_calendar_credentials,
                token_file=args.google_calendar_token,
                default_calendar_id=args.google_calendar_default_id,
                max_results=args.google_calendar_max_results,
                oauth_port=args.google_calendar_oauth_port,
                open_browser_for_auth=args.google_calendar_open_browser,
            )
        )
        try:
            result = (
                client.authorize_interactively()
                if args.google_calendar_auth
                else client.status()
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        finally:
            client.close()

    if args.list_browsers:
        from src.browser import format_installed_browsers

        print(format_installed_browsers())
        return 0

    if args.list_reminders:
        from src.scheduler import SchedulerStore, SchedulerStoreConfig

        with SchedulerStore(
            SchedulerStoreConfig(
                enabled=True,
                database=args.scheduler_database,
                max_tasks=args.scheduler_max_tasks,
                max_message_characters=args.scheduler_max_message_characters,
            )
        ) as store:
            tasks = store.list_tasks(status="all", limit=500)
            if not tasks:
                print("No scheduled reminders.")
            for task in tasks:
                print(
                    f"[{task.status}] #{task.id} {task.next_run_local} "
                    f"{task.recurrence}/{task.interval} - {task.message}"
                )
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
