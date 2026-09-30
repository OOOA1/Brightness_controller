import unittest
from brightness_control.state import VoiceMachine, VoiceState


class StateTests(unittest.TestCase):
    def test_command_confirmation_and_recovery(self):
        machine = VoiceMachine()
        self.assertEqual(machine.transition('wake'), VoiceState.WAKE_DETECTED)
        self.assertEqual(machine.transition('listen'), VoiceState.LISTENING)
        self.assertEqual(machine.transition('command'), VoiceState.PROCESSING)
        self.assertEqual(machine.transition('uncertain'), VoiceState.CONFIRMATION)
        self.assertEqual(machine.transition('execute'), VoiceState.EXECUTING)
        self.assertEqual(machine.transition('done'), VoiceState.IDLE)
        self.assertEqual(machine.transition('tts_start'), VoiceState.TTS)
        self.assertEqual(machine.transition('tts_done'), VoiceState.WAKE_ONLY)
        machine.transition('device_error')
        self.assertEqual(machine.transition('recovered'), VoiceState.IDLE)
        machine.transition('disable')
        self.assertEqual(machine.transition('wake'), VoiceState.DISABLED)
        self.assertEqual(machine.transition('enable'), VoiceState.IDLE)

    def test_cancel_and_timeout(self):
        machine = VoiceMachine()
        machine.transition('wake')
        machine.transition('listen')
        self.assertEqual(machine.transition('no_speech'), VoiceState.WAKE_ONLY)
        machine.transition('wake')
        machine.transition('listen')
        machine.transition('command')
        machine.transition('uncertain')
        self.assertEqual(machine.transition('cancel'), VoiceState.IDLE)
        machine.transition('wake')
        machine.transition('listen')
        machine.transition('command')
        self.assertEqual(machine.transition('unknown'), VoiceState.WAKE_ONLY)
