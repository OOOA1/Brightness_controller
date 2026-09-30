import unittest
from brightness_control.model import MonitorState, clamp, default_display_name, fill_default_profiles


class ModelTests(unittest.TestCase):
    def test_clamp_and_restore(self):
        state = MonitorState(68, 68, 68)
        state.set_target(0)
        self.assertEqual(state.restore(), 68)
        self.assertEqual(state.target_brightness, 0)
        state.preview(1000)
        self.assertEqual(state.current_brightness, 100)
        self.assertEqual(clamp(-5), 0)

    def test_interruption_preserves_actual_current(self):
        state = MonitorState(54.7, 10, 80)
        state.set_target(70)
        self.assertEqual(state.current_brightness, 54.7)
        self.assertEqual(state.target_brightness, 70)

    def test_dynamic_names(self):
        self.assertEqual(default_display_name(1, 1), 'Основной')
        self.assertEqual([default_display_name(i, 2) for i in (1, 2)], ['Левый', 'Правый'])
        self.assertEqual(default_display_name(4, 4), 'Монитор 4')

    def test_dynamic_profile_default_preserves_existing(self):
        profiles = [{'id': 'sleep', 'monitor_values': {'id-a': 5}},
                    {'id': 'work', 'monitor_values': {}}]
        fill_default_profiles(profiles, ['id-a', 'id-b', 'id-c', 'id-d'])
        self.assertEqual(profiles[0]['monitor_values']['id-a'], 5)
        self.assertEqual(profiles[0]['monitor_values']['id-d'], 10)
        self.assertEqual(profiles[1]['monitor_values']['id-c'], 100)


if __name__ == '__main__':
    unittest.main()
