"""Versioned local settings. Existing v0.1 values are retained on migration."""
import copy
import json
import logging
import os
from pathlib import Path
import shutil
import re

SCHEMA = 3
LOG = logging.getLogger(__name__)


def config_path() -> Path:
    return Path(os.environ.get('APPDATA', str(Path.home()))) / 'BrightnessVoiceControl' / 'config.json'


DEFAULT = {
    'schema_version': SCHEMA,
    'first_run_completed': False,
    'monitors': {},
    'monitor_info': {},
    'brightness': {},                 # last targets, keyed by stable monitor ID
    'previous_nonzero': {},
    'voice_enabled': True,
    'voice_runtime_available': False, # transient; never persisted
    'tts_enabled': True,              # migration compatibility
    'microphone': None,
    'microphone_name': '',
    'duration': 1.5,
    'remember_brightness': True,
    'autostart': False,
    'start_in_tray': True,
    'tray_tip_shown': False,
    'relative_step': 10,
    'minimum_brightness': 5,
    'wake_beep': True,
    'wake_phrase': 'компьютер',
    'show_listening': True,
    'command_timeout': 7,
    'tts_mode': 'short',
    'tts_response': 'always',
    'tts_volume': 100,
    'tts_rate': 0,
    'tts_voice': '',
    'tts_provider': 'windows',
    'appearance': {'theme': 'system'},
    'notifications': {'success': True, 'errors': True, 'confirmation': True,
                      'listening': True, 'duration': 2.5, 'placement': 'primary'},
    'profiles': [
        {'id': 'sleep', 'name': 'Сон', 'icon': 'moon',
         'monitor_values': {},
         'voice_aliases': ['спать'], 'transition_duration': None},
        {'id': 'work', 'name': 'Работа', 'icon': 'sun',
         'monitor_values': {},
         'voice_aliases': [], 'transition_duration': None},
    ],
    'schedule': [],
    'active_profile': None,
}


def _bounded(value, fallback, lower, upper, cast=float):
    try:
        number = cast(value)
        return min(upper, max(lower, number))
    except (ValueError, TypeError, OverflowError):
        return fallback


def normalize_phrase(value: str) -> str:
    return ' '.join(re.sub(r'[^\w\s]', ' ', value.lower().replace('ё', 'е')).split())


def migrate(data: object) -> dict:
    result = copy.deepcopy(DEFAULT)
    if not isinstance(data, dict):
        return result
    old_schema = data.get('schema_version', 0)
    if type(old_schema) is not int:
        old_schema = 0
    for key in result:
        if key in ('schema_version', 'voice_runtime_available'):
            continue
        value = data.get(key)
        expected = result[key]
        if value is not None and (isinstance(value, type(expected)) or
                                  (key == 'duration' and type(value) in (int, float))):
            result[key] = copy.deepcopy(value)
    # None is valid for some nullable settings.
    for key in ('microphone', 'active_profile'):
        value = data.get(key)
        if value is None or (key == 'microphone' and type(value) is int) or (
                key == 'active_profile' and isinstance(value, str)):
            result[key] = value
    if old_schema < SCHEMA and data:
        # Existing users have already completed basic setup.
        result['first_run_completed'] = True
    result['schema_version'] = SCHEMA
    result['voice_runtime_available'] = False
    for key in ('monitors', 'monitor_info', 'brightness', 'previous_nonzero'):
        result[key] = result[key] if isinstance(result[key], dict) else {}
    legacy_aliases = data.get('monitor_aliases', {}) if isinstance(data.get('monitor_aliases'), dict) else {}
    monitor_records = {}
    for key, item in result['monitors'].items():
        if not isinstance(key, str):
            continue
        if isinstance(item, str):
            alias = legacy_aliases.get(key, '')
            aliases = [alias] if isinstance(alias, str) and normalize_phrase(alias) else []
            item = {'display_name': item, 'voice_aliases': aliases}
        if not isinstance(item, dict):
            continue
        name = item.get('display_name', '')
        aliases = item.get('voice_aliases', [])
        if not isinstance(name, str) or not isinstance(aliases, list):
            continue
        monitor_records[key] = {
            'display_name': name.strip() or 'Монитор',
            'voice_aliases': list(dict.fromkeys(normalize_phrase(a) for a in aliases
                                                 if isinstance(a, str) and normalize_phrase(a))),
        }
    result['monitors'] = monitor_records
    if not isinstance(result['wake_phrase'], str) or not normalize_phrase(result['wake_phrase']):
        result['wake_phrase'] = 'компьютер'
    else:
        result['wake_phrase'] = normalize_phrase(result['wake_phrase'])
    result['tts_provider'] = 'windows'  # only installed provider in this version
    for key in ('brightness', 'previous_nonzero'):
        result[key] = {str(k): int(_bounded(v, 100, 0, 100, int))
                       for k, v in result[key].items() if isinstance(k, str)}
    result['duration'] = _bounded(result['duration'], 1.5, 0., 5.)
    result['relative_step'] = int(_bounded(result['relative_step'], 10, 1, 100, int))
    result['minimum_brightness'] = int(_bounded(result['minimum_brightness'], 5, 0, 100, int))
    result['command_timeout'] = int(_bounded(result['command_timeout'], 7, 3, 10, int))
    result['tts_volume'] = int(_bounded(result['tts_volume'], 100, 0, 100, int))
    result['tts_rate'] = int(_bounded(result['tts_rate'], 0, -100, 100, int))
    if result['tts_mode'] not in ('short', 'full'):
        result['tts_mode'] = 'short'
    if result['tts_response'] not in ('always', 'important', 'errors', 'off'):
        result['tts_response'] = 'always'
    if not result['tts_enabled']:
        result['tts_response'] = 'off'
    for key, value in DEFAULT['appearance'].items():
        result['appearance'].setdefault(key, value)
    if result['appearance']['theme'] not in ('system', 'dark', 'light'):
        result['appearance']['theme'] = 'system'
    for key, value in DEFAULT['notifications'].items():
        result['notifications'].setdefault(key, value)
    result['notifications']['duration'] = _bounded(
        result['notifications']['duration'], 2.5, 1., 10.)
    if result['notifications']['placement'] not in ('primary', 'cursor'):
        result['notifications']['placement'] = 'primary'
    for flag in ('success', 'errors', 'confirmation', 'listening'):
        if type(result['notifications'][flag]) is not bool:
            result['notifications'][flag] = DEFAULT['notifications'][flag]
    names = {}
    for mid, record in monitor_records.items():
        names.setdefault(record['display_name'], []).append(mid)
    valid_profiles = []
    for item in result['profiles']:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not isinstance(item.get('name'), str):
            continue
        values = item.get('monitor_values', {})
        if not isinstance(values, dict):
            values = {}
        profile = dict(item)
        new_values = {}
        unresolved = dict(item.get('legacy_monitor_values', {})) if isinstance(item.get('legacy_monitor_values'), dict) else {}
        for name, value in values.items():
            if not isinstance(name, str):
                continue
            if name in monitor_records or name.startswith(('edid:', 'device:', 'ambiguous:')):
                new_values[name] = int(_bounded(value, 100, 0, 100, int))
            elif old_schema < 3:
                ids = names.get(name, [])
                stable = [mid for mid in ids if mid.startswith(('edid:', 'device:', 'ambiguous:'))]
                selected = stable if len(stable) == 1 else ids
                if len(selected) == 1:
                    new_values[selected[0]] = int(_bounded(value, 100, 0, 100, int))
                else:
                    unresolved[name] = int(_bounded(value, 100, 0, 100, int))
            else:
                # Keep disconnected stable IDs from imported profiles.
                new_values[name] = int(_bounded(value, 100, 0, 100, int))
        profile['monitor_values'] = new_values
        if unresolved:
            profile['legacy_monitor_values'] = unresolved
        profile['voice_aliases'] = [s for s in item.get('voice_aliases', [])
                                    if isinstance(s, str)] if isinstance(item.get('voice_aliases', []), list) else []
        duration = item.get('transition_duration')
        profile['transition_duration'] = _bounded(duration, 1.5, 0, 5) if duration is not None else None
        valid_profiles.append(profile)
    result['profiles'] = valid_profiles
    valid_rules = []
    for rule in result['schedule']:
        if not isinstance(rule, dict) or not isinstance(rule.get('time'), str) or not isinstance(rule.get('profile_id'), str):
            continue
        days = rule.get('days', list(range(7)))
        if not isinstance(days, list):
            days = []
        clean_rule = dict(rule)
        clean_rule['days'] = [day for day in days if type(day) is int and 0 <= day < 7]
        clean_rule['enabled'] = rule.get('enabled', True) is True
        clean_rule['duration'] = (_bounded(rule['duration'], 1.5, 0, 5)
                                  if rule.get('duration') is not None else None)
        valid_rules.append(clean_rule)
    result['schedule'] = valid_rules
    return result


def load(path: Path | None = None) -> dict:
    path = path or config_path()
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return migrate(None)
    except (OSError, ValueError, UnicodeError):
        LOG.warning('Configuration corrupted; trying backup')
        try:
            data = json.loads(path.with_name('config.backup.json').read_text(encoding='utf-8'))
        except (OSError, ValueError, UnicodeError):
            return migrate(None)
    return migrate(data)


def save(data: dict, path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = migrate(data)
    temp = path.with_name('config.tmp')
    temp.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding='utf-8')
    with temp.open('rb') as handle:
        os.fsync(handle.fileno())
    if path.exists():
        try:
            json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError, UnicodeError):
            pass
        else:
            shutil.copy2(path, path.with_name('config.backup.json'))
    temp.replace(path)
