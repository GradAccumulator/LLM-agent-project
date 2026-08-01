from __future__ import annotations

import argparse

from src.audio import AudioConfig, MicrophoneStream
from src.conversation import ConversationConfig, ConversationSession
from src.llm import AgentConfig, JarvisAgent
from src.metrics import JsonlMetricsLogger, MetricsConfig
from src.speech import (
    CaptureConfig,
    SpeechCapture,
    prune_wave_files,
)
from src.stt import (
    SpeechRecognizer,
    SpeechRecognizerConfig,
)
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
        )
    )

    print(
        "Loading Microsoft Edge "
        "neural TTS..."
    )
    synthesizer = SpeechSynthesizer(
        _tts_config(args)
    )

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
        f"LLM memory     : "
        f"{'enabled' if args.llm_memory else 'disabled'}"
    )
    print(
        f"Vision detail  : "
        f"{args.vision_detail}"
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
        f"Conversation   : "
        f"{'continuous' if args.continuous_conversation else 'wake word each turn'}"
    )
    print(f"Follow-up wait : {args.followup_timeout:.1f} s")
    print(f"Max turns      : {args.max_conversation_turns}")
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
    )
