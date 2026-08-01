from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import sys
from time import perf_counter, sleep
from uuid import uuid4

import numpy as np

from src.audio import MicrophoneStream
from src.bargein import BargeInMonitor
from src.conversation import ConversationSession
from src.console_io import (
    ConsoleTextInput,
    print_numbered_reply,
)
from src.core import AgentState, AgentStateMachine, StateTransition
from src.fastpath import LocalCommandRouter
from src.llm import JarvisAgent, ToolLifecycleEvent
from src.metrics import JsonlMetricsLogger
from src.scheduler import ReminderScheduler
from src.speech import CaptureResult, SpeechCapture, save_wave_file
from src.stt import SpeechRecognizer, TranscriptionResult
from src.streaming import (
    IncrementalSentenceChunker,
    SentenceChunkerConfig,
)
from src.tts import (
    SpeechSynthesizer,
    SpeechTiming,
    StreamingSpeechSession,
)
from src.wakeword import DetectionResult, WakeWordDetector


_RESET_COMMANDS = {'대화초기화', '기억초기화', '대화리셋', '컨텍스트초기화'}
_SESSION_END_COMMANDS = {
    '그만', '대화종료', '대화끝', '자비스그만',
    '이제그만', '이제됐어', '됐어', '종료해',
}
_TTS_OFF_COMMANDS = {
    'tts끄기', 'tts꺼', 'tts꺼줘', '음성끄기', '음성꺼', '음성꺼줘',
    '음성출력끄기', '음성출력꺼줘',
}
_TTS_ON_COMMANDS = {
    'tts켜기', 'tts켜', 'tts켜줘', '음성켜기', '음성켜', '음성켜줘',
    '음성출력켜기', '음성출력켜줘',
}


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    save_audio: bool = True
    save_directory: Path = Path('recordings')
    max_saved_audio_files: int = 5
    tts_enabled: bool = True
    scheduler_announce_tts: bool = True
    scheduler_max_announcements: int = 3
    streaming_enabled: bool = True
    streaming_minimum_characters: int = 24
    streaming_maximum_characters: int = 160
    show_state_transitions: bool = True
    recovery_delay_seconds: float = 0.25


@dataclass(slots=True)
class _CommandTrace:
    command_id: str
    started_at: float
    wake_score: float | None
    conversation_id: str | None
    turn_index: int
    wakeword_required: bool
    input_source: str
    capture_audio_seconds: float | None = None
    stt_seconds: float | None = None
    llm_seconds: float | None = None
    llm_first_text_seconds: float | None = None
    tool_seconds: float = 0.0
    tool_count: int = 0
    tts_first_audio_seconds: float | None = None
    tts_total_seconds: float | None = None
    transcript: str | None = None
    reply: str | None = None


def normalize_local_command(value: str) -> str:
    return re.sub(r'[\W_]+', '', value, flags=re.UNICODE).casefold()


def normalized_rms(samples: np.ndarray) -> float:
    scaled = samples.astype(np.float32) / np.iinfo(np.int16).max
    return float(np.sqrt(np.mean(np.square(scaled, dtype=np.float32))))


def play_detection_sound() -> None:
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_OK)
    except (ImportError, RuntimeError):
        print('\a', end='', flush=True)


def format_token_usage(input_tokens: int | None, output_tokens: int | None) -> str:
    if input_tokens is None and output_tokens is None:
        return 'tokens=?'
    return f"{'?' if input_tokens is None else input_tokens}→{'?' if output_tokens is None else output_tokens} tokens"


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
        metrics: JsonlMetricsLogger,
        conversation: ConversationSession,
        fast_router: LocalCommandRouter,
        barge_in: BargeInMonitor,
        scheduler: ReminderScheduler,
        console_input: ConsoleTextInput,
        state_machine: AgentStateMachine | None = None,
    ) -> None:
        if config.recovery_delay_seconds < 0:
            raise ValueError('recovery_delay_seconds must not be negative.')
        self.config = config
        self.microphone = microphone
        self.wakeword = wakeword
        self.speech_capture = speech_capture
        self.recognizer = recognizer
        self.agent = agent
        self.synthesizer = synthesizer
        self.metrics = metrics
        self.conversation = conversation
        self.fast_router = fast_router
        self.barge_in = barge_in
        self.scheduler = scheduler
        self.console_input = console_input
        self.state = state_machine or AgentStateMachine()
        self.tts_enabled = config.tts_enabled
        self._active_command: _CommandTrace | None = None
        self._pending_barge_in_capture = None
        if config.show_state_transitions:
            self.state.add_listener(self._print_state_transition)
        if metrics.enabled:
            self.state.add_listener(metrics.log_state_transition)

    @staticmethod
    def _print_state_transition(event: StateTransition) -> None:
        print(
            f'[STATE] {event.previous.value} -> {event.current.value} '
            f'| {event.reason} | previous={event.previous_state_seconds:.2f}s'
        )

    def _transition(self, target: AgentState, reason: str) -> None:
        self.state.transition(target, reason=reason)

    def _start_conversation(self) -> None:
        conversation_id = self.conversation.start()
        self.metrics.log('conversation_started', data={
            'conversation_id': conversation_id,
            'continuous': self.conversation.config.enabled,
            'followup_timeout_seconds': self.conversation.config.followup_timeout_seconds,
            'max_turns': self.conversation.config.max_turns,
        })

    def _end_conversation(self, reason: str) -> None:
        if not self.conversation.active:
            return
        snapshot = self.conversation.end()
        self.metrics.log('conversation_ended', data={
            'conversation_id': snapshot.session_id,
            'reason': reason,
            'turn_count': snapshot.turn_count,
            'elapsed_seconds': snapshot.elapsed_seconds,
        })

    def _start_command(
        self,
        *,
        wake_score: float | None,
        wakeword_required: bool,
        input_source: str = "voice",
    ) -> None:
        trace = _CommandTrace(
            command_id=uuid4().hex,
            started_at=perf_counter(),
            wake_score=wake_score,
            conversation_id=self.conversation.session_id,
            turn_index=self.conversation.next_turn_index,
            wakeword_required=wakeword_required,
            input_source=input_source,
        )
        self._active_command = trace
        self.metrics.log('command_started', data={
            'command_id': trace.command_id,
            'conversation_id': trace.conversation_id,
            'turn_index': trace.turn_index,
            'wake_score': trace.wake_score,
            'wakeword_required': trace.wakeword_required,
            'input_source': trace.input_source,
        })

    def _finish_command(self, outcome: str) -> None:
        trace = self._active_command
        if trace is None:
            return
        self.metrics.log('command_completed', data={
            'command_id': trace.command_id,
            'conversation_id': trace.conversation_id,
            'turn_index': trace.turn_index,
            'wakeword_required': trace.wakeword_required,
            'input_source': trace.input_source,
            'outcome': outcome,
            'total_seconds': round(perf_counter() - trace.started_at, 6),
            'capture_audio_seconds': trace.capture_audio_seconds,
            'stt_seconds': trace.stt_seconds,
            'llm_seconds': trace.llm_seconds,
            'llm_first_text_seconds': (
                trace.llm_first_text_seconds
            ),
            'tool_seconds': round(trace.tool_seconds, 6),
            'tool_count': trace.tool_count,
            'tts_first_audio_seconds': trace.tts_first_audio_seconds,
            'tts_total_seconds': trace.tts_total_seconds,
        }, private={'transcript': trace.transcript, 'reply': trace.reply})
        self._active_command = None

    def _return_to_sleep(self, *, reason: str, conversation_end_reason: str) -> None:
        self._end_conversation(conversation_end_reason)
        self.wakeword.reset()
        self.microphone.clear_pending()
        self._transition(AgentState.SLEEPING, reason)
        print('\nSay "Hey Jarvis" to start a new conversation.\n')

    def _continue_conversation(self, *, reason: str) -> None:
        self.wakeword.reset()
        self.microphone.clear_pending()
        self._transition(AgentState.AWAITING_SPEECH, reason)
        timeout = self.conversation.config.followup_timeout_seconds
        print(f'\nFOLLOW-UP: listening for {timeout:.1f}s. Say "대화 종료" to stop.\n')
        self.metrics.log('followup_listening_started', data={
            'conversation_id': self.conversation.session_id,
            'next_turn_index': self.conversation.next_turn_index,
            'timeout_seconds': timeout,
        })

    def _take_pending_barge_in_capture(self):
        pending = self._pending_barge_in_capture
        self._pending_barge_in_capture = None
        if pending is not None:
            return pending

        # The trigger callback changes state to CAPTURING immediately, while
        # the monitor may need a little longer to finish the user's utterance.
        if (
            self.state.current is not AgentState.CAPTURING
            or not self.barge_in.triggered
        ):
            return None

        wait_timeout = (
            self.barge_in.config.max_utterance_seconds
            + self.barge_in.config.end_silence_seconds
            + 2.0
        )
        result = self.barge_in.wait_for_result(
            timeout=wait_timeout
        )
        if result is None:
            self.barge_in.stop(timeout=1.0)
            raise RuntimeError(
                "Barge-in was triggered, but the captured "
                "utterance was not ready before turn finalization."
            )

        self.metrics.log(
            "barge_in_captured",
            data={
                "command_id": (
                    self._active_command.command_id
                    if self._active_command
                    else None
                ),
                "conversation_id": (
                    self.conversation.session_id
                ),
                "trigger_latency_seconds": (
                    result.trigger_latency_seconds
                ),
                "duration_seconds": (
                    result.capture.duration_seconds
                ),
                "peak_probability": (
                    result.capture.peak_probability
                ),
                "end_reason": (
                    result.capture.end_reason
                ),
                "late_collection": True,
            },
        )
        return result.capture

    def _roll_over_conversation_for_barge_in(
        self,
        *,
        previous_conversation_id: str | None,
    ) -> None:
        self._end_conversation(
            "barge_in_at_turn_limit"
        )
        self._start_conversation()
        self.metrics.log(
            "conversation_rolled_over",
            data={
                "previous_conversation_id": (
                    previous_conversation_id
                ),
                "conversation_id": (
                    self.conversation.session_id
                ),
                "reason": "barge_in_at_turn_limit",
            },
        )

    def _after_turn(self, *, outcome: str) -> None:
        pending_barge_in = (
            self._take_pending_barge_in_capture()
        )

        self._finish_command(outcome)
        completed_turn = self.conversation.complete_turn()
        snapshot = self.conversation.snapshot()
        self.metrics.log(
            "conversation_turn_completed",
            data={
                "conversation_id": (
                    self.conversation.session_id
                ),
                "turn_index": completed_turn,
                "remaining_turns": (
                    snapshot.remaining_turns
                ),
            },
        )

        # A captured interruption always wins over normal idle or turn-limit
        # handling. Never discard it because the previous session became full.
        if pending_barge_in is not None:
            rolled_over = snapshot.remaining_turns <= 0
            if rolled_over:
                self._roll_over_conversation_for_barge_in(
                    previous_conversation_id=(
                        snapshot.session_id
                    )
                )

            self._start_command(
                wake_score=None,
                wakeword_required=False,
            )
            if self._active_command is not None:
                self._active_command.capture_audio_seconds = (
                    pending_barge_in.duration_seconds
                )

            self.metrics.log(
                "barge_in_command_started",
                data={
                    "conversation_id": (
                        self.conversation.session_id
                    ),
                    "turn_index": (
                        self.conversation.next_turn_index
                    ),
                    "duration_seconds": (
                        pending_barge_in.duration_seconds
                    ),
                    "peak_probability": (
                        pending_barge_in.peak_probability
                    ),
                    "rolled_over": rolled_over,
                },
            )
            print(
                "BARGE-IN: processing the interruption now."
            )

            # State remains CAPTURING from the trigger callback.
            # _process_capture performs CAPTURING -> TRANSCRIBING.
            self._process_capture(pending_barge_in)
            return

        if self.conversation.can_accept_followup:
            self._continue_conversation(
                reason="awaiting follow-up command"
            )
            return

        reason = (
            "continuous conversation disabled"
            if not self.conversation.config.enabled
            else "maximum turns reached"
        )
        self._return_to_sleep(
            reason=reason,
            conversation_end_reason=reason,
        )

    def _on_barge_in_trigger(self) -> None:
        self.synthesizer.stop()
        if self.state.current is AgentState.SPEAKING:
            self._transition(
                AgentState.CAPTURING,
                'user interrupted TTS',
            )
        print('\nBARGE-IN: voice detected, stopping TTS...')

    def _speak(self, text: str) -> bool:
        self._transition(
            AgentState.SPEAKING,
            'speaking response',
        )
        monitor_started = False
        self._pending_barge_in_capture = None

        try:
            if self.barge_in.config.enabled:
                self.microphone.clear_pending()
                self.barge_in.start(
                    self.microphone,
                    on_trigger=self._on_barge_in_trigger,
                )
                monitor_started = True

            self.synthesizer.speak(text)
            timing = self.synthesizer.last_timing

            if monitor_started:
                if self.barge_in.triggered:
                    wait_timeout = (
                        self.barge_in.config.max_utterance_seconds
                        + self.barge_in.config.end_silence_seconds
                        + 2.0
                    )
                    result = self.barge_in.wait_for_result(
                        timeout=wait_timeout
                    )
                    if result is None:
                        self.barge_in.stop(timeout=1.0)
                        raise RuntimeError(
                            'Barge-in capture did not finish in time.'
                        )
                    self._pending_barge_in_capture = (
                        result.capture
                    )
                    self.metrics.log(
                        'barge_in_captured',
                        data={
                            'command_id': (
                                self._active_command.command_id
                                if self._active_command
                                else None
                            ),
                            'conversation_id': (
                                self.conversation.session_id
                            ),
                            'trigger_latency_seconds': (
                                result.trigger_latency_seconds
                            ),
                            'duration_seconds': (
                                result.capture.duration_seconds
                            ),
                            'peak_probability': (
                                result.capture.peak_probability
                            ),
                            'end_reason': (
                                result.capture.end_reason
                            ),
                        },
                    )
                else:
                    self.barge_in.stop(timeout=1.0)

            trace = self._active_command
            if trace is not None:
                trace.tts_first_audio_seconds = (
                    timing.first_audio_seconds
                )
                trace.tts_total_seconds = timing.total_seconds

            self.metrics.log('tts_completed', data={
                'command_id': (
                    trace.command_id
                    if trace is not None
                    else None
                ),
                'conversation_id': self.conversation.session_id,
                'first_audio_seconds': timing.first_audio_seconds,
                'chunks': timing.chunks,
                'requested_chunks': timing.requested_chunks,
                'total_seconds': timing.total_seconds,
                'interrupted': timing.interrupted,
            })
            print(
                f'TTS LATENCY: first_audio='
                f'{timing.first_audio_seconds:.2f}s '
                f'| chunks={timing.chunks}/'
                f'{timing.requested_chunks} '
                f'| total={timing.total_seconds:.2f}s '
                f'| interrupted={timing.interrupted}'
            )
            return True
        except RuntimeError as exc:
            if monitor_started:
                try:
                    self.barge_in.stop(timeout=1.0)
                except RuntimeError:
                    pass
            self.metrics.log('tts_failed', data={
                'command_id': (
                    self._active_command.command_id
                    if self._active_command
                    else None
                ),
                'error_type': type(exc).__name__,
                'error': str(exc),
            })
            print(f'TTS warning: {exc}', file=sys.stderr)
            return False

    def _on_tool_event(self, event: ToolLifecycleEvent) -> None:
        trace = self._active_command
        command_id = trace.command_id if trace else None
        if event.phase == 'started':
            self.metrics.log('tool_started', data={
                'command_id': command_id,
                'conversation_id': self.conversation.session_id,
                'tool': event.name,
            })
            self._transition(AgentState.EXECUTING_TOOL, f'tool started: {event.name}')
            return
        if event.phase == 'finished':
            if trace is not None:
                trace.tool_count += 1
                trace.tool_seconds += event.elapsed_seconds or 0.0
            status = 'success' if event.success else 'failed'
            self.metrics.log('tool_finished', data={
                'command_id': command_id,
                'conversation_id': self.conversation.session_id,
                'tool': event.name,
                'success': event.success,
                'elapsed_seconds': event.elapsed_seconds,
                'verified': event.verified,
                'verification': event.verification,
                'plan_progress': event.plan_progress,
            })
            self._transition(AgentState.THINKING, f'tool finished: {event.name} ({status})')
            return
        raise ValueError(f'Unknown tool lifecycle phase: {event.phase}')

    def _announce_due_reminder(self, reminder) -> None:
        task = reminder.task
        text = f"알림입니다. {task.message}"
        print("\n" + "=" * 60)
        print(f"REMINDER #{task.id}: {task.message}")
        print("=" * 60)
        play_detection_sound()
        self.metrics.log(
            "reminder_delivered",
            data={
                "task_id": task.id,
                "due_at": reminder.due_at,
                "claimed_at": reminder.claimed_at,
                "late_seconds": reminder.late_seconds,
                "recurrence": task.recurrence,
                "interval": task.interval,
            },
            private={"reminder_message": task.message},
        )
        if not self.tts_enabled or not self.config.scheduler_announce_tts:
            return
        self._transition(AgentState.SPEAKING, "scheduled reminder")
        try:
            self.synthesizer.speak(text)
        except RuntimeError as exc:
            print(f"Reminder TTS warning: {exc}", file=sys.stderr)
        finally:
            self._transition(AgentState.SLEEPING, "scheduled reminder delivered")
            self.microphone.clear_pending()

    def _deliver_due_reminders(self) -> int:
        if self.state.current is not AgentState.SLEEPING:
            return 0
        reminders = self.scheduler.drain(limit=self.config.scheduler_max_announcements)
        for reminder in reminders:
            self._announce_due_reminder(reminder)
        return len(reminders)

    def _wait_for_wakeword(
        self,
    ) -> DetectionResult | None:
        while True:
            self._deliver_due_reminders()
            if self.console_input.has_pending():
                return None
            try:
                frame = self.microphone.read(
                    timeout=0.25
                )
            except TimeoutError:
                continue
            if self.console_input.has_pending():
                return None
            result = self.wakeword.predict(
                frame.samples
            )
            if result.detected:
                return result

    def _on_speech_start(self) -> None:
        self._transition(AgentState.CAPTURING, 'speech detected')
        print('COMMAND: speech detected.')

    def _capture_after_wakeword(self, wake_result: DetectionResult) -> CaptureResult:
        self._start_conversation()
        self._start_command(wake_score=wake_result.score, wakeword_required=True)
        timestamp = datetime.now().strftime('%H:%M:%S')
        print(
            f'\n[{timestamp}] WAKE WORD DETECTED | phrase={wake_result.model_name} '
            f'| score={wake_result.score:.3f}'
        )
        self._transition(AgentState.AWAITING_SPEECH, 'wake word detected')
        play_detection_sound()
        self.microphone.clear_pending()
        print('COMMAND: waiting for speech...')
        return self.speech_capture.capture(
            self.microphone,
            on_speech_start=self._on_speech_start,
            should_cancel=(
                self.console_input.has_pending
            ),
        )

    def _capture_followup(self) -> CaptureResult:
        self._start_command(wake_score=None, wakeword_required=False)
        return self.speech_capture.capture(
            self.microphone,
            start_timeout_seconds=self.conversation.config.followup_timeout_seconds,
            on_speech_start=self._on_speech_start,
            should_cancel=(
                self.console_input.has_pending
            ),
        )

    def _transcribe(self, capture: CaptureResult) -> TranscriptionResult:
        self._transition(AgentState.TRANSCRIBING, 'speech capture completed')
        print('TRANSCRIBING...', flush=True)
        transcription = self.recognizer.transcribe(capture.samples)
        text = transcription.text.strip()
        if self._active_command is not None:
            self._active_command.stt_seconds = transcription.inference_seconds
            self._active_command.transcript = text
        self.metrics.log('transcription_completed', data={
            'command_id': self._active_command.command_id if self._active_command else None,
            'conversation_id': self.conversation.session_id,
            'language': transcription.language,
            'language_probability': transcription.language_probability,
            'inference_seconds': transcription.inference_seconds,
            'text_characters': len(text),
        }, private={'transcript': text})
        return transcription

    def _print_capture(self, capture: CaptureResult) -> None:
        print(
            f'COMMAND CAPTURED | duration={capture.duration_seconds:.2f}s '
            f'| peak VAD={capture.peak_probability:.3f} | end={capture.end_reason}'
        )
        if self.config.save_audio:
            output_path = save_wave_file(
                capture.samples,
                directory=self.config.save_directory,
                max_saved_files=self.config.max_saved_audio_files,
            )
            print(f'Saved: {output_path}')

    @staticmethod
    def _print_transcription(transcription: TranscriptionResult) -> str:
        confidence = transcription.language_probability * 100.0
        text = transcription.text.strip()
        print(
            f'TRANSCRIPT [{transcription.language} {confidence:.1f}% '
            f'| {transcription.inference_seconds:.2f}s]: {text or "<empty>"}'
        )
        return text

    def _local_reply(
        self,
        text: str,
        *,
        speak_response: bool,
    ) -> None:
        if self._active_command is not None:
            self._active_command.reply = text
        print_numbered_reply(text)
        if speak_response and self.tts_enabled:
            self.tts_enabled = self._speak(text)

    def _handle_local_command(
        self,
        transcript_text: str,
        *,
        speak_response: bool,
    ) -> str | None:
        normalized = normalize_local_command(transcript_text)
        if not transcript_text:
            self._local_reply(
                '입력을 이해하지 못했습니다.',
                speak_response=speak_response,
            )
            return 'local_command'
        if normalized in _SESSION_END_COMMANDS:
            self._local_reply(
                '대화 모드를 종료합니다.',
                speak_response=speak_response,
            )
            return 'end_session'
        if normalized in _TTS_OFF_COMMANDS:
            message = '음성 출력을 끕니다.'
            if self._active_command is not None:
                self._active_command.reply = message
            print(f'JARVIS: {message}')
            print_numbered_reply(message)
            if speak_response and self.tts_enabled:
                self._speak(message)
            self.tts_enabled = False
            return 'local_command'
        if normalized in _TTS_ON_COMMANDS:
            self.tts_enabled = True
            self._local_reply(
                '음성 출력을 켰습니다.',
                speak_response=speak_response,
            )
            return 'local_command'
        if normalized in _RESET_COMMANDS:
            self.agent.reset_conversation()
            self._local_reply(
                '대화 기억을 초기화했습니다.',
                speak_response=speak_response,
            )
            return 'local_command'
        return None

    def _try_fast_path(
        self,
        transcript_text: str,
        *,
        speak_response: bool,
    ) -> bool:
        result = self.fast_router.try_execute(
            transcript_text,
            on_match=lambda route: self._transition(
                AgentState.EXECUTING_TOOL,
                f"fast path: {route}",
            ),
        )
        if result is None:
            return False

        trace = self._active_command
        if trace is not None:
            trace.tool_count += len(result.tool_calls)
            trace.tool_seconds += sum(
                call.elapsed_seconds
                for call in result.tool_calls
            )
            trace.reply = result.reply

        for call in result.tool_calls:
            status = "success" if call.success else "failed"
            print(
                f"FAST TOOL {call.name}({call.arguments}) "
                f"-> {status} ({call.elapsed_seconds:.3f}s)"
            )

        self.metrics.log(
            "fast_path_completed",
            data={
                "command_id": (
                    trace.command_id if trace else None
                ),
                "conversation_id": self.conversation.session_id,
                "route": result.route,
                "success": result.success,
                "elapsed_seconds": result.elapsed_seconds,
                "tool_count": len(result.tool_calls),
                "gpt_bypassed": True,
            },
            private={"reply": result.reply},
        )
        print(
            f"FAST PATH [{result.route} | "
            f"{result.elapsed_seconds:.3f}s | GPT bypassed]"
        )
        self._local_reply(
            result.reply,
            speak_response=speak_response,
        )
        return True


    def _log_agent_reply(self, reply) -> None:
        trace = self._active_command
        if trace is not None:
            trace.llm_seconds = reply.elapsed_seconds
            trace.llm_first_text_seconds = (
                reply.first_text_seconds
            )
            trace.reply = reply.text

        for tool_call in reply.tool_calls:
            status = (
                "success"
                if tool_call.success
                else "failed"
            )
            print(
                f"TOOL {tool_call.name}"
                f"({tool_call.arguments})"
            )
            print(
                f"TOOL RESULT: {status} "
                f"({tool_call.elapsed_seconds:.3f}s)"
            )
            if tool_call.verified is not None:
                verification_status = (
                    "verified"
                    if tool_call.verified
                    else "not verified"
                )
                print(
                    f"VERIFY: {verification_status}"
                )
            if tool_call.plan_progress is not None:
                progress = tool_call.plan_progress
                print(
                    "PLAN: "
                    f"{progress.get('status')} "
                    f"{progress.get('completed_steps')}/"
                    f"{progress.get('total_steps')} "
                    f"| current={progress.get('current_step')}"
                )
            if not tool_call.success:
                print(tool_call.output)

        usage_text = format_token_usage(
            reply.input_tokens,
            reply.output_tokens,
        )
        first_text = (
            "?"
            if reply.first_text_seconds is None
            else f"{reply.first_text_seconds:.2f}s"
        )
        print(
            f"JARVIS META [{reply.model} | "
            f"first_text={first_text} | "
            f"total={reply.elapsed_seconds:.2f}s | "
            f"{usage_text} | "
            f"tools={len(reply.tool_calls)}]"
        )

        plan = reply.plan_snapshot
        if reply.planning_required and plan is not None:
            print(
                "TASK PLAN: "
                f"{plan.get('status')} "
                f"{plan.get('completed_steps')}/"
                f"{plan.get('total_steps')}"
            )

        self.metrics.log(
            "llm_completed",
            data={
                "command_id": (
                    trace.command_id
                    if trace
                    else None
                ),
                "conversation_id": (
                    self.conversation.session_id
                ),
                "model": reply.model,
                "elapsed_seconds": (
                    reply.elapsed_seconds
                ),
                "first_text_seconds": (
                    reply.first_text_seconds
                ),
                "input_tokens": reply.input_tokens,
                "output_tokens": (
                    reply.output_tokens
                ),
                "total_tokens": reply.total_tokens,
                "tool_count": len(reply.tool_calls),
                "reply_characters": len(reply.text),
                "streaming": (
                    self.config.streaming_enabled
                ),
                "planning_required": (
                    reply.planning_required
                ),
                "plan_status": (
                    reply.plan_snapshot.get("status")
                    if reply.plan_snapshot
                    else None
                ),
                "plan_completed_steps": (
                    reply.plan_snapshot.get(
                        "completed_steps"
                    )
                    if reply.plan_snapshot
                    else None
                ),
                "plan_total_steps": (
                    reply.plan_snapshot.get(
                        "total_steps"
                    )
                    if reply.plan_snapshot
                    else None
                ),
            },
            private={"reply": reply.text},
        )

    def _settle_stream_barge_in(
        self,
        *,
        monitor_started: bool,
    ) -> None:
        if not monitor_started:
            return

        if self.barge_in.triggered:
            wait_timeout = (
                self.barge_in.config.max_utterance_seconds
                + self.barge_in.config.end_silence_seconds
                + 2.0
            )
            result = self.barge_in.wait_for_result(
                timeout=wait_timeout
            )
            if result is None:
                self.barge_in.stop(timeout=1.0)
                raise RuntimeError(
                    "Barge-in capture did not finish in time."
                )

            self._pending_barge_in_capture = (
                result.capture
            )
            self.metrics.log(
                "barge_in_captured",
                data={
                    "command_id": (
                        self._active_command.command_id
                        if self._active_command
                        else None
                    ),
                    "conversation_id": (
                        self.conversation.session_id
                    ),
                    "trigger_latency_seconds": (
                        result.trigger_latency_seconds
                    ),
                    "duration_seconds": (
                        result.capture.duration_seconds
                    ),
                    "peak_probability": (
                        result.capture.peak_probability
                    ),
                    "end_reason": (
                        result.capture.end_reason
                    ),
                    "during_streaming": True,
                },
            )
        else:
            self.barge_in.stop(timeout=1.0)

    def _record_stream_timing(
        self,
        timing: SpeechTiming,
    ) -> None:
        trace = self._active_command
        if trace is not None:
            trace.tts_first_audio_seconds = (
                timing.first_audio_seconds
            )
            trace.tts_total_seconds = (
                timing.total_seconds
            )

        self.metrics.log(
            "streaming_tts_completed",
            data={
                "command_id": (
                    trace.command_id
                    if trace
                    else None
                ),
                "conversation_id": (
                    self.conversation.session_id
                ),
                "first_audio_seconds": (
                    timing.first_audio_seconds
                ),
                "chunks": timing.chunks,
                "requested_chunks": (
                    timing.requested_chunks
                ),
                "total_seconds": timing.total_seconds,
                "interrupted": timing.interrupted,
            },
        )
        print(
            "STREAM TTS: first_audio="
            f"{timing.first_audio_seconds:.2f}s "
            f"| chunks={timing.chunks}/"
            f"{timing.requested_chunks} "
            f"| total={timing.total_seconds:.2f}s "
            f"| interrupted={timing.interrupted}"
        )

    def _ask_agent_buffered(
        self,
        transcript_text: str,
        *,
        speak_response: bool,
    ) -> None:
        self._transition(
            AgentState.THINKING,
            "transcription ready",
        )
        print("THINKING...", flush=True)
        reply = self.agent.ask(
            transcript_text,
            on_tool_event=self._on_tool_event,
        )
        print_numbered_reply(reply.text)
        self._log_agent_reply(reply)
        if speak_response and self.tts_enabled:
            self.tts_enabled = self._speak(
                reply.text
            )

    def _ask_agent_streaming(
        self,
        transcript_text: str,
        *,
        speak_response: bool,
    ) -> None:
        self._transition(
            AgentState.THINKING,
            "transcription ready",
        )
        print("THINKING (streaming)...", flush=True)

        chunker = IncrementalSentenceChunker(
            SentenceChunkerConfig(
                minimum_characters=(
                    self.config
                    .streaming_minimum_characters
                ),
                maximum_characters=(
                    self.config
                    .streaming_maximum_characters
                ),
            )
        )
        session: StreamingSpeechSession | None = None
        monitor_started = False

        def start_audio_stream() -> (
            StreamingSpeechSession
        ):
            nonlocal session, monitor_started
            if session is not None:
                return session

            if self.state.current is not AgentState.SPEAKING:
                self._transition(
                    AgentState.SPEAKING,
                    "streaming first sentence",
                )

            self._pending_barge_in_capture = None
            if self.barge_in.config.enabled:
                self.microphone.clear_pending()
                self.barge_in.start(
                    self.microphone,
                    on_trigger=(
                        self._on_barge_in_trigger
                    ),
                )
                monitor_started = True

            session = self.synthesizer.start_stream()
            return session

        def enqueue_chunks(
            chunks: tuple[str, ...],
        ) -> None:
            if (
                not chunks
                or not speak_response
                or not self.tts_enabled
            ):
                return
            speech_session = start_audio_stream()
            for chunk in chunks:
                speech_session.enqueue(chunk)

        def on_text_delta(delta: str) -> None:
            enqueue_chunks(chunker.feed(delta))

        def on_text_cancel() -> None:
            nonlocal session
            nonlocal monitor_started

            chunker.reset()
            if session is not None:
                session.cancel()
                session = None

            if monitor_started:
                try:
                    if not self.barge_in.triggered:
                        self.barge_in.stop(timeout=1.0)
                finally:
                    monitor_started = False

            if self.state.current is AgentState.SPEAKING:
                self._transition(
                    AgentState.THINKING,
                    "stream paused for tool call",
                )

        reply = self.agent.ask_stream(
            transcript_text,
            on_text_delta=on_text_delta,
            on_text_cancel=on_text_cancel,
            on_tool_event=self._on_tool_event,
        )

        enqueue_chunks(chunker.flush())
        print_numbered_reply(reply.text)

        if session is not None:
            timing = session.finish()
            self._settle_stream_barge_in(
                monitor_started=monitor_started
            )
            self._record_stream_timing(timing)

        self._log_agent_reply(reply)

    def _ask_agent(
        self,
        transcript_text: str,
        *,
        speak_response: bool,
    ) -> None:
        if (
            self.config.streaming_enabled
            and speak_response
        ):
            self._ask_agent_streaming(
                transcript_text,
                speak_response=True,
            )
        else:
            self._ask_agent_buffered(
                transcript_text,
                speak_response=speak_response,
            )

    def _process_capture(self, capture: CaptureResult) -> None:
        self._print_capture(capture)
        transcription = self._transcribe(capture)
        transcript_text = self._print_transcription(transcription)
        local_result = self._handle_local_command(
            transcript_text,
            speak_response=True,
        )
        if local_result == 'end_session':
            self._pending_barge_in_capture = None
            self._finish_command('session_end_command')
            self.conversation.complete_turn()
            self._return_to_sleep(
                reason='conversation ended by user',
                conversation_end_reason='user_command',
            )
            return
        if local_result is not None:
            self._after_turn(outcome=local_result)
            return
        if self._try_fast_path(
            transcript_text,
            speak_response=True,
        ):
            self._after_turn(outcome="fast_path")
            return
        self._ask_agent(
            transcript_text,
            speak_response=True,
        )
        self._after_turn(outcome='success')

    def _on_console_text_submitted(
        self,
        text: str,
    ) -> None:
        del text
        if self.state.current is AgentState.SPEAKING:
            self.synthesizer.stop()
            print(
                "\nTEXT INPUT: stopping TTS and queueing the command."
            )

    def _prepare_text_conversation(self) -> None:
        if not self.conversation.active:
            self._start_conversation()
            return
        if self.conversation.can_accept_followup:
            return
        self._end_conversation(
            "text_input_at_turn_limit"
        )
        self._start_conversation()

    def _process_next_text_input(self) -> bool:
        text = self.console_input.try_read()
        if text is None:
            return False

        self._prepare_text_conversation()
        self.microphone.clear_pending()
        self.wakeword.reset()
        self._transition(
            AgentState.TEXT_INPUT,
            "console text submitted",
        )
        self._start_command(
            wake_score=None,
            wakeword_required=False,
            input_source="text",
        )
        if self._active_command is not None:
            self._active_command.transcript = text

        self.metrics.log(
            "text_input_received",
            data={
                "command_id": (
                    self._active_command.command_id
                    if self._active_command
                    else None
                ),
                "conversation_id": (
                    self.conversation.session_id
                ),
                "turn_index": (
                    self.conversation.next_turn_index
                ),
                "characters": len(text),
            },
            private={"text_input": text},
        )
        print(
            f"\nTEXT COMMAND: {text}"
        )

        local_result = self._handle_local_command(
            text,
            speak_response=False,
        )
        if local_result == "end_session":
            self._pending_barge_in_capture = None
            self._finish_command(
                "text_session_end_command"
            )
            self.conversation.complete_turn()
            self._return_to_sleep(
                reason="conversation ended by text command",
                conversation_end_reason="text_user_command",
            )
            return True
        if local_result is not None:
            self._after_turn(
                outcome=f"text_{local_result}"
            )
            return True

        if self._try_fast_path(
            text,
            speak_response=False,
        ):
            self._after_turn(
                outcome="text_fast_path"
            )
            return True

        self._ask_agent(
            text,
            speak_response=False,
        )
        self._after_turn(
            outcome="text_success"
        )
        return True

    def _run_wakeword_cycle(self) -> None:
        wake_result = self._wait_for_wakeword()
        if wake_result is None:
            self._process_next_text_input()
            return
        capture = self._capture_after_wakeword(
            wake_result
        )
        if capture.end_reason == "text_input":
            self._finish_command(
                "voice_capture_preempted_by_text"
            )
            self._process_next_text_input()
            return
        if not capture.speech_detected:
            print(
                f'COMMAND: no speech detected '
                f'(peak VAD={capture.peak_probability:.3f}).'
            )
            self._finish_command('no_speech')
            self._return_to_sleep(
                reason='speech start timeout',
                conversation_end_reason='wakeword_without_command',
            )
            return
        self._process_capture(capture)

    def _run_followup_cycle(self) -> None:
        if self._process_next_text_input():
            return
        capture = self._capture_followup()
        if capture.end_reason == "text_input":
            self._finish_command(
                "voice_followup_preempted_by_text"
            )
            self._process_next_text_input()
            return
        if not capture.speech_detected:
            print('\nFOLLOW-UP: timed out. Returning to wake-word mode.')
            self._finish_command('followup_timeout')
            self._return_to_sleep(
                reason='follow-up timeout',
                conversation_end_reason='timeout',
            )
            return
        self._process_capture(capture)

    def _recover(self, error: BaseException) -> None:
        message = str(error).strip() or type(error).__name__
        trace = self._active_command
        self.metrics.log('runtime_error', data={
            'command_id': trace.command_id if trace else None,
            'conversation_id': self.conversation.session_id,
            'state': self.state.current,
            'error_type': type(error).__name__,
            'error': message,
        })
        self.synthesizer.stop()
        self.barge_in.stop(timeout=1.0)
        self._pending_barge_in_capture = None
        self._finish_command('error')
        self._end_conversation('runtime_error')
        if self.state.current is not AgentState.ERROR:
            self._transition(AgentState.ERROR, f'{type(error).__name__}: {message}')
        print(f'\nRuntime error: {message}', file=sys.stderr)
        self._transition(AgentState.RECOVERING, 'resetting audio and model state')
        self.wakeword.reset()
        self.speech_capture.detector.reset()
        self.microphone.clear_pending()
        if self.config.recovery_delay_seconds:
            sleep(self.config.recovery_delay_seconds)
        self._transition(AgentState.SLEEPING, 'recovery completed')
        print('\nRecovered. Say "Hey Jarvis" again.\n')

    def run(self) -> int:
        try:
            self.scheduler.start()
            self.console_input.start(
                on_submit=(
                    self._on_console_text_submitted
                )
            )
            with self.microphone:
                self._transition(AgentState.SLEEPING, 'startup completed')
                self._deliver_due_reminders()
                print(
                    'Voice: say "Hey Jarvis". '
                    'Text: type normally and press Enter. '
                    'Ctrl+C stops Jarvis.\n'
                )
                while True:
                    try:
                        if self.conversation.active:
                            self._run_followup_cycle()
                        else:
                            self._run_wakeword_cycle()
                    except (TimeoutError, RuntimeError, ValueError) as exc:
                        self._recover(exc)
        except KeyboardInterrupt:
            print('\nStopped by user.')
            return 0
        finally:
            self._finish_command('stopped')
            self._end_conversation('runtime_stopped')
            self.synthesizer.stop()
            self.scheduler.stop()
            self.console_input.close()
            try:
                self.barge_in.close()
            finally:
                try:
                    self.agent.close()
                finally:
                    try:
                        self.synthesizer.close()
                    finally:
                        try:
                            self.state.stop(
                                reason='runtime exited'
                            )
                        finally:
                            self.metrics.close()
        return 0
