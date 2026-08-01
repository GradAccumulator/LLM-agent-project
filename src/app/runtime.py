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
from src.conversation import ConversationSession
from src.core import AgentState, AgentStateMachine, StateTransition
from src.llm import JarvisAgent, ToolLifecycleEvent
from src.metrics import JsonlMetricsLogger
from src.speech import CaptureResult, SpeechCapture, save_wave_file
from src.stt import SpeechRecognizer, TranscriptionResult
from src.tts import SpeechSynthesizer
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
    tts_enabled: bool = True
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
    capture_audio_seconds: float | None = None
    stt_seconds: float | None = None
    llm_seconds: float | None = None
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
        self.state = state_machine or AgentStateMachine()
        self.tts_enabled = config.tts_enabled
        self._active_command: _CommandTrace | None = None
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

    def _start_command(self, *, wake_score: float | None, wakeword_required: bool) -> None:
        trace = _CommandTrace(
            command_id=uuid4().hex,
            started_at=perf_counter(),
            wake_score=wake_score,
            conversation_id=self.conversation.session_id,
            turn_index=self.conversation.next_turn_index,
            wakeword_required=wakeword_required,
        )
        self._active_command = trace
        self.metrics.log('command_started', data={
            'command_id': trace.command_id,
            'conversation_id': trace.conversation_id,
            'turn_index': trace.turn_index,
            'wake_score': trace.wake_score,
            'wakeword_required': trace.wakeword_required,
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
            'outcome': outcome,
            'total_seconds': round(perf_counter() - trace.started_at, 6),
            'capture_audio_seconds': trace.capture_audio_seconds,
            'stt_seconds': trace.stt_seconds,
            'llm_seconds': trace.llm_seconds,
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

    def _after_turn(self, *, outcome: str) -> None:
        self._finish_command(outcome)
        completed_turn = self.conversation.complete_turn()
        self.metrics.log('conversation_turn_completed', data={
            'conversation_id': self.conversation.session_id,
            'turn_index': completed_turn,
            'remaining_turns': self.conversation.snapshot().remaining_turns,
        })
        if self.conversation.can_accept_followup:
            self._continue_conversation(reason='awaiting follow-up command')
            return
        reason = (
            'continuous conversation disabled'
            if not self.conversation.config.enabled
            else 'maximum turns reached'
        )
        self._return_to_sleep(reason=reason, conversation_end_reason=reason)

    def _speak(self, text: str) -> bool:
        self._transition(AgentState.SPEAKING, 'speaking response')
        try:
            self.synthesizer.speak(text)
            timing = self.synthesizer.last_timing
            trace = self._active_command
            if trace is not None:
                trace.tts_first_audio_seconds = timing.first_audio_seconds
                trace.tts_total_seconds = timing.total_seconds
            self.metrics.log('tts_completed', data={
                'command_id': trace.command_id if trace is not None else None,
                'conversation_id': self.conversation.session_id,
                'first_audio_seconds': timing.first_audio_seconds,
                'chunks': timing.chunks,
                'total_seconds': timing.total_seconds,
            })
            print(
                f'TTS LATENCY: first_audio={timing.first_audio_seconds:.2f}s '
                f'| chunks={timing.chunks} | total={timing.total_seconds:.2f}s'
            )
            return True
        except RuntimeError as exc:
            self.metrics.log('tts_failed', data={
                'command_id': self._active_command.command_id if self._active_command else None,
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
            })
            self._transition(AgentState.THINKING, f'tool finished: {event.name} ({status})')
            return
        raise ValueError(f'Unknown tool lifecycle phase: {event.phase}')

    def _wait_for_wakeword(self) -> DetectionResult:
        while True:
            frame = self.microphone.read(timeout=2.0)
            result = self.wakeword.predict(frame.samples)
            rms = normalized_rms(frame.samples)
            print(
                f'\rSLEEPING wake={result.score:.3f} rms={rms:.4f} '
                f'device={self.microphone.device}      ',
                end='',
                flush=True,
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
        )

    def _capture_followup(self) -> CaptureResult:
        self._start_command(wake_score=None, wakeword_required=False)
        return self.speech_capture.capture(
            self.microphone,
            start_timeout_seconds=self.conversation.config.followup_timeout_seconds,
            on_speech_start=self._on_speech_start,
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
            output_path = save_wave_file(capture.samples, directory=self.config.save_directory)
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

    def _local_reply(self, text: str) -> None:
        if self._active_command is not None:
            self._active_command.reply = text
        print(f'JARVIS: {text}')
        if self.tts_enabled:
            self.tts_enabled = self._speak(text)

    def _handle_local_command(self, transcript_text: str) -> str | None:
        normalized = normalize_local_command(transcript_text)
        if not transcript_text:
            self._local_reply('음성을 이해하지 못했습니다.')
            return 'local_command'
        if normalized in _SESSION_END_COMMANDS:
            self._local_reply('대화 모드를 종료합니다.')
            return 'end_session'
        if normalized in _TTS_OFF_COMMANDS:
            message = '음성 출력을 끕니다.'
            if self._active_command is not None:
                self._active_command.reply = message
            print(f'JARVIS: {message}')
            if self.tts_enabled:
                self._speak(message)
            self.tts_enabled = False
            return 'local_command'
        if normalized in _TTS_ON_COMMANDS:
            self.tts_enabled = True
            self._local_reply('음성 출력을 켰습니다.')
            return 'local_command'
        if normalized in _RESET_COMMANDS:
            self.agent.reset_conversation()
            self._local_reply('대화 기억을 초기화했습니다.')
            return 'local_command'
        return None

    def _ask_agent(self, transcript_text: str) -> None:
        self._transition(AgentState.THINKING, 'transcription ready')
        print('THINKING...', flush=True)
        reply = self.agent.ask(transcript_text, on_tool_event=self._on_tool_event)
        trace = self._active_command
        if trace is not None:
            trace.llm_seconds = reply.elapsed_seconds
            trace.reply = reply.text
        for tool_call in reply.tool_calls:
            status = 'success' if tool_call.success else 'failed'
            print(f'TOOL {tool_call.name}({tool_call.arguments})')
            print(f'TOOL RESULT: {status} ({tool_call.elapsed_seconds:.3f}s)')
            if not tool_call.success:
                print(tool_call.output)
        usage_text = format_token_usage(reply.input_tokens, reply.output_tokens)
        print(
            f'JARVIS [{reply.model} | {reply.elapsed_seconds:.2f}s | '
            f'{usage_text} | tools={len(reply.tool_calls)}]:'
        )
        print(reply.text)
        self.metrics.log('llm_completed', data={
            'command_id': trace.command_id if trace else None,
            'conversation_id': self.conversation.session_id,
            'model': reply.model,
            'elapsed_seconds': reply.elapsed_seconds,
            'input_tokens': reply.input_tokens,
            'output_tokens': reply.output_tokens,
            'total_tokens': reply.total_tokens,
            'tool_count': len(reply.tool_calls),
            'reply_characters': len(reply.text),
        }, private={'reply': reply.text})
        if self.tts_enabled:
            self.tts_enabled = self._speak(reply.text)

    def _process_capture(self, capture: CaptureResult) -> None:
        self._print_capture(capture)
        transcription = self._transcribe(capture)
        transcript_text = self._print_transcription(transcription)
        local_result = self._handle_local_command(transcript_text)
        if local_result == 'end_session':
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
        self._ask_agent(transcript_text)
        self._after_turn(outcome='success')

    def _run_wakeword_cycle(self) -> None:
        wake_result = self._wait_for_wakeword()
        capture = self._capture_after_wakeword(wake_result)
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
        capture = self._capture_followup()
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
            with self.microphone:
                self._transition(AgentState.SLEEPING, 'startup completed')
                print('Say "Hey Jarvis". Press Ctrl+C to stop.\n')
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
            try:
                self.synthesizer.close()
            finally:
                try:
                    self.state.stop(reason='runtime exited')
                finally:
                    self.metrics.close()
        return 0
