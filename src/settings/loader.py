from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any, Callable


class ConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LoadedSettings:
    argument_defaults: dict[str, Any]
    loaded_files: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class _SettingSpec:
    destination: str
    expected_type: type | tuple[type, ...]
    converter: Callable[[Any], Any] | None = None


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _as_path(value: Any) -> Path:
    if not isinstance(value, str):
        raise ConfigError("Path values must be TOML strings.")
    return Path(value)


def _as_optional_path(value: Any) -> Path | None:
    if not isinstance(value, str):
        raise ConfigError(
            "Optional path values must be TOML strings."
        )
    stripped = value.strip()
    return Path(stripped) if stripped else None


def _as_language(value: Any) -> str | None:
    if not isinstance(value, str):
        raise ConfigError("STT language must be a string.")
    return None if value.casefold() == "auto" else value


def _as_float(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError("Expected a numeric value.")
    return float(value)


def _as_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError("Expected an integer value.")
    return value


def _as_audio_device(value: Any) -> int | str:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ConfigError("Audio device must be an integer or string.")
    return value


_SCHEMA: dict[str, dict[str, _SettingSpec]] = {
    "audio": {
        "device": _SettingSpec(
            "device", (int, str), _as_audio_device
        ),
        "preferred_device": _SettingSpec("prefer_device", str),
        "start_timeout_seconds": _SettingSpec(
            "start_timeout", (int, float), _as_float
        ),
        "end_silence_seconds": _SettingSpec(
            "end_silence", (int, float), _as_float
        ),
        "max_command_seconds": _SettingSpec(
            "max_command_seconds", (int, float), _as_float
        ),
        "save_audio": _SettingSpec("save_audio", bool),
        "save_directory": _SettingSpec(
            "save_dir", str, _as_path
        ),
        "max_saved_files": _SettingSpec(
            "max_saved_audio_files", int, _as_int
        ),
    },
    "wakeword": {
        "threshold": _SettingSpec(
            "wake_threshold", (int, float), _as_float
        ),
        "cooldown_seconds": _SettingSpec(
            "cooldown", (int, float), _as_float
        ),
    },
    "vad": {
        "threshold": _SettingSpec(
            "vad_threshold", (int, float), _as_float
        ),
    },
    "stt": {
        "model": _SettingSpec("stt_model", str),
        "language": _SettingSpec(
            "stt_language", str, _as_language
        ),
        "device": _SettingSpec("stt_device", str),
        "compute_type": _SettingSpec("stt_compute_type", str),
        "beam_size": _SettingSpec(
            "stt_beam_size", int, _as_int
        ),
        "best_of": _SettingSpec("stt_best_of", int, _as_int),
        "model_directory": _SettingSpec(
            "stt_model_dir", str, _as_path
        ),
        "workers": _SettingSpec("stt_workers", int, _as_int),
        "warmup": _SettingSpec("stt_warmup", bool),
        "cpu_threads": _SettingSpec(
            "stt_cpu_threads", int, _as_int
        ),
    },
    "llm": {
        "model": _SettingSpec("llm_model", str),
        "reasoning": _SettingSpec("llm_reasoning", str),
        "max_output_tokens": _SettingSpec(
            "llm_max_output_tokens", int, _as_int
        ),
        "timeout_seconds": _SettingSpec(
            "llm_timeout", (int, float), _as_float
        ),
        "memory": _SettingSpec("llm_memory", bool),
        "tools": _SettingSpec("tools_enabled", bool),
        "max_tool_rounds": _SettingSpec(
            "llm_max_tool_rounds", int, _as_int
        ),
        "vision_detail": _SettingSpec("vision_detail", str),
    },
    "web_search": {
        "enabled": _SettingSpec(
            "web_search_enabled", bool
        ),
        "external_web_access": _SettingSpec(
            "web_search_external_access", bool
        ),
        "max_sources_display": _SettingSpec(
            "web_search_max_sources",
            int,
            _as_int,
        ),
    },
    "tts": {
        "enabled": _SettingSpec("tts_enabled", bool),
        "voice": _SettingSpec("tts_voice", str),
        "rate_percent": _SettingSpec(
            "tts_rate", int, _as_int
        ),
        "volume": _SettingSpec("tts_volume", int, _as_int),
        "pitch_hz": _SettingSpec("tts_pitch", int, _as_int),
        "max_characters": _SettingSpec(
            "tts_max_characters", int, _as_int
        ),
        "first_chunk_characters": _SettingSpec(
            "tts_first_chunk_characters", int, _as_int
        ),
        "chunk_characters": _SettingSpec(
            "tts_chunk_characters", int, _as_int
        ),
        "parallel_requests": _SettingSpec(
            "tts_parallel_requests", int, _as_int
        ),
        "mixer_buffer": _SettingSpec(
            "tts_mixer_buffer", int, _as_int
        ),
    },
    "windows_uia": {
        "enabled": _SettingSpec("windows_uia_enabled", bool),
        "backend": _SettingSpec("windows_uia_backend", str),
        "element_ttl_seconds": _SettingSpec(
            "windows_uia_element_ttl", (int, float), _as_float
        ),
        "max_elements": _SettingSpec(
            "windows_uia_max_elements", int, _as_int
        ),
        "allow_actions": _SettingSpec(
            "windows_uia_allow_actions", bool
        ),
    },
    "confirmation": {
        "enabled": _SettingSpec(
            "confirmation_enabled", bool
        ),
        "timeout_seconds": _SettingSpec(
            "confirmation_timeout",
            (int, float),
            _as_float,
        ),
        "high_risk_code_digits": _SettingSpec(
            "confirmation_code_digits",
            int,
            _as_int,
        ),
        "max_code_attempts": _SettingSpec(
            "confirmation_max_attempts",
            int,
            _as_int,
        ),
    },
    "gmail": {
        "enabled": _SettingSpec(
            "gmail_enabled", bool
        ),
        "credentials_file": _SettingSpec(
            "gmail_credentials", str, _as_path
        ),
        "token_file": _SettingSpec(
            "gmail_token", str, _as_path
        ),
        "user_id": _SettingSpec(
            "gmail_user_id", str
        ),
        "max_results": _SettingSpec(
            "gmail_max_results", int, _as_int
        ),
        "max_body_characters": _SettingSpec(
            "gmail_max_body_characters",
            int,
            _as_int,
        ),
        "oauth_port": _SettingSpec(
            "gmail_oauth_port", int, _as_int
        ),
        "open_browser_for_auth": _SettingSpec(
            "gmail_open_browser", bool
        ),
    },
    "google_calendar": {
        "enabled": _SettingSpec("google_calendar_enabled", bool),
        "credentials_file": _SettingSpec(
            "google_calendar_credentials", str, _as_path
        ),
        "token_file": _SettingSpec(
            "google_calendar_token", str, _as_path
        ),
        "default_calendar_id": _SettingSpec(
            "google_calendar_default_id", str
        ),
        "max_results": _SettingSpec(
            "google_calendar_max_results", int, _as_int
        ),
        "oauth_port": _SettingSpec(
            "google_calendar_oauth_port", int, _as_int
        ),
        "open_browser_for_auth": _SettingSpec(
            "google_calendar_open_browser", bool
        ),
        "allow_writes": _SettingSpec(
            "google_calendar_allow_writes", bool
        ),
    },
    "scheduler": {
        "enabled": _SettingSpec("scheduler_enabled", bool),
        "database": _SettingSpec("scheduler_database", str, _as_path),
        "poll_interval_seconds": _SettingSpec("scheduler_poll_interval", (int, float), _as_float),
        "max_tasks": _SettingSpec("scheduler_max_tasks", int, _as_int),
        "max_message_characters": _SettingSpec("scheduler_max_message_characters", int, _as_int),
        "announce_with_tts": _SettingSpec("scheduler_announce_tts", bool),
        "max_announcements_per_cycle": _SettingSpec("scheduler_max_announcements", int, _as_int),
    },
    "long_term_memory": {
        "enabled": _SettingSpec(
            "long_term_memory_enabled", bool
        ),
        "database": _SettingSpec(
            "memory_database", str, _as_path
        ),
        "context_limit": _SettingSpec(
            "memory_context_limit", int, _as_int
        ),
        "max_context_characters": _SettingSpec(
            "memory_context_characters", int, _as_int
        ),
        "max_entries": _SettingSpec(
            "memory_max_entries", int, _as_int
        ),
        "max_value_characters": _SettingSpec(
            "memory_max_value_characters", int, _as_int
        ),
    },
    "planning": {
        "enabled": _SettingSpec(
            "planning_enabled", bool
        ),
        "max_steps": _SettingSpec(
            "planning_max_steps", int, _as_int
        ),
        "max_repair_attempts": _SettingSpec(
            "planning_max_repair_attempts",
            int,
            _as_int,
        ),
    },
    "streaming": {
        "enabled": _SettingSpec(
            "streaming_enabled", bool
        ),
        "minimum_sentence_characters": _SettingSpec(
            "streaming_minimum_characters",
            int,
            _as_int,
        ),
        "maximum_chunk_characters": _SettingSpec(
            "streaming_maximum_characters",
            int,
            _as_int,
        ),
    },
    "conversation": {
        "enabled": _SettingSpec("continuous_conversation", bool),
        "followup_timeout_seconds": _SettingSpec(
            "followup_timeout", (int, float), _as_float
        ),
        "max_turns": _SettingSpec(
            "max_conversation_turns", int, _as_int
        ),
    },
    "browser": {
        "enabled": _SettingSpec("browser_automation", bool),
        "control_mode": _SettingSpec(
            "browser_control_mode", str
        ),
        "headless": _SettingSpec("browser_headless", bool),
        "browser": _SettingSpec(
            "browser_selection", str
        ),
        "executable_path": _SettingSpec(
            "browser_executable_path",
            str,
            _as_optional_path,
        ),
        "profile_directory": _SettingSpec(
            "browser_profile_dir", str, _as_path
        ),
        "navigation_timeout_seconds": _SettingSpec(
            "browser_navigation_timeout", (int, float), _as_float
        ),
        "action_timeout_seconds": _SettingSpec(
            "browser_action_timeout", (int, float), _as_float
        ),
        "max_page_text_characters": _SettingSpec(
            "browser_max_page_text", int, _as_int
        ),
    },
    "fast_path": {
        "enabled": _SettingSpec("fast_path_enabled", bool),
    },
    "barge_in": {
        "enabled": _SettingSpec("barge_in_enabled", bool),
        "vad_threshold": _SettingSpec(
            "barge_in_vad_threshold", (int, float), _as_float
        ),
        "grace_seconds": _SettingSpec(
            "barge_in_grace", (int, float), _as_float
        ),
        "trigger_speech_seconds": _SettingSpec(
            "barge_in_trigger_speech", (int, float), _as_float
        ),
        "end_silence_seconds": _SettingSpec(
            "barge_in_end_silence", (int, float), _as_float
        ),
        "max_utterance_seconds": _SettingSpec(
            "barge_in_max_utterance", (int, float), _as_float
        ),
        "pre_roll_seconds": _SettingSpec(
            "barge_in_pre_roll", (int, float), _as_float
        ),
        "minimum_rms": _SettingSpec(
            "barge_in_minimum_rms", (int, float), _as_float
        ),
    },
    "runtime": {
        "show_state_transitions": _SettingSpec(
            "show_state_transitions", bool
        ),
        "recovery_delay_seconds": _SettingSpec(
            "recovery_delay", (int, float), _as_float
        ),
    },
    "metrics": {
        "enabled": _SettingSpec("metrics_enabled", bool),
        "directory": _SettingSpec(
            "metrics_dir", str, _as_path
        ),
        "include_text": _SettingSpec(
            "metrics_include_text", bool
        ),
        "flush_each_event": _SettingSpec(
            "metrics_flush_each_event", bool
        ),
    },
}


def _load_toml(path: Path, *, required: bool) -> dict[str, Any]:
    if not path.is_file():
        if required:
            raise ConfigError(
                f"Config file does not exist: {path}"
            )
        return {}

    try:
        with path.open("rb") as file:
            data = tomllib.load(file)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(
            f"Invalid TOML in {path}: {exc}"
        ) from exc
    except OSError as exc:
        raise ConfigError(
            f"Could not read config file {path}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ConfigError(
            f"Config root must be a TOML table: {path}"
        )
    return data


def _merge_tables(
    base: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _merge_tables(current, value)
        else:
            merged[key] = value
    return merged


def _type_is_valid(value: Any, expected: type | tuple[type, ...]) -> bool:
    if expected is bool:
        return isinstance(value, bool)
    if expected is int:
        return isinstance(value, int) and not isinstance(value, bool)

    valid = isinstance(value, expected)
    expected_tuple = expected if isinstance(expected, tuple) else (expected,)
    if isinstance(value, bool) and bool not in expected_tuple:
        return False
    return valid


def _validate_and_map(data: dict[str, Any]) -> dict[str, Any]:
    unknown_sections = sorted(set(data) - set(_SCHEMA))
    if unknown_sections:
        raise ConfigError(
            "Unknown config section(s): "
            + ", ".join(unknown_sections)
        )

    defaults: dict[str, Any] = {}
    for section_name, section_value in data.items():
        if not isinstance(section_value, dict):
            raise ConfigError(
                f"Config section [{section_name}] must be a table."
            )

        section_schema = _SCHEMA[section_name]
        unknown_keys = sorted(
            set(section_value) - set(section_schema)
        )
        if unknown_keys:
            raise ConfigError(
                f"Unknown key(s) in [{section_name}]: "
                + ", ".join(unknown_keys)
            )

        for key, value in section_value.items():
            spec = section_schema[key]
            if not _type_is_valid(value, spec.expected_type):
                expected = (
                    ", ".join(
                        item.__name__
                        for item in spec.expected_type
                    )
                    if isinstance(spec.expected_type, tuple)
                    else spec.expected_type.__name__
                )
                raise ConfigError(
                    f"Invalid type for [{section_name}].{key}: "
                    f"expected {expected}, "
                    f"got {type(value).__name__}."
                )

            mapped = (
                spec.converter(value)
                if spec.converter is not None
                else value
            )
            defaults[spec.destination] = mapped

    _validate_values(defaults)
    return defaults


def _validate_values(values: dict[str, Any]) -> None:
    for name in (
        "wake_threshold",
        "vad_threshold",
        "barge_in_vad_threshold",
    ):
        if name in values and not 0.0 < values[name] < 1.0:
            raise ConfigError(
                f"{name} must be between 0 and 1."
            )

    positive = {
        "start_timeout",
        "end_silence",
        "max_command_seconds",
        "cooldown",
        "stt_beam_size",
        "stt_best_of",
        "stt_workers",
        "stt_cpu_threads",
        "llm_max_output_tokens",
        "llm_timeout",
        "llm_max_tool_rounds",
        "web_search_max_sources",
        "tts_max_characters",
        "tts_first_chunk_characters",
        "tts_chunk_characters",
        "tts_parallel_requests",
        "tts_mixer_buffer",
        "gmail_max_results",
        "gmail_max_body_characters",
        "google_calendar_max_results",
        "scheduler_poll_interval",
        "scheduler_max_tasks",
        "scheduler_max_message_characters",
        "scheduler_max_announcements",
        "memory_context_limit",
        "memory_context_characters",
        "memory_max_entries",
        "memory_max_value_characters",
        "planning_max_steps",
        "streaming_minimum_characters",
        "streaming_maximum_characters",
        "max_saved_audio_files",
        "followup_timeout",
        "max_conversation_turns",
        "browser_navigation_timeout",
        "browser_action_timeout",
        "browser_max_page_text",
        "barge_in_trigger_speech",
        "barge_in_end_silence",
        "barge_in_max_utterance",
        "barge_in_pre_roll",
    }
    for name in positive:
        if name in values and values[name] <= 0:
            raise ConfigError(f"{name} must be positive.")

    if (
        "planning_max_steps" in values
        and values["planning_max_steps"] < 2
    ):
        raise ConfigError(
            "planning_max_steps must be at least 2."
        )
    if values.get(
        "planning_max_repair_attempts",
        0,
    ) < 0:
        raise ConfigError(
            "planning_max_repair_attempts must not be negative."
        )

    if (
        "streaming_minimum_characters" in values
        and "streaming_maximum_characters" in values
        and values["streaming_minimum_characters"]
        > values["streaming_maximum_characters"]
    ):
        raise ConfigError(
            "streaming_minimum_characters must not exceed "
            "streaming_maximum_characters."
        )

    if values.get("recovery_delay", 0.0) < 0:
        raise ConfigError(
            "recovery_delay must not be negative."
        )

    if values.get("barge_in_grace", 0.0) < 0:
        raise ConfigError(
            "barge_in_grace must not be negative."
        )
    if values.get("barge_in_minimum_rms", 0.0) < 0:
        raise ConfigError(
            "barge_in_minimum_rms must not be negative."
        )

    choices: dict[str, set[str]] = {
        "stt_device": {"auto", "cuda", "cpu"},
        "llm_reasoning": {
            "none", "low", "medium", "high", "xhigh", "max"
        },
        "vision_detail": {
            "low", "high", "original", "auto"
        },
        "browser_control_mode": {"system", "automation"},
        "browser_selection": {
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
        },
    }
    for name, allowed in choices.items():
        if name in values and values[name] not in allowed:
            raise ConfigError(
                f"{name} must be one of: "
                + ", ".join(sorted(allowed))
            )

    browser_mode = values.get("browser_control_mode")
    browser_selection = values.get(
        "browser_selection"
    )
    if browser_mode == "system" and browser_selection == "chromium":
        raise ConfigError(
            "browser=chromium requires control_mode=automation."
        )
    browser_executable = values.get(
        "browser_executable_path"
    )
    if (
        browser_selection == "custom"
        and browser_executable is None
    ):
        raise ConfigError(
            "[browser].executable_path is required "
            "when browser='custom'."
        )
    if (
        browser_selection
        and browser_selection != "custom"
        and browser_executable is not None
    ):
        raise ConfigError(
            "[browser].executable_path is only valid "
            "when browser='custom'."
        )

    if "tts_rate" in values and not -100 <= values["tts_rate"] <= 100:
        raise ConfigError(
            "tts_rate must be between -100 and 100."
        )
    if (
        "tts_volume" in values
        and not 0 <= values["tts_volume"] <= 100
    ):
        raise ConfigError(
            "tts_volume must be between 0 and 100."
        )
    if (
        "tts_pitch" in values
        and not -100 <= values["tts_pitch"] <= 100
    ):
        raise ConfigError(
            "tts_pitch must be between -100 and 100."
        )


def load_settings(
    *,
    custom_path: Path | None = None,
    load_user: bool = True,
    default_path: Path | None = None,
    user_path: Path | None = None,
) -> LoadedSettings:
    project_root = _project_root()
    default_path = (
        default_path
        or project_root / "config" / "default.toml"
    )
    user_path = (
        user_path
        or project_root / "config" / "user.toml"
    )

    merged: dict[str, Any] = {}
    loaded_files: list[Path] = []

    sources: list[tuple[Path, bool]] = [
        (default_path, True)
    ]
    if load_user:
        sources.append((user_path, False))
    if custom_path is not None:
        custom = (
            custom_path
            if custom_path.is_absolute()
            else Path.cwd() / custom_path
        )
        sources.append((custom, True))

    for path, required in sources:
        resolved = path.resolve()
        data = _load_toml(resolved, required=required)
        if data:
            merged = _merge_tables(merged, data)
            loaded_files.append(resolved)

    return LoadedSettings(
        argument_defaults=_validate_and_map(merged),
        loaded_files=tuple(loaded_files),
    )
