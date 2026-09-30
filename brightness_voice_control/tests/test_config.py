import json
import tempfile
import unittest
from pathlib import Path
from brightness_control.config import load, save, SCHEMA


class ConfigTests(unittest.TestCase):
    def test_missing_and_migration(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            self.assertEqual(load(path)['schema_version'], SCHEMA)
            old = {'schema_version': 2, 'monitors': {'device:abc': 'Левый'},
                   'monitor_aliases': {'device:abc': 'игровой'},
                   'profiles': [{'id': 'sleep', 'name': 'Сон',
                                 'monitor_values': {'Левый': 5}}],
                   'brightness': {'device:abc': 42}, 'previous_nonzero': {'device:abc': 70},
                   'microphone': 2, 'tts_voice': 'selected-voice', 'autostart': True,
                   'voice_enabled': False, 'duration': 9}
            path.write_text(json.dumps(old), encoding='utf-8')
            config = load(path)
            self.assertTrue(config['first_run_completed'])
            self.assertEqual(config['monitors']['device:abc'],
                             {'display_name': 'Левый', 'voice_aliases': ['игровой']})
            self.assertEqual(config['profiles'][0]['monitor_values']['device:abc'], 5)
            self.assertEqual(config['wake_phrase'], 'компьютер')
            self.assertEqual(config['tts_voice'], 'selected-voice')
            self.assertTrue(config['autostart'])
            self.assertEqual(config['brightness'], old['brightness'])
            self.assertEqual(config['duration'], 5)
            self.assertFalse(config['voice_enabled'])
            save(config, path)
            self.assertEqual(load(path)['brightness']['device:abc'], 42)

    def test_corruption_backup_and_atomic(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            config = load(path)
            save(config, path)
            config['relative_step'] = 17
            save(config, path)
            path.write_text('{broken', encoding='utf-8')
            self.assertEqual(load(path)['relative_step'], 10)
            recovered = load(path)
            save(recovered, path)
            self.assertEqual(json.loads((path.parent / 'config.backup.json').read_text())['relative_step'], 10)
            self.assertFalse((path.parent / 'config.tmp').exists())

    def test_invalid_nested_values(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            path.write_text(json.dumps({'schema_version': 2, 'duration': 'bad',
                'notifications': {'duration': 'broken', 'success': 'yes'},
                'profiles': [{'id': 'x', 'name': 'Bad', 'monitor_values': None}],
                'schedule': [{'id': 'a', 'time': '12:00', 'profile_id': 'x', 'days': 'Mon'}]}),
                encoding='utf-8')
            config = load(path)
            self.assertEqual(config['duration'], 1.5)
            self.assertTrue(config['notifications']['success'])
            self.assertEqual(config['profiles'][0]['monitor_values'], {})
            self.assertEqual(config['schedule'][0]['days'], [])

    def test_wake_validation_and_profile_id_survives_rename(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            data = {'schema_version': 3, 'wake_phrase': '!!!',
                    'monitors': {'edid:one': {'display_name': 'Игровой', 'voice_aliases': ['ЛГ', 'lg']}},
                    'profiles': [{'id': 'sleep', 'name': 'Сон', 'monitor_values': {'edid:one': 10}}]}
            path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            config = load(path)
            self.assertEqual(config['wake_phrase'], 'компьютер')
            self.assertEqual(config['monitors']['edid:one']['voice_aliases'], ['лг', 'lg'])
            config['monitors']['edid:one']['display_name'] = 'Главный'
            save(config, path)
            self.assertEqual(load(path)['profiles'][0]['monitor_values']['edid:one'], 10)


if __name__ == '__main__':
    unittest.main()
