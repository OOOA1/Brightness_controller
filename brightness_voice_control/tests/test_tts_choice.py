import unittest
from unittest.mock import patch
import sys
import types


class TTSChoiceTests(unittest.TestCase):
    def test_missing_voice_prefers_russian_then_system_default(self):
        qtcore = types.ModuleType('PySide6.QtCore')
        qtcore.QObject = type('QObject', (), {})
        qtcore.Signal = lambda *args: None
        with patch.dict(sys.modules, {'PySide6': types.ModuleType('PySide6'),
                                      'PySide6.QtCore': qtcore}):
            from brightness_control.tts import choose_voice
            voices = [('english', 'English', '409'), ('russian', 'Russian', '419')]
            self.assertEqual(choose_voice('removed', voices), 'russian')
            self.assertEqual(choose_voice('english', voices), 'english')
            self.assertEqual(choose_voice('removed', voices[:1]), 'english')
            self.assertEqual(choose_voice('removed', []), '')


if __name__ == '__main__':
    unittest.main()
