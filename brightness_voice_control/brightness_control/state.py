"""Explicit transitions for the voice controller."""
from enum import Enum


class VoiceState(str, Enum):
    WAKE_ONLY = 'WAKE_ONLY'
    IDLE = 'WAKE_ONLY'  # compatibility with older tests
    WAKE_DETECTED = 'WAKE_DETECTED'
    LISTENING = 'LISTENING'
    PROCESSING = 'PROCESSING'
    CONFIRMATION = 'CONFIRMATION'
    EXECUTING = 'EXECUTING'
    TTS = 'TTS'
    DEVICE_ERROR = 'DEVICE_ERROR'
    DISABLED = 'DISABLED'


class VoiceMachine:
    def __init__(self, enabled=True):
        self.state = VoiceState.WAKE_ONLY if enabled else VoiceState.DISABLED

    def transition(self, event):
        current = self.state
        if event == 'disable':
            self.state = VoiceState.DISABLED
        elif event == 'device_error' and current != VoiceState.DISABLED:
            self.state = VoiceState.DEVICE_ERROR
        elif event == 'recovered' and current == VoiceState.DEVICE_ERROR:
            self.state = VoiceState.WAKE_ONLY
        elif event == 'enable' and current == VoiceState.DISABLED:
            self.state = VoiceState.WAKE_ONLY
        elif event == 'wake' and current == VoiceState.WAKE_ONLY:
            self.state = VoiceState.WAKE_DETECTED
        elif event == 'listen' and current == VoiceState.WAKE_DETECTED:
            self.state = VoiceState.LISTENING
        elif event == 'command' and current == VoiceState.LISTENING:
            self.state = VoiceState.PROCESSING
        elif event == 'uncertain' and current == VoiceState.PROCESSING:
            self.state = VoiceState.CONFIRMATION
        elif event == 'execute' and current in (VoiceState.PROCESSING, VoiceState.CONFIRMATION):
            self.state = VoiceState.EXECUTING
        elif event == 'tts_start' and current not in (VoiceState.DISABLED, VoiceState.DEVICE_ERROR):
            self.state = VoiceState.TTS
        elif event in ('done', 'cancel', 'timeout', 'no_speech', 'unknown', 'tts_done') and current not in (
                VoiceState.DISABLED, VoiceState.DEVICE_ERROR):
            self.state = VoiceState.WAKE_ONLY
        return self.state
