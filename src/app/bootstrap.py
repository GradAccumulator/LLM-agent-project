from __future__ import annotations

import argparse

from src.audio import AudioConfig, MicrophoneStream
from src.llm import AgentConfig, JarvisAgent
from src.speech import CaptureConfig, SpeechCapture
from src.stt import SpeechRecognizer, SpeechRecognizerConfig
from src.tts import SpeechSynthesizer, SpeechSynthesizerConfig
from src.vad import VoiceActivityConfig, VoiceActivityDetector
from src.wakeword import WakeWordConfig, WakeWordDetector

from .runtime import RuntimeConfig, VoiceAssistantRuntime


def print_input_devices() -> int:
    print(MicrophoneStream.list_devices())
    return 0


def print_tts_voices(args: argparse.Namespace) -> int:
    with SpeechSynthesizer(
        SpeechSynthesizerConfig(
            voice_name=args.tts_voice,
            rate=args.tts_rate,
            volume=args.tts_volume,
            pitch_hz=args.tts_pitch,
            max_characters=args.tts_max_characters,
            first_chunk_characters=args.tts_first_chunk_characters,
            chunk_characters=args.tts_chunk_characters,
            parallel_requests=args.tts_parallel_requests,
            mixer_buffer=args.tts_mixer_buffer,
        )
    ) as synthesizer:
        print(synthesizer.format_available_voices())
    return 0


def build_runtime(args: argparse.Namespace) -> VoiceAssistantRuntime:
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
            best_of=args.stt_best_of,
            download_root=args.stt_model_dir,
            cpu_threads=args.stt_cpu_threads,
            num_workers=args.stt_workers,
            warmup_seconds=(
                0.0 if args.disable_stt_warmup else 1.0
            ),
            without_timestamps=True,
        )
    )

    if args.disable_stt_warmup:
        warmup_seconds = 0.0
    else:
        print("Warming Faster-Whisper/CUDA...")
        warmup_seconds = recognizer.warmup()
        print(f"STT warm-up completed in {warmup_seconds:.2f}s.")

    print(f"Connecting GPT model '{args.llm_model}'...")
    agent = JarvisAgent(
        AgentConfig(
            model=args.llm_model,
            reasoning_effort=args.llm_reasoning,
            max_output_tokens=args.llm_max_output_tokens,
            timeout_seconds=args.llm_timeout,
            use_memory=not args.no_llm_memory,
            max_tool_rounds=args.llm_max_tool_rounds,
            tools_enabled=not args.disable_tools,
            vision_detail=args.vision_detail,
        )
    )

    print("Loading Microsoft Edge neural TTS...")
    synthesizer = SpeechSynthesizer(
        SpeechSynthesizerConfig(
            voice_name=args.tts_voice,
            rate=args.tts_rate,
            volume=args.tts_volume,
            pitch_hz=args.tts_pitch,
            max_characters=args.tts_max_characters,
            first_chunk_characters=args.tts_first_chunk_characters,
            chunk_characters=args.tts_chunk_characters,
            parallel_requests=args.tts_parallel_requests,
            mixer_buffer=args.tts_mixer_buffer,
        )
    )

    language_text = recognizer.language or "auto"
    memory_text = "enabled" if not args.no_llm_memory else "disabled"
    tools_text = (
        ", ".join(agent.tool_names) if agent.tool_names else "disabled"
    )

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
    print(f"STT beam       : {args.stt_beam_size}")
    print(f"STT best-of    : {args.stt_best_of}")
    print(
        f"STT warm-up    : "
        f"{'disabled' if args.disable_stt_warmup else 'enabled'}"
    )
    print(f"LLM model      : {args.llm_model}")
    print(f"LLM reasoning  : {args.llm_reasoning}")
    print(f"LLM memory     : {memory_text}")
    print(f"Vision detail  : {args.vision_detail}")
    print(f"Local tools    : {tools_text}")
    print(
        f"TTS voice      : {synthesizer.selected_voice.name} "
        f"(locale={synthesizer.selected_voice.language or '?'})"
    )
    print("TTS backend    : Microsoft Edge neural TTS (online)")
    print(f"TTS rate       : {args.tts_rate:+d}%")
    print(f"TTS volume     : {args.tts_volume}")
    print(f"TTS pitch      : {args.tts_pitch:+d} Hz")
    print(
        f"TTS chunking   : first={args.tts_first_chunk_characters}, "
        f"later={args.tts_chunk_characters}, "
        f"parallel={args.tts_parallel_requests}"
    )
    print(
        f"TTS output     : "
        f"{'disabled' if args.disable_tts else 'enabled'}"
    )
    print(
        f"State logging  : "
        f"{'hidden' if args.hide_state_transitions else 'visible'}"
    )

    return VoiceAssistantRuntime(
        config=RuntimeConfig(
            save_audio=not args.no_save_audio,
            save_directory=args.save_dir,
            tts_enabled=not args.disable_tts,
            show_state_transitions=not args.hide_state_transitions,
            recovery_delay_seconds=args.recovery_delay,
        ),
        microphone=microphone,
        wakeword=wakeword,
        speech_capture=speech_capture,
        recognizer=recognizer,
        agent=agent,
        synthesizer=synthesizer,
    )
