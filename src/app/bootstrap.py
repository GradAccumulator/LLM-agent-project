from __future__ import annotations

import argparse

from src.audio import AudioConfig, MicrophoneStream
from src.bargein import (
    BargeInConfig,
    BargeInMonitor,
)
from src.browser import BrowserAutomationConfig
from src.edge_cdp import (
    EdgeCdpConfig,
    EdgeCdpController,
)
from src.conversation import ConversationConfig, ConversationSession
from src.console_io import ConsoleTextInput
from src.fastpath import FastPathConfig, LocalCommandRouter
from src.llm import AgentConfig, JarvisAgent
from src.model_routing import ModelRoutingConfig
from src.google_calendar import GoogleCalendarClient, GoogleCalendarConfig
from src.gmail import GmailClient, GmailConfig
from src.confirmation import ConfirmationConfig
from src.windows_uia import WindowsUiAutomation, WindowsUiAutomationConfig
from src.memory import (
    LocalMemoryStore,
    MemoryStoreConfig,
)
from src.metrics import JsonlMetricsLogger, MetricsConfig
from src.scheduler import (
    ReminderScheduler,
    ReminderSchedulerConfig,
    SchedulerStore,
    SchedulerStoreConfig,
)
from src.speech import (
    CaptureConfig,
    SpeechCapture,
    prune_wave_files,
)
from src.stt import (
    SpeechRecognizer,
    SpeechRecognizerConfig,
)
from src.tools import build_default_tool_registry
from src.tts import (
    SpeechSynthesizer,
    SpeechSynthesizerConfig,
)
from src.vad import (
    VoiceActivityConfig,
    VoiceActivityDetector,
)
from src.wakeword import (
    WakeWordConfig,
    WakeWordDetector,
)

from .runtime import (
    RuntimeConfig,
    VoiceAssistantRuntime,
)


def print_input_devices() -> int:
    print(MicrophoneStream.list_devices())
    return 0


def _tts_config(
    args: argparse.Namespace,
) -> SpeechSynthesizerConfig:
    return SpeechSynthesizerConfig(
        voice_name=args.tts_voice,
        rate=args.tts_rate,
        volume=args.tts_volume,
        pitch_hz=args.tts_pitch,
        max_characters=args.tts_max_characters,
        first_chunk_characters=(
            args.tts_first_chunk_characters
        ),
        chunk_characters=(
            args.tts_chunk_characters
        ),
        parallel_requests=(
            args.tts_parallel_requests
        ),
        mixer_buffer=args.tts_mixer_buffer,
    )


def print_tts_voices(
    args: argparse.Namespace,
) -> int:
    with SpeechSynthesizer(
        _tts_config(args)
    ) as synthesizer:
        print(
            synthesizer.format_available_voices()
        )
    return 0


def build_runtime(
    args: argparse.Namespace,
) -> VoiceAssistantRuntime:
    if args.save_audio:
        deleted_recordings = prune_wave_files(
            args.save_dir,
            max_files=args.max_saved_audio_files,
        )
        if deleted_recordings:
            print(
                f"Audio retention: deleted "
                f"{len(deleted_recordings)} old recording(s)."
            )

    microphone = MicrophoneStream(
        AudioConfig(
            device=args.device,
            preferred_device_name=(
                args.prefer_device
            ),
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
        VoiceActivityConfig(
            threshold=args.vad_threshold
        )
    )
    speech_capture = SpeechCapture(
        CaptureConfig(
            start_timeout_seconds=(
                args.start_timeout
            ),
            end_silence_seconds=(
                args.end_silence
            ),
            max_utterance_seconds=(
                args.max_command_seconds
            ),
        ),
        detector=vad,
    )

    print("Loading barge-in VAD...")
    barge_in_detector = VoiceActivityDetector(
        VoiceActivityConfig(
            threshold=args.barge_in_vad_threshold
        )
    )
    barge_in = BargeInMonitor(
        BargeInConfig(
            enabled=args.barge_in_enabled,
            grace_seconds=args.barge_in_grace,
            trigger_speech_seconds=(
                args.barge_in_trigger_speech
            ),
            end_silence_seconds=(
                args.barge_in_end_silence
            ),
            max_utterance_seconds=(
                args.barge_in_max_utterance
            ),
            pre_roll_seconds=args.barge_in_pre_roll,
            minimum_rms=args.barge_in_minimum_rms,
        ),
        detector=barge_in_detector,
    )

    print(
        f"Loading Faster-Whisper "
        f"'{args.stt_model}' "
        "(the first run may download "
        "the model)..."
    )
    recognizer = SpeechRecognizer(
        SpeechRecognizerConfig(
            model_size=args.stt_model,
            language=args.stt_language,
            device=args.stt_device,
            compute_type=(
                args.stt_compute_type
            ),
            beam_size=args.stt_beam_size,
            best_of=args.stt_best_of,
            download_root=args.stt_model_dir,
            cpu_threads=args.stt_cpu_threads,
            num_workers=args.stt_workers,
            warmup_seconds=(
                1.0
                if args.stt_warmup
                else 0.0
            ),
            without_timestamps=True,
        )
    )

    if args.stt_warmup:
        print(
            "Warming Faster-Whisper/CUDA..."
        )
        warmup_seconds = recognizer.warmup()
        print(
            "STT warm-up completed in "
            f"{warmup_seconds:.2f}s."
        )

    browser_config = BrowserAutomationConfig(
        enabled=args.browser_automation,
        headless=args.browser_headless,
        browser=args.browser_selection,
        executable_path=(
            args.browser_executable_path
        ),
        profile_directory=args.browser_profile_dir,
        navigation_timeout_seconds=(
            args.browser_navigation_timeout
        ),
        action_timeout_seconds=(
            args.browser_action_timeout
        ),
        max_page_text_characters=(
            args.browser_max_page_text
        ),
    )
    edge_cdp = EdgeCdpController(
        EdgeCdpConfig(
            enabled=args.edge_cdp_enabled,
            endpoint_url=(
                args.edge_cdp_endpoint
            ),
            connect_timeout_seconds=(
                args.edge_cdp_connect_timeout
            ),
            action_timeout_seconds=(
                args.edge_cdp_action_timeout
            ),
            max_page_text_characters=(
                args.edge_cdp_max_page_text
            ),
            tab_ref_ttl_seconds=(
                args.edge_cdp_tab_ttl
            ),
            screenshot_directory=(
                args.edge_cdp_screenshot_dir
            ),
            allow_tab_close=(
                args.edge_cdp_allow_tab_close
            ),
        )
    )

    windows_uia = WindowsUiAutomation(
        WindowsUiAutomationConfig(
            enabled=args.windows_uia_enabled,
            backend=args.windows_uia_backend,
            element_ttl_seconds=args.windows_uia_element_ttl,
            max_elements=args.windows_uia_max_elements,
            allow_actions=args.windows_uia_allow_actions,
            screenshot_directory=(
                args.windows_uia_screenshot_dir
            ),
        )
    )

    gmail_client = GmailClient(
        GmailConfig(
            enabled=args.gmail_enabled,
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

    google_calendar_client = GoogleCalendarClient(
        GoogleCalendarConfig(
            enabled=args.google_calendar_enabled,
            credentials_file=args.google_calendar_credentials,
            token_file=args.google_calendar_token,
            default_calendar_id=args.google_calendar_default_id,
            max_results=args.google_calendar_max_results,
            oauth_port=args.google_calendar_oauth_port,
            open_browser_for_auth=args.google_calendar_open_browser,
            allow_writes=(
                args.google_calendar_allow_writes
            ),
        )
    )
    scheduler_store = SchedulerStore(
        SchedulerStoreConfig(
            enabled=args.scheduler_enabled,
            database=args.scheduler_database,
            max_tasks=args.scheduler_max_tasks,
            max_message_characters=args.scheduler_max_message_characters,
        )
    )
    reminder_scheduler = ReminderScheduler(
        scheduler_store,
        ReminderSchedulerConfig(
            enabled=args.scheduler_enabled,
            poll_interval_seconds=args.scheduler_poll_interval,
        ),
    )

    memory_store = LocalMemoryStore(
        MemoryStoreConfig(
            enabled=args.long_term_memory_enabled,
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
    )
    tool_registry = build_default_tool_registry(
        browser_config=browser_config,
        browser_control_mode=args.browser_control_mode,
        memory_store=memory_store,
        scheduler_store=scheduler_store,
        google_calendar_client=google_calendar_client,
        gmail_client=gmail_client,
        windows_uia=windows_uia,
        edge_cdp=edge_cdp,
        confirmation_config=(
            ConfirmationConfig(
                enabled=(
                    args.confirmation_enabled
                ),
                timeout_seconds=(
                    args.confirmation_timeout
                ),
                high_risk_code_digits=(
                    args.confirmation_code_digits
                ),
                max_code_attempts=(
                    args.confirmation_max_attempts
                ),
            )
        ),
    )
    fast_router = LocalCommandRouter(
        tool_registry,
        FastPathConfig(
            enabled=(
                args.fast_path_enabled
                and args.tools_enabled
            )
        ),
    )

    print(
        f"Connecting GPT model "
        f"'{args.llm_model}'..."
    )
    agent = JarvisAgent(
        AgentConfig(
            model=args.llm_model,
            reasoning_effort=(
                args.llm_reasoning
            ),
            max_output_tokens=(
                args.llm_max_output_tokens
            ),
            timeout_seconds=args.llm_timeout,
            use_memory=args.llm_memory,
            max_tool_rounds=(
                args.llm_max_tool_rounds
            ),
            tools_enabled=(
                args.tools_enabled
            ),
            vision_detail=args.vision_detail,
            planning_enabled=args.planning_enabled,
            planning_max_steps=(
                args.planning_max_steps
            ),
            planning_max_repair_attempts=(
                args.planning_max_repair_attempts
            ),
            long_term_memory_enabled=(
                args.long_term_memory_enabled
            ),
            memory_context_limit=(
                args.memory_context_limit
            ),
            memory_context_characters=(
                args.memory_context_characters
            ),
            web_search_enabled=(
                args.web_search_enabled
            ),
            web_search_external_access=(
                args.web_search_external_access
            ),
            web_search_max_sources=(
                args.web_search_max_sources
            ),
            model_routing=(
                ModelRoutingConfig(
                    enabled=(
                        args.model_routing_enabled
                    ),
                    balanced_model=(
                        args.routing_balanced_model
                    ),
                    strong_model=(
                        args.routing_strong_model
                    ),
                    balanced_reasoning=(
                        args.routing_balanced_reasoning
                    ),
                    strong_reasoning=(
                        args.routing_strong_reasoning
                    ),
                    allow_user_override=(
                        args.routing_allow_user_override
                    ),
                    allow_automatic_escalation=(
                        args.routing_allow_automatic
                    ),
                    max_delegations_per_turn=(
                        args.routing_max_delegations
                    ),
                    max_input_characters=(
                        args.routing_max_input_characters
                    ),
                    max_output_tokens=(
                        args.routing_max_output_tokens
                    ),
                    timeout_seconds=(
                        args.routing_timeout
                    ),
                    fallback_to_default=(
                        args.routing_fallback
                    ),
                )
            ),
        ),
        tool_registry=tool_registry,
    )

    print(
        "Loading Microsoft Edge "
        "neural TTS..."
    )
    synthesizer = SpeechSynthesizer(
        _tts_config(args)
    )

    console_input = ConsoleTextInput()

    conversation = ConversationSession(
        ConversationConfig(
            enabled=args.continuous_conversation,
            followup_timeout_seconds=args.followup_timeout,
            max_turns=args.max_conversation_turns,
        )
    )

    metrics = JsonlMetricsLogger(
        MetricsConfig(
            enabled=args.metrics_enabled,
            directory=args.metrics_dir,
            include_text=(
                args.metrics_include_text
            ),
            flush_each_event=(
                args.metrics_flush_each_event
            ),
        )
    )

    language_text = (
        recognizer.language or "auto"
    )
    tools_text = (
        ", ".join(agent.tool_names)
        if agent.tool_names
        else "disabled"
    )

    print(
        f"Audio files    : keep newest "
        f"{args.max_saved_audio_files}"
    )
    print(
        f"Input device   : "
        f"[{microphone.device}] "
        f"{info['name']}"
    )
    print(
        f"Capture rate   : "
        f"{microphone.input_sample_rate} Hz"
    )
    print(
        "Pipeline audio : "
        "16000 Hz / mono / int16 / 80 ms"
    )
    print(
        f"Wake threshold : "
        f"{args.wake_threshold:.2f}"
    )
    print(
        f"VAD threshold  : "
        f"{args.vad_threshold:.2f}"
    )
    print(
        f"End silence    : "
        f"{args.end_silence:.2f} s"
    )
    print(
        f"STT model      : "
        f"{recognizer.model_name}"
    )
    print(
        f"STT runtime    : "
        f"{recognizer.device} / "
        f"{recognizer.compute_type}"
    )
    print(
        f"STT language   : "
        f"{language_text}"
    )
    print(
        f"STT beam       : "
        f"{args.stt_beam_size}"
    )
    print(
        f"STT best-of    : "
        f"{args.stt_best_of}"
    )
    print(
        f"STT warm-up    : "
        f"{'enabled' if args.stt_warmup else 'disabled'}"
    )
    print(
        f"LLM model      : "
        f"{args.llm_model}"
    )
    print(
        f"LLM reasoning  : "
        f"{args.llm_reasoning}"
    )
    print(
        f"Model routing : "
        f"{'enabled' if args.model_routing_enabled else 'disabled'}"
    )
    print(
        f"Route balanced: "
        f"{args.routing_balanced_model} / "
        f"{args.routing_balanced_reasoning}"
    )
    print(
        f"Route strong  : "
        f"{args.routing_strong_model} / "
        f"{args.routing_strong_reasoning}"
    )
    print(
        f"Route policy  : explicit="
        f"{args.routing_allow_user_override} / automatic="
        f"{args.routing_allow_automatic} / max="
        f"{args.routing_max_delegations}"
    )
    print(
        f"LLM memory     : "
        f"{'enabled' if args.llm_memory else 'disabled'}"
    )
    print(
        f"Vision detail  : "
        f"{args.vision_detail}"
    )
    print(
        f"Hosted search  : "
        f"{'enabled' if args.web_search_enabled else 'disabled'}"
    )
    print(
        f"Web access     : "
        f"{'live' if args.web_search_external_access else 'cache-only'}"
    )
    print(
        f"Local tools    : {tools_text}"
    )
    print(
        f"TTS voice      : "
        f"{synthesizer.selected_voice.name} "
        f"(locale="
        f"{synthesizer.selected_voice.language or '?'})"
    )
    print(
        "TTS backend    : "
        "Microsoft Edge neural TTS (online)"
    )
    print(
        f"TTS rate       : "
        f"{args.tts_rate:+d}%"
    )
    print(
        f"TTS volume     : "
        f"{args.tts_volume}"
    )
    print(
        f"TTS pitch      : "
        f"{args.tts_pitch:+d} Hz"
    )
    print(
        f"TTS output     : "
        f"{'enabled' if args.tts_enabled else 'disabled'}"
    )
    print(
        f"Edge CDP       : "
        f"{'enabled' if args.edge_cdp_enabled else 'disabled'} "
        f"({args.edge_cdp_endpoint})"
    )
    print(
        f"Edge tab close : "
        f"{'confirmed' if args.edge_cdp_allow_tab_close else 'disabled'}"
    )
    print(
        f"Windows UIA    : "
        f"{'enabled' if args.windows_uia_enabled else 'disabled'} / "
        f"{'actions' if args.windows_uia_allow_actions else 'read-only'}"
    )
    print(
        f"UIA ref TTL    : {args.windows_uia_element_ttl:.0f}s"
    )
    print(
        f"Confirmation   : "
        f"{'enabled' if args.confirmation_enabled else 'disabled'} "
        f"({args.confirmation_timeout:.0f}s timeout)"
    )
    print(
        "Protected tools: create_note, "
        "Calendar create/update/delete"
    )
    calendar_status = (
        google_calendar_client.status()
    )
    print(
        "Calendar scope : read + event write"
    )
    print(
        f"Calendar writes: "
        f"{'ready' if calendar_status['write_ready'] else 'reauth required'}"
    )
    print(
        f"Scheduler      : {'enabled' if args.scheduler_enabled else 'disabled'}"
    )
    print(
        f"Reminder DB    : {args.scheduler_database} ({scheduler_store.count_active()} active)"
    )
    print(
        f"Reminder TTS   : {'enabled' if args.scheduler_announce_tts else 'disabled'}"
    )
    print(
        f"Long memory   : "
        f"{'enabled' if args.long_term_memory_enabled else 'disabled'}"
    )
    print(
        f"Memory DB      : {args.memory_database} "
        f"({memory_store.count()} item(s))"
    )
    print(
        f"Task planning  : "
        f"{'enabled' if args.planning_enabled else 'disabled'}"
    )
    print(
        f"Plan limits    : "
        f"steps={args.planning_max_steps}, "
        f"repairs={args.planning_max_repair_attempts}"
    )
    print(
        f"LLM streaming  : "
        f"{'enabled' if args.streaming_enabled else 'disabled'}"
    )
    print(
        f"Stream chunks  : "
        f"min={args.streaming_minimum_characters}, "
        f"max={args.streaming_maximum_characters}"
    )
    print(
        "Console input  : enabled "
        "(type and press Enter; text replies are silent)"
    )
    print(
        f"Conversation   : "
        f"{'continuous' if args.continuous_conversation else 'wake word each turn'}"
    )
    print(f"Follow-up wait : {args.followup_timeout:.1f} s")
    print(f"Max turns      : {args.max_conversation_turns}")
    print(
        f"Browser tools  : "
        f"{'enabled' if args.browser_automation else 'disabled'} "
        f"({'headless' if args.browser_headless else 'headed'})"
    )
    print(
        f"Browser        : "
        f"{browser_config.display_name} "
        f"({browser_config.browser})"
    )
    print(
        f"Browser mode   : {args.browser_control_mode}"
    )
    print(
        f"Browser profile: "
        f"{browser_config.effective_profile_directory}"
    )
    print(
        f"Fast path      : "
        f"{'enabled' if args.fast_path_enabled and args.tools_enabled else 'disabled'}"
    )
    print(
        f"Barge-in       : "
        f"{'enabled' if args.barge_in_enabled else 'disabled'}"
    )
    print(
        f"Barge-in VAD   : "
        f"{args.barge_in_vad_threshold:.2f} "
        f"for {args.barge_in_trigger_speech:.2f}s"
    )
    print(
        f"State logging  : "
        f"{'visible' if args.show_state_transitions else 'hidden'}"
    )
    print(
        f"Metrics        : "
        f"{metrics.path if metrics.path else 'disabled'}"
    )

    metrics.log(
        "runtime_configured",
        data={
            "input_device": str(info["name"]),
            "capture_rate": (
                microphone.input_sample_rate
            ),
            "wake_threshold": (
                args.wake_threshold
            ),
            "vad_threshold": (
                args.vad_threshold
            ),
            "end_silence": args.end_silence,
            "stt_model": recognizer.model_name,
            "stt_device": recognizer.device,
            "stt_compute_type": (
                recognizer.compute_type
            ),
            "llm_model": args.llm_model,
            "tts_voice": (
                synthesizer.selected_voice.name
            ),
        },
    )

    return VoiceAssistantRuntime(
        config=RuntimeConfig(
            save_audio=args.save_audio,
            save_directory=args.save_dir,
            max_saved_audio_files=(
                args.max_saved_audio_files
            ),
            tts_enabled=args.tts_enabled,
            scheduler_announce_tts=args.scheduler_announce_tts,
            scheduler_max_announcements=args.scheduler_max_announcements,
            streaming_enabled=(
                args.streaming_enabled
            ),
            streaming_minimum_characters=(
                args.streaming_minimum_characters
            ),
            streaming_maximum_characters=(
                args.streaming_maximum_characters
            ),
            show_state_transitions=(
                args.show_state_transitions
            ),
            recovery_delay_seconds=(
                args.recovery_delay
            ),
        ),
        microphone=microphone,
        wakeword=wakeword,
        speech_capture=speech_capture,
        recognizer=recognizer,
        agent=agent,
        synthesizer=synthesizer,
        metrics=metrics,
        conversation=conversation,
        fast_router=fast_router,
        barge_in=barge_in,
        scheduler=reminder_scheduler,
        console_input=console_input,
    )
