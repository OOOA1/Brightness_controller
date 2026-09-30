import unittest
from brightness_control.wake import confirmed_wake


class WakeTests(unittest.TestCase):
    def test_partial_never_activates(self):
        candidate = {'text': 'джарвис', 'result': [{'word': 'джарвис', 'conf': .99}]}
        self.assertFalse(confirmed_wake(candidate, 'джарвис', final=False))
        self.assertTrue(confirmed_wake(candidate, 'джарвис', final=True))

    def test_rejects_weak_or_wrong_phrase(self):
        self.assertFalse(confirmed_wake({'text': 'джарвис', 'result': [
            {'word': 'джарвис', 'conf': .65}]}, 'джарвис'))
        self.assertFalse(confirmed_wake({'text': 'компьютер', 'result': [
            {'word': 'компьютер', 'conf': .99}]}, 'джарвис'))
        self.assertFalse(confirmed_wake({'text': '[unk]'}, 'джарвис'))

    def test_multiword_and_uninterrupted_command(self):
        result = {'text': 'привет джарвис яркость тридцать', 'result': [
            {'word': 'привет', 'conf': .94}, {'word': 'джарвис', 'conf': .92},
            {'word': 'яркость', 'conf': .8}, {'word': 'тридцать', 'conf': .7}]}
        self.assertTrue(confirmed_wake(result, 'привет джарвис'))
