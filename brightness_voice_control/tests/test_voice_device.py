import sys
import types
import unittest
from unittest.mock import patch


class VoiceDeviceTests(unittest.TestCase):
    def test_unsaved_device_used_only_during_test(self):
        qtcore = types.ModuleType('PySide6.QtCore')
        qtcore.QObject = type('QObject', (), {})
        qtcore.Signal = lambda *args: None
        with patch.dict(sys.modules, {'PySide6': types.ModuleType('PySide6'),
                                      'PySide6.QtCore': qtcore}):
            from brightness_control.voice import Voice
            voice = Voice()
            voice.device = 3
            voice.thread = types.SimpleNamespace(is_alive=lambda: True)
            with patch.object(voice, 'start') as start:
                voice.test_wake_phrase('Джарвис', 7)
                start.assert_called_once_with(7, initial_mode='test')
                self.assertEqual(voice.test_phrase, 'джарвис')
                start.reset_mock()
                voice.cancel_wake_test()
                start.assert_called_once_with(3)

    def test_same_device_reuses_existing_stream(self):
        qtcore = types.ModuleType('PySide6.QtCore')
        qtcore.QObject = type('QObject', (), {})
        qtcore.Signal = lambda *args: None
        with patch.dict(sys.modules, {'PySide6': types.ModuleType('PySide6'),
                                      'PySide6.QtCore': qtcore}):
            from brightness_control.voice import Voice
            voice = Voice()
            voice.device = 3
            voice.thread = types.SimpleNamespace(is_alive=lambda: True)
            with patch.object(voice, 'start') as start:
                voice.begin_microphone_test(3)
                start.assert_not_called()
                self.assertEqual(voice.mode, 'meter')
                voice.cancel_wake_test()
                self.assertEqual(voice.mode, 'wake')


if __name__ == '__main__':
    unittest.main()
