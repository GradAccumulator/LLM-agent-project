from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import sys
from time import sleep

import numpy as np

from src.audio import MicrophoneStream
from src.core import AgentState, AgentStateMachine, StateTransition
from src.llm import JarvisAgent, ToolLifecycleEvent
from src.speech import CaptureResult, SpeechCapture, save_wave_file
from src.stt import SpeechRecognizer, TranscriptionResult
from src.tts import SpeechSynthesizer
from src.wakeword import DetectionResult, WakeWordDetector


_RESET_COMMANDS = {
    "대화초기화",
    "기억초기화",
    "대화리셋",
    "컨텍스트초기화",
}

_TTS_OFF_COMMANDS = {
    "tts끄기",
    "tts꺼",
    "tts꺼줘",
    "음성끄기",
    "음성꺼",
    "음성꺼줘",
    "음성출력끄기",
    "음성출력꺼줘",
}

_TTS_ON_COMMANDS = {
    "tts켜기",
    "tts켜",
    "tts켜줘",
    "음성켜기",
    "음성켜",
    "음성켜줘",
    "음성출력켜기",
    "음성출력켜줘",
}


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    save_audio: bool = True
    save_directory: Path = Path("recordings")
    tts_enabled: bool = True
    show_state_transitions: bool = True
    recovery_delay_seconds: float = 0.25


def normalize_local_command(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()


def normalized_rms(samples: np.ndarray) -> float:
    scaled = samples.astype(np.float32) / np.iinfo(np.int16).max
    return float(np.sqrt(np.mean(np.square(scaled, dtype=np.float32))))


def play_detection_sound() -> None:
    try:
        import winsound

        winsound.MessageBeep(winsound.MB_OK)
    except (ImportError, RuntimeError):
        print("\a", end="", flush=True)


def format_token_usage(
    input_tokens: int | None,
    output_tokens: int | None,
) -> str:
    if input_tokens is None and output_tokens is None:
        return "tokens=?"
    input_text = "?" if input_tokens is None else str(input_tokens)
    output_text = "?" if output_tokens is None else str(output_tokens)
    return f"{input_text}→{output_text} tokens"


class VoiceAssistantRuntime:
    def __init__(
        self,
        *,
        config: RuntimeConfig,
        microphone: MicrophoneStream,
        wakeword: WakeWordDetector,
        speech_capture: SpeechCapture,
        recognizer: SpeechRecognizer,
        agent: JarvisAgent,
        synthesizer: SpeechSynthesizer,
        state_machine: AgentStateMachine | None = None,
    ) -> None:
        if config.recovery_delay_seconds < 0:
            raise ValueError(
                "recovery_delay_seconds must not be negative."
            )

        self.config = config
        self.microphone = microphone
        self.wakeword = wakeword
        self.speech_capture = speech_capture
        self.recognizer = recognizer
        self.agent = agent
        self.synthesizer = synthesizer
        self.state = state_machine or AgentStateMachine()
        self.tts_enabled = config.tts_enabled

        if config.show_state_transitions:
            self.state.add_listener(self._print_state_transition)

    @staticmethod
    def _print_state_transition(event: StateTransition) -> None:
        print(
            f"[STATE] {event.previous.value} -> {event.current.value} "
            f"| {event.reason} "
            f"| previous={event.previous_state_seconds:.2f}s"
        )

    def _transition(self, target: AgentState, reason: str) -> None:
        self.state.transition(target, reason=reason)

    def _prepare_listening(self, reason: str) -> None:
        self.wakeword.reset()
        self.microphone.clear_pending()
        self._transition(AgentState.LISTENING, reason)
        print('\nSay "Hey Jarvis" for another command.\n')

    def _speak(self, text: str) -> bool:
        self._transition(AgentState.SPEAKING, "speaking response")
        try:
            self.synthesizer.speak(text)
            timing = self.synthesizer.last_timing
            print(
                f"TTS LATENCY: first_audio="
                f"{timing.first_audio_seconds:.2f}s | "
                f"chunks={timing.chunks} | "
                f"total={timing.total_seconds:.2f}s"
            )
            return True
        except RuntimeError as exc:
            print(f"TTS warning: {exc}", file=sys.stderr)
            return False

    def _on_tool_event(self, event: ToolLifecycleEvent) -> None:
        if event.phase == "started":
            self._transition(
                AgentState.EXECUTING_TOOL,
                f"tool started: {event.name}",
            )
            return

        if event.phase == "finished":
            status = "success" if event.success else "failed"
            self._transition(
                AgentState.THINKING,
                f"tool finished: {event.name} ({status})",
            )
            return

        raise ValueError(f"Unknown tool lifecycle phase: {event.phase}")

    def _wait_for_wakeword(self) -> DetectionResult:
        while True:
            frame = self.microphone.read(timeout=2.0)
            result = self.wakeword.predict(frame.samples)
            rms = normalized_rms(frame.samples)

            print(
                f"\rLISTENING wake={result.score:.3f} "
                f"rms={rms:.4f} device={self.microphone.device}      ",
                end="",
                flush=True,
            )

            if result.detected:
                return result

    def _capture(self, wake_result: DetectionResult) -> CaptureResult:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(
            f"\n[{timestamp}] WAKE WORD DETECTED | "
            f"phrase={wake_result.model_name} | "
            f"score={wake_result.score:.3f}"
        )
        self._transition(
            AgentState.CAPTURING,
            "wake word detected",
        )
        play_detection_sound()
        self.microphone.clear_pending()
        print("COMMAND: waiting for speech...")
        return self.speech_capture.capture(self.microphone)

    def _transcribe(
        self,
        capture: CaptureResult,
    ) -> TranscriptionResult:
        self._transition(
            AgentState.TRANSCRIBING,
            "speech capture completed",
        )
        print("TRANSCRIBING...", flush=True)
        return self.recognizer.transcribe(capture.samples)

    def _print_capture(self, capture: CaptureResult) -> None:
        print(
            "COMMAND CAPTURED | "
            f"duration={capture.duration_seconds:.2f}s | "
            f"peak VAD={capture.peak_probability:.3f} | "
            f"end={capture.end_reason}"
        )

        if self.config.save_audio:
            output_path = save_wave_file(
                capture.samples,
                directory=self.config.save_directory,
            )
            print(f"Saved: {output_path}")

    @staticmethod
    def _print_transcription(
        transcription: TranscriptionResult,
    ) -> str:
        confidence = transcription.language_probability * 100.0
        transcript_text = transcription.text.strip()
        shown_transcript = transcript_text or "<empty>"
        print(
            f"TRANSCRIPT [{transcription.language} "
            f"{confidence:.1f}% | "
            f"{transcription.inference_seconds:.2f}s]: "
            f"{shown_transcript}"
        )
        return transcript_text

    def _local_reply(self, text: str) -> None:
        print(f"JARVIS: {text}")
        if self.tts_enabled:
            self.tts_enabled = self._speak(text)

    def _handle_local_command(
        self,
        transcript_text: str,
    ) -> bool:
        normalized = normalize_local_command(transcript_text)

        if not transcript_text:
            self._local_reply("음성을 이해하지 못했습니다.")
            return True

        if normalized in _TTS_OFF_COMMANDS:
            message = "음성 출력을 끕니다."
            print(f"JARVIS: {message}")
            if self.tts_enabled:
                self._speak(message)
            self.tts_enabled = False
            return True

        if normalized in _TTS_ON_COMMANDS:
            self.tts_enabled = True
            self._local_reply("음성 출력을 켰습니다.")
            return True

        if normalized in _RESET_COMMANDS:
            self.agent.reset_conversation()
            self._local_reply("대화 기억을 초기화했습니다.")
            return True

        return False

    def _ask_agent(self, transcript_text: str) -> None:
        self._transition(AgentState.THINKING, "transcription ready")
        print("THINKING...", flush=True)
        reply = self.agent.ask(
            transcript_text,
            on_tool_event=self._on_tool_event,
        )

        for tool_call in reply.tool_calls:
            status = "success" if tool_call.success else "failed"
            print(f"TOOL {tool_call.name}({tool_call.arguments})")
            print(f"TOOL RESULT: {status}")
            if not tool_call.success:
                print(tool_call.output)

        usage_text = format_token_usage(
            reply.input_tokens,
            reply.output_tokens,
        )
        print(
            f"JARVIS [{reply.model} | "
            f"{reply.elapsed_seconds:.2f}s | "
            f"{usage_text} | "
            f"tools={len(reply.tool_calls)}]:"
        )
        print(reply.text)

        if self.tts_enabled:
            self.tts_enabled = self._speak(reply.text)

    def _run_command_cycle(self) -> None:
        wake_result = self._wait_for_wakeword()
        capture = self._capture(wake_result)

        if not capture.speech_detected:
            print(
                "COMMAND: no speech detected "
                f"(peak VAD={capture.peak_probability:.3f})."
            )
            self._prepare_listening("speech start timeout")
            return

        self._print_capture(capture)
        transcription = self._transcribe(capture)
        transcript_text = self._print_transcription(transcription)

        if self._handle_local_command(transcript_text):
            self._prepare_listening("local command completed")
            return

        self._ask_agent(transcript_text)
        self._prepare_listening("response completed")

    def _recover(self, error: BaseException) -> None:
        message = str(error).strip() or type(error).__name__

        if self.state.current is not AgentState.ERROR:
            self._transition(
                AgentState.ERROR,
                f"{type(error).__name__}: {message}",
            )

        print(
            f"\nRuntime error: {message}",
            file=sys.stderr,
        )
        self._transition(
            AgentState.RECOVERING,
            "resetting audio and model state",
        )

        self.wakeword.reset()
        self.speech_capture.detector.reset()
        self.microphone.clear_pending()

        if self.config.recovery_delay_seconds:
            sleep(self.config.recovery_delay_seconds)

        self._transition(
            AgentState.LISTENING,
            "recovery completed",
        )
        print('\nRecovered. Say "Hey Jarvis" again.\n')

    def run(self) -> int:
        try:
            with self.microphone:
                self._transition(
                    AgentState.LISTENING,
                    "startup completed",
                )
                print('Say "Hey Jarvis". Press Ctrl+C to stop.\n')

                while True:
                    try:
                        self._run_command_cycle()
                    except (TimeoutError, RuntimeError, ValueError) as exc:
                        self._recover(exc)

        except KeyboardInterrupt:
            print("\nStopped by user.")
            return 0
        finally:
            try:
                self.synthesizer.close()
            finally:
                self.state.stop(reason="runtime exited")

        return 0
