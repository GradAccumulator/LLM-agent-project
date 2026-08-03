from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from src.settings import LoadedSettings, load_settings
from src.model_routing import (
    normalize_legacy_model_id,
    normalize_reasoning_for_model,
)


def parse_device(
    value: str,
) -> int | str | None:
    value = value.strip()
    if value.casefold() in {
        "",
        "auto",
        "default",
        "none",
    }:
        return None
    return (
        int(value)
        if value.isdigit()
        else value
    )


def parse_language(value: str) -> str | None:
    value = value.strip()
    return None if value.casefold() == "auto" else value


def _bool_pair(
    parser: argparse.ArgumentParser,
    *,
    destination: str,
    positive: tuple[str, ...],
    negative: tuple[str, ...],
    positive_help: str,
    negative_help: str,
) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        *positive,
        dest=destination,
        action="store_true",
        help=positive_help,
    )
    group.add_argument(
        *negative,
        dest=destination,
        action="store_false",
        help=negative_help,
    )


def build_parser(
    defaults: dict[str, object] | None = None,
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Jarvis voice assistant."
        )
    )

    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument(
        "--no-user-config",
        action="store_true",
    )
    parser.add_argument(
        "--print-config",
        action="store_true",
    )

    parser.add_argument(
        "--gmail-auth",
        action="store_true",
        help="Authorize Gmail read-only access.",
    )
    parser.add_argument(
        "--gmail-status",
        action="store_true",
        help="Show Gmail OAuth status.",
    )
    parser.add_argument(
        "--google-calendar-auth",
        action="store_true",
    )
    parser.add_argument(
        "--google-calendar-status",
        action="store_true",
    )
    parser.add_argument(
        "--list-memories",
        action="store_true",
        help="List saved local aliases and preferences.",
    )
    parser.add_argument(
        "--list-reminders",
        action="store_true",
        help="List reminders stored in the scheduler database.",
    )
    parser.add_argument(
        "--edge-cdp-start",
        action="store_true",
        help=(
            "Start or reuse the Jarvis-managed Edge profile "
            "and print its CDP status."
        ),
    )
    parser.add_argument(
        "--edge-cdp-status",
        action="store_true",
        help=(
            "Check the local Edge CDP connection without "
            "starting the voice runtime."
        ),
    )
    parser.add_argument(
        "--list-browsers",
        action="store_true",
        help=(
            "List detected Edge, Chrome, and common "
            "Chromium-based browser installations."
        ),
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
    )
    parser.add_argument(
        "--device",
        type=parse_device,
        default=None,
    )
    parser.add_argument(
        "--prefer-device",
        default="BlackShark",
    )
    _bool_pair(
        parser,
        destination="audio_device_recovery",
        positive=(
            "--audio-device-recovery",
        ),
        negative=(
            "--disable-audio-device-recovery",
        ),
        positive_help=(
            "Recover from stale or unavailable microphone indices."
        ),
        negative_help=(
            "Fail instead of selecting another microphone."
        ),
    )
    _bool_pair(
        parser,
        destination="audio_probe_devices",
        positive=(
            "--audio-probe-devices",
        ),
        negative=(
            "--disable-audio-probe-devices",
        ),
        positive_help=(
            "Open candidate microphones briefly during startup "
            "to verify that PortAudio can use them."
        ),
        negative_help=(
            "Only validate candidate settings without opening them."
        ),
    )
    _bool_pair(
        parser,
        destination="audio_persist_recovery",
        positive=(
            "--persist-audio-recovery",
        ),
        negative=(
            "--no-persist-audio-recovery",
        ),
        positive_help=(
            "Change a stale numeric user-config device to auto."
        ),
        negative_help=(
            "Recover for this run without editing the user config."
        ),
    )
    parser.add_argument(
        "--wake-threshold",
        "--threshold",
        dest="wake_threshold",
        type=float,
        default=0.45,
    )
    parser.add_argument(
        "--cooldown",
        type=float,
        default=2.0,
    )
    parser.add_argument(
        "--vad-threshold",
        type=float,
        default=0.50,
    )
    parser.add_argument(
        "--start-timeout",
        type=float,
        default=4.0,
    )
    parser.add_argument(
        "--end-silence",
        type=float,
        default=0.4,
    )
    parser.add_argument(
        "--max-command-seconds",
        type=float,
        default=15.0,
    )
    parser.add_argument(
        "--save-dir",
        type=Path,
        default=Path("recordings"),
    )
    parser.add_argument(
        "--max-saved-audio-files",
        type=int,
        default=5,
        help="Keep only the newest command WAV files. Default: 5.",
    )
    _bool_pair(
        parser,
        destination="save_audio",
        positive=("--save-audio",),
        negative=("--no-save-audio",),
        positive_help="Save command WAV files.",
        negative_help="Do not save command WAV files.",
    )

    parser.add_argument(
        "--stt-model",
        default="turbo",
    )
    parser.add_argument(
        "--stt-language",
        type=parse_language,
        default="ko",
    )
    parser.add_argument(
        "--stt-device",
        choices=("auto", "cuda", "cpu"),
        default="auto",
    )
    parser.add_argument(
        "--stt-compute-type",
        default="float16",
    )
    parser.add_argument(
        "--stt-beam-size",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--stt-best-of",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--stt-model-dir",
        type=Path,
        default=Path("models/faster-whisper"),
    )
    parser.add_argument(
        "--stt-workers",
        type=int,
        default=2,
    )
    parser.add_argument(
        "--stt-cpu-threads",
        type=int,
        default=16,
    )
    _bool_pair(
        parser,
        destination="stt_warmup",
        positive=("--stt-warmup",),
        negative=("--disable-stt-warmup",),
        positive_help="Warm STT at startup.",
        negative_help="Skip STT warm-up.",
    )

    parser.add_argument(
        "--llm-model",
        default="gpt-5.6-luna",
    )
    parser.add_argument(
        "--llm-reasoning",
        choices=(
            "none",
            "minimal",
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
        ),
        default="low",
    )
    parser.add_argument(
        "--llm-max-output-tokens",
        type=int,
        default=512,
    )
    parser.add_argument(
        "--llm-timeout",
        type=float,
        default=60.0,
    )
    _bool_pair(
        parser,
        destination="llm_memory",
        positive=("--llm-memory",),
        negative=("--no-llm-memory",),
        positive_help="Enable LLM conversation memory.",
        negative_help="Disable LLM conversation memory.",
    )
    _bool_pair(
        parser,
        destination="tools_enabled",
        positive=("--tools",),
        negative=("--disable-tools",),
        positive_help="Enable local tools.",
        negative_help="Disable local tools.",
    )
    parser.add_argument(
        "--llm-max-tool-rounds",
        type=int,
        default=12,
    )
    parser.add_argument(
        "--vision-detail",
        choices=("low", "high", "original", "auto"),
        default="original",
    )

    _bool_pair(
        parser,
        destination="model_routing_enabled",
        positive=("--model-routing",),
        negative=("--disable-model-routing",),
        positive_help=(
            "Enable selective stronger-model delegation."
        ),
        negative_help=(
            "Disable selective stronger-model delegation."
        ),
    )
    parser.add_argument(
        "--routing-balanced-model",
        default="gpt-5.6-terra",
    )
    parser.add_argument(
        "--routing-strong-model",
        default="gpt-5.6-sol",
    )
    parser.add_argument(
        "--routing-balanced-reasoning",
        choices=(
            "none", "minimal", "low", "medium", "high", "xhigh", "max"
        ),
        default="high",
    )
    parser.add_argument(
        "--routing-strong-reasoning",
        choices=(
            "none", "minimal", "low", "medium", "high", "xhigh", "max"
        ),
        default="xhigh",
    )
    _bool_pair(
        parser,
        destination="routing_allow_user_override",
        positive=("--routing-user-override",),
        negative=("--disable-routing-user-override",),
        positive_help=(
            "Honor explicit requests to use a stronger model."
        ),
        negative_help=(
            "Ignore explicit model-escalation phrases."
        ),
    )
    _bool_pair(
        parser,
        destination="routing_allow_automatic",
        positive=("--routing-automatic",),
        negative=("--disable-routing-automatic",),
        positive_help=(
            "Allow the base model to delegate difficult judgments."
        ),
        negative_help=(
            "Allow delegation only when the user explicitly asks."
        ),
    )
    parser.add_argument(
        "--routing-max-delegations",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--routing-max-input-characters",
        type=int,
        default=20000,
    )
    parser.add_argument(
        "--routing-max-output-tokens",
        type=int,
        default=1200,
    )
    parser.add_argument(
        "--routing-timeout",
        type=float,
        default=90.0,
    )
    _bool_pair(
        parser,
        destination="routing_fallback",
        positive=("--routing-fallback",),
        negative=("--disable-routing-fallback",),
        positive_help=(
            "Continue with the base model if delegation fails."
        ),
        negative_help=(
            "Fail the delegated judgment if the stronger model fails."
        ),
    )

    _bool_pair(
        parser,
        destination="web_search_enabled",
        positive=("--web-search",),
        negative=("--disable-web-search",),
        positive_help=(
            "Enable OpenAI hosted web search."
        ),
        negative_help=(
            "Disable OpenAI hosted web search."
        ),
    )
    _bool_pair(
        parser,
        destination="web_search_external_access",
        positive=("--web-search-live",),
        negative=("--web-search-cache-only",),
        positive_help=(
            "Allow live external web access."
        ),
        negative_help=(
            "Use indexed/cached web results only."
        ),
    )
    parser.add_argument(
        "--web-search-max-sources",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--list-tts-voices",
        action="store_true",
    )
    _bool_pair(
        parser,
        destination="tts_enabled",
        positive=("--tts",),
        negative=("--disable-tts", "--no-tts"),
        positive_help="Enable spoken responses.",
        negative_help="Disable spoken responses.",
    )
    parser.add_argument(
        "--tts-voice",
        default="ko-KR-InJoonNeural",
    )
    parser.add_argument(
        "--tts-rate",
        type=int,
        default=50,
    )
    parser.add_argument(
        "--tts-volume",
        type=int,
        default=100,
    )
    parser.add_argument(
        "--tts-pitch",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--tts-max-characters",
        type=int,
        default=1200,
    )
    parser.add_argument(
        "--tts-first-chunk-characters",
        type=int,
        default=80,
    )
    parser.add_argument(
        "--tts-chunk-characters",
        type=int,
        default=180,
    )
    parser.add_argument(
        "--tts-parallel-requests",
        type=int,
        default=3,
    )
    parser.add_argument(
        "--tts-mixer-buffer",
        type=int,
        default=256,
    )

    _bool_pair(
        parser,
        destination="edge_cdp_enabled",
        positive=("--edge-cdp",),
        negative=("--disable-edge-cdp",),
        positive_help=(
            "Enable the local Edge CDP bridge."
        ),
        negative_help=(
            "Disable the Edge CDP bridge."
        ),
    )
    parser.add_argument(
        "--edge-cdp-endpoint",
        default="http://127.0.0.1:9222",
    )
    parser.add_argument(
        "--edge-cdp-connect-timeout",
        type=float,
        default=5.0,
    )
    parser.add_argument(
        "--edge-cdp-action-timeout",
        type=float,
        default=10.0,
    )
    parser.add_argument(
        "--edge-cdp-max-page-text",
        type=int,
        default=16000,
    )
    parser.add_argument(
        "--edge-cdp-tab-ttl",
        type=float,
        default=300.0,
    )
    parser.add_argument(
        "--edge-cdp-element-ttl",
        type=float,
        default=180.0,
    )
    parser.add_argument(
        "--edge-cdp-max-elements",
        type=int,
        default=100,
    )
    parser.add_argument(
        "--edge-cdp-max-fill-characters",
        type=int,
        default=2000,
    )
    parser.add_argument(
        "--edge-cdp-screenshot-dir",
        type=Path,
        default=Path("screenshots"),
    )
    _bool_pair(
        parser,
        destination="edge_cdp_auto_start",
        positive=("--edge-cdp-auto-start",),
        negative=("--disable-edge-cdp-auto-start",),
        positive_help=(
            "Automatically start the dedicated Jarvis Edge profile."
        ),
        negative_help=(
            "Only attach to an Edge CDP endpoint that is already running."
        ),
    )
    parser.add_argument(
        "--edge-cdp-executable",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--edge-cdp-profile-dir",
        type=Path,
        default=Path("data/edge_profile"),
    )
    parser.add_argument(
        "--edge-cdp-start-timeout",
        type=float,
        default=15.0,
    )
    parser.add_argument(
        "--edge-cdp-start-poll",
        type=float,
        default=0.2,
    )
    parser.add_argument(
        "--edge-cdp-startup-url",
        default="",
    )
    _bool_pair(
        parser,
        destination="edge_cdp_restore_session",
        positive=("--edge-cdp-restore-session",),
        negative=("--disable-edge-cdp-restore-session",),
        positive_help=(
            "Restore the dedicated Edge profile's previous session."
        ),
        negative_help=(
            "Start the dedicated Edge profile without the restore flag."
        ),
    )
    _bool_pair(
        parser,
        destination="edge_cdp_keep_running",
        positive=("--edge-cdp-keep-running",),
        negative=("--edge-cdp-stop-on-exit",),
        positive_help=(
            "Keep the dedicated Edge process running when Jarvis exits."
        ),
        negative_help=(
            "Terminate only the Edge process launched by this Jarvis run."
        ),
    )

    _bool_pair(
        parser,
        destination="edge_cdp_allow_dom_actions",
        positive=("--edge-cdp-dom-actions",),
        negative=("--disable-edge-cdp-dom-actions",),
        positive_help=(
            "Allow safety-filtered Edge DOM click and draft text actions."
        ),
        negative_help=(
            "Keep the Edge CDP bridge read-only except tab selection."
        ),
    )

    _bool_pair(
        parser,
        destination="edge_cdp_allow_tab_close",
        positive=("--edge-cdp-tab-close",),
        negative=("--disable-edge-cdp-tab-close",),
        positive_help=(
            "Allow confirmed Edge tab closing."
        ),
        negative_help=(
            "Disable Edge tab closing."
        ),
    )

    _bool_pair(
        parser,
        destination="windows_uia_enabled",
        positive=("--windows-uia",),
        negative=("--disable-windows-uia",),
        positive_help="Enable Windows UI Automation inspection.",
        negative_help="Disable Windows UI Automation.",
    )
    _bool_pair(
        parser,
        destination="windows_uia_allow_actions",
        positive=("--windows-uia-actions",),
        negative=("--disable-windows-uia-actions",),
        positive_help="Register confirmed UI Automation actions.",
        negative_help="Keep UI Automation inspection read-only.",
    )
    parser.add_argument(
        "--windows-uia-backend",
        choices=("uia",),
        default="uia",
    )
    parser.add_argument(
        "--windows-uia-element-ttl",
        type=float,
        default=180.0,
    )
    parser.add_argument(
        "--windows-uia-max-elements",
        type=int,
        default=200,
    )
    parser.add_argument(
        "--windows-uia-screenshot-dir",
        type=Path,
        default=Path("screenshots"),
    )

    _bool_pair(
        parser,
        destination="confirmation_enabled",
        positive=("--confirmation",),
        negative=("--disable-confirmation",),
        positive_help=(
            "Require explicit approval for protected write tools."
        ),
        negative_help=(
            "Disable the confirmation gate."
        ),
    )
    parser.add_argument(
        "--confirmation-timeout",
        type=float,
        default=60.0,
    )
    parser.add_argument(
        "--confirmation-code-digits",
        type=int,
        default=4,
    )
    parser.add_argument(
        "--confirmation-max-attempts",
        type=int,
        default=3,
    )

    _bool_pair(
        parser,
        destination="gmail_enabled",
        positive=("--gmail",),
        negative=("--disable-gmail",),
        positive_help="Enable read-only Gmail tools.",
        negative_help="Disable Gmail integration.",
    )
    parser.add_argument(
        "--gmail-credentials",
        type=Path,
        default=Path("config/gmail_credentials.json"),
    )
    parser.add_argument(
        "--gmail-token",
        type=Path,
        default=Path("data/gmail_token.json"),
    )
    parser.add_argument(
        "--gmail-user-id",
        default="me",
    )
    parser.add_argument(
        "--gmail-max-results",
        type=int,
        default=20,
    )
    parser.add_argument(
        "--gmail-max-body-characters",
        type=int,
        default=8000,
    )
    parser.add_argument(
        "--gmail-oauth-port",
        type=int,
        default=0,
    )
    _bool_pair(
        parser,
        destination="gmail_open_browser",
        positive=("--gmail-open-browser",),
        negative=("--gmail-no-browser",),
        positive_help="Open browser for Gmail OAuth.",
        negative_help="Do not automatically open OAuth browser.",
    )

    _bool_pair(
        parser,
        destination="google_calendar_enabled",
        positive=("--google-calendar",),
        negative=("--disable-google-calendar",),
        positive_help="Enable read-only Google Calendar.",
        negative_help="Disable Google Calendar.",
    )
    parser.add_argument(
        "--google-calendar-credentials",
        type=Path,
        default=Path("config/google_calendar_credentials.json"),
    )
    parser.add_argument(
        "--google-calendar-token",
        type=Path,
        default=Path("data/google_calendar_token.json"),
    )
    parser.add_argument(
        "--google-calendar-default-id",
        default="primary",
    )
    parser.add_argument(
        "--google-calendar-max-results",
        type=int,
        default=50,
    )
    parser.add_argument(
        "--google-calendar-oauth-port",
        type=int,
        default=0,
    )
    _bool_pair(
        parser,
        destination="google_calendar_allow_writes",
        positive=(
            "--google-calendar-writes",
        ),
        negative=(
            "--disable-google-calendar-writes",
        ),
        positive_help=(
            "Register confirmed Calendar create, update, and delete tools."
        ),
        negative_help=(
            "Keep Google Calendar read-only."
        ),
    )
    _bool_pair(
        parser,
        destination="google_calendar_open_browser",
        positive=("--google-calendar-open-browser",),
        negative=("--google-calendar-no-browser",),
        positive_help="Open browser for Calendar OAuth.",
        negative_help="Do not automatically open OAuth browser.",
    )

    _bool_pair(
        parser,
        destination="scheduler_enabled",
        positive=("--scheduler",),
        negative=("--disable-scheduler",),
        positive_help="Enable persistent reminders.",
        negative_help="Disable reminders.",
    )
    parser.add_argument("--scheduler-database", type=Path, default=Path("data/jarvis_tasks.db"))
    parser.add_argument("--scheduler-poll-interval", type=float, default=0.5)
    parser.add_argument("--scheduler-max-tasks", type=int, default=200)
    parser.add_argument("--scheduler-max-message-characters", type=int, default=500)
    _bool_pair(
        parser,
        destination="scheduler_announce_tts",
        positive=("--scheduler-tts",),
        negative=("--scheduler-no-tts",),
        positive_help="Speak due reminders.",
        negative_help="Do not speak due reminders.",
    )
    parser.add_argument("--scheduler-max-announcements", type=int, default=3)

    _bool_pair(
        parser,
        destination="long_term_memory_enabled",
        positive=("--long-term-memory",),
        negative=("--disable-long-term-memory",),
        positive_help="Enable explicit SQLite long-term memory.",
        negative_help="Disable local long-term memory tools and context.",
    )
    parser.add_argument(
        "--memory-database",
        type=Path,
        default=Path("data/jarvis_memory.db"),
    )
    parser.add_argument(
        "--memory-context-limit",
        type=int,
        default=20,
    )
    parser.add_argument(
        "--memory-context-characters",
        type=int,
        default=4000,
    )
    parser.add_argument(
        "--memory-max-entries",
        type=int,
        default=200,
    )
    parser.add_argument(
        "--memory-max-value-characters",
        type=int,
        default=2048,
    )

    _bool_pair(
        parser,
        destination="planning_enabled",
        positive=("--planning",),
        negative=("--disable-planning",),
        positive_help=(
            "Plan and verify multi-step computer tasks."
        ),
        negative_help=(
            "Disable enforced planning for multi-step tasks."
        ),
    )
    parser.add_argument(
        "--planning-max-steps",
        type=int,
        default=6,
    )
    parser.add_argument(
        "--planning-max-repair-attempts",
        type=int,
        default=2,
    )

    _bool_pair(
        parser,
        destination="streaming_enabled",
        positive=("--streaming",),
        negative=("--disable-streaming",),
        positive_help=(
            "Stream GPT text into sentence-level TTS."
        ),
        negative_help=(
            "Wait for the full GPT response before TTS."
        ),
    )
    parser.add_argument(
        "--streaming-minimum-characters",
        type=int,
        default=24,
    )
    parser.add_argument(
        "--streaming-maximum-characters",
        type=int,
        default=160,
    )

    _bool_pair(
        parser,
        destination="continuous_conversation",
        positive=("--continuous-conversation",),
        negative=("--disable-continuous-conversation",),
        positive_help=(
            "Allow follow-up commands without the wake word."
        ),
        negative_help=(
            "Require the wake word before every command."
        ),
    )
    parser.add_argument(
        "--followup-timeout",
        type=float,
        default=12.0,
    )
    parser.add_argument(
        "--max-conversation-turns",
        type=int,
        default=8,
    )

    _bool_pair(
        parser,
        destination="browser_automation",
        positive=("--browser-automation",),
        negative=("--disable-browser-automation",),
        positive_help="Enable Playwright browser tools.",
        negative_help="Disable Playwright browser tools.",
    )
    parser.add_argument(
        "--browser-control-mode",
        choices=("system", "automation"),
        default="system",
    )
    parser.add_argument(
        "--browser",
        dest="browser_selection",
        choices=(
            "msedge",
            "msedge-beta",
            "msedge-dev",
            "msedge-canary",
            "chrome",
            "chrome-beta",
            "chrome-dev",
            "chrome-canary",
            "chromium",
            "custom",
        ),
        default="msedge",
        help=(
            "Browser used by automation and fast-path web commands."
        ),
    )
    parser.add_argument(
        "--browser-executable",
        dest="browser_executable_path",
        type=Path,
        default=None,
        help=(
            "Executable path used only with --browser custom."
        ),
    )
    _bool_pair(
        parser,
        destination="browser_headless",
        positive=("--browser-headless",),
        negative=("--browser-headed",),
        positive_help="Run the selected browser without a visible window.",
        negative_help="Show the selected browser window.",
    )
    parser.add_argument(
        "--browser-profile-dir",
        type=Path,
        default=Path("browser_profiles"),
    )
    parser.add_argument(
        "--browser-navigation-timeout",
        type=float,
        default=20.0,
    )
    parser.add_argument(
        "--browser-action-timeout",
        type=float,
        default=10.0,
    )
    parser.add_argument(
        "--browser-max-page-text",
        type=int,
        default=12000,
    )
    _bool_pair(
        parser,
        destination="fast_path_enabled",
        positive=("--fast-path",),
        negative=("--disable-fast-path",),
        positive_help="Execute simple deterministic commands without GPT.",
        negative_help="Send all non-local commands through GPT.",
    )

    _bool_pair(
        parser,
        destination="barge_in_enabled",
        positive=("--barge-in",),
        negative=("--disable-barge-in",),
        positive_help=(
            "Allow the user to interrupt spoken responses."
        ),
        negative_help=(
            "Do not listen for interruptions during TTS."
        ),
    )
    parser.add_argument(
        "--barge-in-vad-threshold",
        type=float,
        default=0.78,
    )
    parser.add_argument(
        "--barge-in-grace",
        type=float,
        default=0.65,
    )
    parser.add_argument(
        "--barge-in-trigger-speech",
        type=float,
        default=0.32,
    )
    parser.add_argument(
        "--barge-in-end-silence",
        type=float,
        default=0.48,
    )
    parser.add_argument(
        "--barge-in-max-utterance",
        type=float,
        default=12.0,
    )
    parser.add_argument(
        "--barge-in-pre-roll",
        type=float,
        default=0.24,
    )
    parser.add_argument(
        "--barge-in-minimum-rms",
        type=float,
        default=0.008,
    )

    _bool_pair(
        parser,
        destination="show_state_transitions",
        positive=("--state-transitions",),
        negative=("--hide-state-transitions",),
        positive_help="Print state transitions.",
        negative_help="Hide state transitions.",
    )
    parser.add_argument(
        "--recovery-delay",
        type=float,
        default=0.25,
    )

    _bool_pair(
        parser,
        destination="metrics_enabled",
        positive=("--metrics",),
        negative=("--disable-metrics",),
        positive_help="Enable JSONL metrics.",
        negative_help="Disable JSONL metrics.",
    )
    parser.add_argument(
        "--metrics-dir",
        type=Path,
        default=Path("logs"),
    )
    _bool_pair(
        parser,
        destination="metrics_include_text",
        positive=("--metrics-include-text",),
        negative=("--metrics-redact-text",),
        positive_help="Store transcript and reply text.",
        negative_help="Redact transcript and reply text.",
    )
    _bool_pair(
        parser,
        destination="metrics_flush_each_event",
        positive=("--metrics-flush",),
        negative=("--metrics-buffered",),
        positive_help="Flush each JSONL event.",
        negative_help="Buffer JSONL writes.",
    )

    parser.set_defaults(
        save_audio=True,
        stt_warmup=True,
        llm_memory=True,
        tools_enabled=True,
        model_routing_enabled=True,
        routing_allow_user_override=True,
        routing_allow_automatic=True,
        routing_fallback=True,
        web_search_enabled=True,
        web_search_external_access=True,
        tts_enabled=True,
        edge_cdp_enabled=True,
        edge_cdp_auto_start=True,
        edge_cdp_restore_session=True,
        edge_cdp_keep_running=True,
        edge_cdp_allow_dom_actions=True,
        edge_cdp_allow_tab_close=True,
        windows_uia_enabled=True,
        windows_uia_allow_actions=True,
        audio_device_recovery=True,
        audio_probe_devices=True,
        audio_persist_recovery=True,
        confirmation_enabled=True,
        gmail_enabled=True,
        gmail_open_browser=True,
        google_calendar_enabled=True,
        google_calendar_allow_writes=True,
        google_calendar_open_browser=True,
        scheduler_enabled=True,
        scheduler_announce_tts=True,
        long_term_memory_enabled=True,
        planning_enabled=True,
        streaming_enabled=True,
        continuous_conversation=True,
        browser_automation=True,
        browser_headless=False,
        fast_path_enabled=True,
        barge_in_enabled=True,
        show_state_transitions=True,
        metrics_enabled=True,
        metrics_include_text=False,
        metrics_flush_each_event=True,
    )
    if defaults:
        parser.set_defaults(**defaults)

    return parser


def parse_args(
    argv: Sequence[str] | None = None,
) -> tuple[argparse.Namespace, LoadedSettings]:
    pre_parser = argparse.ArgumentParser(
        add_help=False
    )
    pre_parser.add_argument(
        "--config",
        type=Path,
        default=None,
    )
    pre_parser.add_argument(
        "--no-user-config",
        action="store_true",
    )
    preliminary, _ = pre_parser.parse_known_args(argv)

    loaded = load_settings(
        custom_path=preliminary.config,
        load_user=not preliminary.no_user_config,
    )
    effective_argv = (
        list(argv)
        if argv is not None
        else list(
            __import__("sys").argv[1:]
        )
    )
    args = build_parser(
        loaded.argument_defaults
    ).parse_args(effective_argv)
    args.device_was_explicit = any(
        item == "--device"
        or item.startswith("--device=")
        for item in effective_argv
    )

    migrations: list[str] = []
    for attribute in (
        "llm_model",
        "routing_balanced_model",
        "routing_strong_model",
    ):
        current = str(getattr(args, attribute))
        normalized, note = normalize_legacy_model_id(current)
        setattr(args, attribute, normalized)
        if note is not None:
            migrations.append(note)

    for model_attribute, effort_attribute in (
        ("llm_model", "llm_reasoning"),
        ("routing_balanced_model", "routing_balanced_reasoning"),
        ("routing_strong_model", "routing_strong_reasoning"),
    ):
        normalized, note = normalize_reasoning_for_model(
            str(getattr(args, model_attribute)),
            str(getattr(args, effort_attribute)),
        )
        setattr(args, effort_attribute, normalized)
        if note is not None:
            migrations.append(note)

    args.model_migrations = tuple(dict.fromkeys(migrations))
    return args, loaded


def print_effective_config(
    args: argparse.Namespace,
    loaded: LoadedSettings,
) -> None:
    omitted = {
        "config",
        "no_user_config",
        "print_config",
        "list_devices",
        "list_browsers",
        "edge_cdp_status",
        "edge_cdp_start",
        "list_memories",
        "list_tts_voices",
        "device_was_explicit",
        "model_migrations",
    }
    values = {
        key: (
            str(value)
            if isinstance(value, Path)
            else value
        )
        for key, value in sorted(vars(args).items())
        if key not in omitted
    }
    print(
        json.dumps(
            {
                "loaded_files": [
                    str(path)
                    for path in loaded.loaded_files
                ],
                "effective_arguments": values,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
