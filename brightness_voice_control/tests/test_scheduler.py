import unittest
from datetime import datetime
from brightness_control.scheduler import due_rules, latest_due_since


class SchedulerTests(unittest.TestCase):
    def test_once_per_day_and_day_filter(self):
        rules = [{'id': 'night', 'time': '23:30', 'days': [0, 1], 'profile_id': 'sleep'}]
        fired = set()
        monday = datetime(2026, 9, 28, 23, 30)
        self.assertEqual(len(due_rules(rules, monday, fired)), 1)
        self.assertEqual(due_rules(rules, monday, fired), [])
        wednesday = datetime(2026, 9, 30, 23, 30)
        self.assertEqual(due_rules(rules, wednesday, fired), [])

    def test_resume_uses_latest_due_rule(self):
        rules = [{'id': 'sleep', 'time': '23:30', 'days': list(range(7))},
                 {'id': 'work', 'time': '08:00', 'days': list(range(7))}]
        fired = set()
        earlier = datetime(2026, 9, 28, 23, 20)
        now = datetime(2026, 9, 29, 8, 10)
        self.assertEqual(latest_due_since(rules, earlier, now, fired)['id'], 'work')
        self.assertIsNone(latest_due_since(rules, earlier, now, fired))
