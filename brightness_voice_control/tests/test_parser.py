import unittest
from brightness_control.parser import parse, split_wake

ALIASES = {
    'левый': 'device:left', 'слева': 'device:left',
    'центральный': 'device:center', 'правый': 'device:right',
    'игровой': 'device:left', 'lg': 'device:left',
}


class ParserTests(unittest.TestCase):
    def test_dynamic_wake(self):
        self.assertEqual(split_wake('Привет Джарвис, яркость 30', 'привет джарвис'),
                         (True, 'яркость 30'))
        self.assertEqual(split_wake('Компьютер, яркость 30', 'джарвис')[0], False)
        self.assertFalse(split_wake('джарвиска яркость 30', 'джарвис')[0])

    def test_intents_and_aliases(self):
        samples = [
            ('яркость 20', 'set_brightness', None, 20),
            ('яркость до двадцати процентов', 'set_brightness', None, 20),
            ('левый 20', 'set_brightness', 'device:left', 20),
            ('яркость левого десять', 'set_brightness', 'device:left', 10),
            ('монитор 4 на 30', 'set_brightness', '#4', 30),
            ('четвёртый монитор на тридцать', 'set_brightness', '#4', 30),
            ('монитор десять на 30', 'set_brightness', '#10', 30),
            ('убавь на 20', 'change_brightness', None, -20),
            ('добавь 15', 'change_brightness', None, 15),
            ('правый ярче', 'change_brightness', 'device:right', 10),
            ('максимальная яркость', 'max_brightness', None, None),
            ('выключи игровой', 'blackout', 'device:left', None),
            ('верни lg', 'restore', 'device:left', None),
        ]
        for phrase, intent, target, value in samples:
            with self.subTest(phrase=phrase):
                cmd = parse(phrase, aliases=ALIASES)
                self.assertIsNotNone(cmd)
                self.assertEqual((cmd.intent, cmd.target, cmd.value), (intent, target, value))

    def test_negative_and_ambiguity(self):
        for phrase in ('монитор два', 'левый правый 30', 'яркость 200',
                       'левый 10 30', 'сделай темнее и ярче', 'случайная фраза 50'):
            with self.subTest(phrase=phrase):
                self.assertIsNone(parse(phrase, aliases=ALIASES))
        ambiguous = {'игровой': ['device:left', 'device:right']}
        self.assertIsNone(parse('игровой 30', aliases=ambiguous))

    def test_confidence_profiles_and_all(self):
        self.assertTrue(parse('левый 30', .75, aliases=ALIASES).requires_confirmation)
        self.assertEqual(parse('режим сна', profiles=[{'id': 'sleep', 'name': 'Сон'}]).profile_id, 'sleep')
        self.assertIsNone(parse('яркость 30').target)
        self.assertIsNone(parse('сделай темнее').target)


if __name__ == '__main__':
    unittest.main()
