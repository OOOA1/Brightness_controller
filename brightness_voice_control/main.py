"""Windows tray entry point. All Qt windows and overlays live on this thread."""
from dataclasses import replace
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QCheckBox, QMenu, QMessageBox, QSystemTrayIcon

from brightness_control.config import config_path, load, save, sync_autostart
from brightness_control.overlay import MonitorManager
from brightness_control.panel import TrayPanel
from brightness_control.parser import parse, split_wake, describe, spoken, normalize
from brightness_control.scheduler import latest_due_since
from brightness_control.settings_window import Settings
from brightness_control.single_instance import SingleInstance
from brightness_control.startup import set_autostart, is_autostart
from brightness_control.state import VoiceMachine, VoiceState
from brightness_control.theme import style
from brightness_control.ui import Notice
from brightness_control.voice import Voice, Speaker

LOG = logging.getLogger('brightness_control')


def setup_logging():
    folder = config_path().parent / 'logs'
    folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(folder / 'app.log', maxBytes=2_000_000,
                                  backupCount=5, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logging.getLogger().setLevel(logging.INFO)
    logging.getLogger().addHandler(handler)


def icon():
    asset = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'assets' / 'app.ico'
    if asset.exists():
        return QIcon(str(asset))
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor('#17191E'))
    painter = QPainter(pixmap)
    painter.setBrush(QColor('#7AA2FF'))
    painter.setPen(QColor('#7AA2FF'))
    painter.drawEllipse(16, 16, 32, 32)
    painter.end()
    return QIcon(pixmap)


class Controller(QObject):
    def __init__(self, app, instance):
        super().__init__()
        self.app = app
        self.instance = instance
        self.config = load()
        if sync_autostart(self.config, is_autostart()):
            try:
                save(self.config)
            except OSError:
                LOG.exception('Could not persist actual autostart state')
        app.setStyleSheet(style(self.config['appearance']['theme']))
        self.manager = MonitorManager(self.config)
        self.manager.changed.connect(self._refresh)
        self.manager.level_changed.connect(self._level)
        self.manager.overlay_shown.connect(self._raise_ui)
        self.manager.unassigned.connect(self._unassigned)
        self.voice = Voice(self.config['wake_phrase'])
        self.voice.wake_detected.connect(self._wake)
        self.voice.recognized.connect(self._recognized)
        self.voice.ready.connect(self._voice_ready)
        self.voice.error.connect(self._voice_error)
        self.speaker = Speaker(self.voice)
        selected_voice = self.speaker.resolve_voice(self.config['tts_voice'])
        if selected_voice != self.config['tts_voice']:
            LOG.warning('Configured TTS voice unavailable; using Windows fallback')
            self.config['tts_voice'] = selected_voice
        self.speaker.started.connect(self._tts_started)
        self.speaker.finished.connect(self._tts_finished)
        self.machine = VoiceMachine(self.config['voice_enabled'])
        self.pending = None
        self.retry_index = 0
        self.retry_timer = QTimer(self)
        self.retry_timer.setSingleShot(True)
        self.retry_timer.timeout.connect(self.restart_voice)
        self.state_timer = QTimer(self)
        self.state_timer.setSingleShot(True)
        self.state_timer.timeout.connect(self._timeout)
        self.schedule_timer = QTimer(self)
        self.schedule_timer.timeout.connect(self._schedule_tick)
        self.schedule_timer.start(15000)
        self.fired = set()
        self.last_schedule_check = datetime.now()
        self.notice = Notice()
        self.notice.placement = self.config['notifications']['placement']
        self.notice.decision.connect(self._decision)
        self.notice.settings_requested.connect(self._settings)
        self.panel = TrayPanel()
        self.panel.voice_toggled.connect(self._toggle_voice)
        self.panel.preview_started.connect(self._preview_begin)
        self.panel.preview_moved.connect(self._preview)
        self.panel.preview_finished.connect(self._preview_end)
        self.panel.preset_requested.connect(self._preset)
        self.panel.profile_requested.connect(self._profile_by_id)
        self.panel.settings_requested.connect(self._settings)
        self.panel.quit_requested.connect(self.close)
        self.tray = QSystemTrayIcon(icon(), app)
        self.tray.setToolTip('Brightness Voice Control')
        menu = QMenu()
        for label, callback in (
            ('Открыть панель', self._show_panel),
            ('Настройки', self._settings),
            ('Режим сна', lambda: self._profile_by_id('sleep')),
            ('Яркость 100%', lambda: self._preset(100)),
            ('Выход', self.close),
        ):
            action = QAction(label, menu)
            action.triggered.connect(callback)
            menu.addAction(action)
        self.voice_action = QAction('Голосовое управление', menu)
        self.voice_action.setCheckable(True)
        self.voice_action.setChecked(self.config['voice_enabled'])
        self.voice_action.triggered.connect(self._toggle_voice)
        menu.insertAction(menu.actions()[2], self.voice_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self._show_panel()
            if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()
        instance.received.connect(self._ipc)
        self._refresh()
        if self.config['voice_enabled']:
            self.restart_voice()
        if not self.config['first_run_completed']:
            QTimer.singleShot(0, self._onboarding)
        elif not self.config['start_in_tray'] and '--tray' not in sys.argv:
            QTimer.singleShot(0, self._settings)
        LOG.info('Application started')

    def _ipc(self, command):
        if command == 'settings':
            self._settings()
        else:
            self._show_panel()

    def _save(self):
        try:
            data = (self.config if self.config['remember_brightness'] else
                    {**self.config, 'brightness': {}, 'previous_nonzero': {}})
            save(data)
        except OSError:
            LOG.exception('Could not save settings')

    def _refresh(self):
        if not hasattr(self, 'panel'):
            return
        self.panel.rebuild(self.manager.ordered_monitors(), self.config['profiles'])
        status = {
            VoiceState.DISABLED: '○ Голос выключен',
            VoiceState.DEVICE_ERROR: '● Микрофон недоступен',
            VoiceState.LISTENING: '● Слушаю…',
            VoiceState.EXECUTING: '● Выполняю…',
        }.get(self.machine.state, '● Голос активен')
        self.panel.set_voice_status(status, self.config['voice_enabled'])
        self.voice_action.setChecked(self.config['voice_enabled'])
        self.tray.setToolTip('Brightness Voice Control\n' + ', '.join(
            f'{name}: {round(value)}%' for name, value in self.manager.named().items()))
        self._save()

    def _level(self, key, value):
        if hasattr(self, 'panel'):
            self.panel.update_level(key, value)

    def _raise_ui(self):
        if hasattr(self, 'panel') and self.panel.isVisible():
            self.panel.raise_()
        if hasattr(self, 'notice') and self.notice.isVisible():
            self.notice.raise_()

    def _show_panel(self):
        self._refresh()
        self.panel.show_near_cursor()

    def _preview_begin(self, monitor_id):
        for key in self.manager.key_for(None if monitor_id == '__all__' else monitor_id):
            self.manager.begin_preview(key)

    def _preview(self, monitor_id, value):
        for key in self.manager.key_for(None if monitor_id == '__all__' else monitor_id):
            self.manager.preview(key, value)

    def _preview_end(self, monitor_id):
        for key in self.manager.key_for(None if monitor_id == '__all__' else monitor_id):
            self.manager.commit_preview(key)
        self.config['active_profile'] = None
        self._refresh()

    def _preset(self, value):
        self.manager.set_named(None, value)
        self.config['active_profile'] = None
        self.notice.show_message(f'Все мониторы → {value}%')
        self._save()

    def _profile_by_id(self, profile_id):
        profile = next((p for p in self.config['profiles'] if p['id'] == profile_id), None)
        if profile:
            self.apply_profile(profile)

    def apply_profile(self, profile, duration=None):
        transition = duration if duration is not None else profile.get('transition_duration')
        for monitor_id, value in profile.get('monitor_values', {}).items():
            if monitor_id in self.manager.states:
                self.manager.set_value(monitor_id, value, transition)
        self.config['active_profile'] = profile['id']
        self.notice.show_message('Профиль: ' + profile['name'])
        self._say('Профиль ' + profile['name'] + ' включён.', important=True)
        self._save()

    def _schedule_tick(self):
        now = datetime.now()
        rule = latest_due_since(self.config['schedule'], self.last_schedule_check,
                                now, self.fired)
        self.last_schedule_check = now
        if rule:
            profile = next((p for p in self.config['profiles'] if p['id'] == rule.get('profile_id')), None)
            if profile:
                LOG.info('Schedule activated profile=%s', profile['id'])
                self.apply_profile(profile, rule.get('duration'))

    def _settings(self):
        self.panel.hide()
        if sync_autostart(self.config, is_autostart()):
            self._save()
        dialog = Settings(self.manager, self.config, self.voice, self.speaker, self)
        result = dialog.exec()
        if not result and not self.config['tray_tip_shown']:
            reminder = QMessageBox(QMessageBox.Icon.Information, 'Brightness Voice Control',
                'Приложение продолжает работать в системном трее.')
            checkbox = QCheckBox('Больше не показывать')
            reminder.setCheckBox(checkbox)
            reminder.exec()
            self.config['tray_tip_shown'] = checkbox.isChecked()
            self._save()

    def _onboarding(self):
        from brightness_control.onboarding import Onboarding
        wizard = Onboarding(self)
        wizard.exec()

    def settings_saved(self):
        try:
            set_autostart(self.config['autostart'])
        except OSError:
            LOG.exception('Could not set autostart')
            self.notice.show_message('Не удалось настроить автозапуск', error=True)
        sync_autostart(self.config, is_autostart())
        self.app.setStyleSheet(style(self.config['appearance']['theme']))
        self.notice.placement = self.config['notifications']['placement']
        self.voice.set_wake_phrase(self.config['wake_phrase'])
        if self.config['voice_enabled']:
            self.machine.transition('enable')
        else:
            self.machine.transition('disable')
        self._save()
        self._refresh()
        self.restart_voice()

    def apply_import(self, imported):
        self.config.update(imported)
        self.manager.refresh()
        for key in list(self.manager.states):
            self.manager.set_value(key, self.config['brightness'].get(key, 100), 0)
        self.settings_saved()

    def _toggle_voice(self, enabled):
        self.config['voice_enabled'] = bool(enabled)
        self.retry_timer.stop()
        self._timeout()
        if enabled:
            self.machine.transition('enable')
            self.restart_voice()
        else:
            self.machine.transition('disable')
            self.voice.stop()
            self.config['voice_runtime_available'] = False
        self._refresh()

    def restart_voice(self):
        self.retry_timer.stop()
        self.voice.stop()
        if self.config['voice_enabled']:
            device = self.config['microphone']
            name = self.config.get('microphone_name')
            if name:
                try:
                    matches = [idx for idx, label in self.voice.devices()
                               if label.split(': ', 1)[-1] == name]
                    if not matches:
                        self._voice_error('Выбранный микрофон не подключён')
                        return
                    device = matches[0]
                    self.config['microphone'] = device
                except Exception as exc:
                    self._voice_error(str(exc))
                    return
            self.voice.start(device)

    def _voice_ready(self):
        if not self.config['voice_enabled']:
            return
        recovered = self.machine.state == VoiceState.DEVICE_ERROR
        self.config['voice_runtime_available'] = True
        self.machine.transition('recovered')
        self.retry_index = 0
        if recovered:
            self.notice.show_message('Микрофон снова доступен')
        LOG.info('Voice engine ready')
        self._refresh()

    def _voice_error(self, message):
        if not self.config['voice_enabled']:
            return
        self.config['voice_runtime_available'] = False
        self.machine.transition('device_error')
        self.state_timer.stop()
        self.voice.set_mode('wake')
        self.pending = None
        delay = (2, 5, 10, 30, 60)[min(self.retry_index, 4)]
        self.retry_index += 1
        self.retry_timer.start(delay * 1000)
        LOG.warning('Voice device error; retry in %ss: %s', delay, message)
        if self.config['notifications']['errors']:
            self.notice.show_message('Микрофон недоступен. Попробуем подключиться автоматически.',
                                     error=True, timeout=6000)
        self._refresh()

    def _wake(self):
        if self.machine.state != VoiceState.WAKE_ONLY:
            return
        self.machine.transition('wake')
        LOG.info('Wake word detected')
        if self.config['wake_beep']:
            QApplication.beep()
        self.machine.transition('listen')
        if self.config['show_listening'] and self.config['notifications']['listening']:
            self.notice.show_message('Слушаю…', timeout=self.config['command_timeout'] * 1000,
                                     listening=True)
        self.state_timer.start(self.config['command_timeout'] * 1000)
        self._refresh()

    def _timeout(self, hide_notice=True):
        self.state_timer.stop()
        self.pending = None
        self.machine.transition('timeout')
        self.voice.set_mode('wake')
        if hide_notice:
            self.notice.hide()
        self._refresh()

    def _recognized(self, phrase, confidence):
        if not self.config['voice_enabled']:
            return
        if self.machine.state == VoiceState.CONFIRMATION:
            reply = parse(phrase)
            if reply and reply.intent in ('confirm', 'cancel'):
                self._decision(reply.intent == 'confirm')
            return
        if self.machine.state != VoiceState.LISTENING:
            return
        if phrase.strip().lower() in ('[unk]', ''):
            return
        found, text = split_wake(phrase, self.config['wake_phrase'])
        if found and not text:
            return
        self._command(text if found else phrase, confidence)

    def _command(self, phrase, confidence):
        self.machine.transition('command')
        aliases = {}
        for monitor_id in self.manager.active_monitor_ids():
            record = self.config['monitors'][monitor_id]
            for alias in [record['display_name'], *record['voice_aliases']]:
                key = normalize(alias)
                if key.startswith(('монитор ', 'экран ')) and key.split()[-1].isdecimal():
                    continue  # Ordinal parser resolves numbered display names.
                aliases.setdefault(key, [])
                if monitor_id not in aliases[key]:
                    aliases[key].append(monitor_id)
        command = parse(phrase, confidence, self.config['relative_step'],
                        self.config['minimum_brightness'], self.config['profiles'], aliases)
        if not command or confidence < .60 or command.intent in ('confirm', 'cancel'):
            self._say('Не удалось понять команду.', error=True)
            self.notice.show_message('Не понял команду. Попробуйте ещё раз.')
            self._timeout(False)
            return
        if command.target:
            keys = self.manager.key_for(command.target)
            if not keys:
                self._say('Монитор сейчас не подключён.', error=True)
                self.notice.show_message('Монитор сейчас не подключён', error=True)
                self._timeout(False)
                return
            if command.target.startswith('#'):
                command = replace(command, target=keys[0])
        human = replace(command, target=self.manager.display_name(command.target)) if command.target else command
        if command.requires_confirmation:
            self.pending = command
            self.machine.transition('uncertain')
            self.voice.set_mode('confirm')
            self.state_timer.start(9000)
            if self.config['notifications']['confirmation']:
                self.notice.show_message('Я правильно понял?\n' +
                    describe(human, self.manager.named()), confirm=True)
            self._say(spoken(human, self.manager.named(), question=True), important=True)
            return
        self._execute(command)

    def _decision(self, yes):
        if self.machine.state != VoiceState.CONFIRMATION or self.pending is None:
            return
        command = self.pending
        self.pending = None
        if yes:
            self._execute(command)
        else:
            self._say('Отменено.', important=True)
            self._timeout()

    def _execute(self, command):
        self.machine.transition('execute')
        human = replace(command, target=self.manager.display_name(command.target)) if command.target else command
        before_values = self.manager.named()
        if command.intent == 'activate_profile':
            self._profile_by_id(command.profile_id)
        elif command.intent == 'show_status':
            self._say(describe(command, self.manager.named()), important=True)
            self.notice.show_message(describe(command, self.manager.named()))
        else:
            for key in self.manager.key_for(command.target):
                state = self.manager.states[key]
                value = {
                    'set_brightness': command.value,
                    'change_brightness': state.current_brightness + (command.value or 0),
                    'max_brightness': 100,
                    'min_brightness': self.config['minimum_brightness'],
                    'blackout': 0,
                    'restore': state.restore(),
                }.get(command.intent)
                if value is not None:
                    before = state.current_brightness
                    self.manager.set_value(key, value)
                    LOG.info('Brightness %s %.1f -> %.1f', key, before, value)
            self.config['active_profile'] = None
            summary_values = before_values if command.intent == 'change_brightness' else self.manager.named()
            if self.config['notifications']['success']:
                self.notice.show_message(describe(human, summary_values),
                                         timeout=round(self.config['notifications']['duration'] * 1000))
            self._say(spoken(human, summary_values,
                             short=self.config['tts_mode'] == 'short'),
                      important=command.intent in ('blackout', 'restore'))
            LOG.info('Intent %s target=%s value=%s', command.intent, command.target, command.value)
        self.state_timer.stop()
        self.pending = None
        self.machine.transition('done')
        self.voice.set_mode('wake')
        self._refresh()

    def _tts_started(self):
        self.machine.transition('tts_start')

    def _tts_finished(self):
        self.machine.transition('tts_done')
        self.voice.set_mode('wake')

    def _say(self, text, error=False, important=False):
        mode = self.config['tts_response']
        if mode == 'off' or (mode == 'errors' and not error) or (
                mode == 'important' and not (important or error)):
            return
        self.speaker.say(text, {
            'voice': self.config['tts_voice'], 'volume': self.config['tts_volume'],
            'rate': self.config['tts_rate'],
        })

    def _unassigned(self, key):
        if hasattr(self, 'notice'):
            self.notice.show_message('Обнаружен монитор с неоднозначным ID. Назначьте имя в настройках.',
                                     error=True, timeout=6000)

    def close(self):
        self.schedule_timer.stop()
        self.state_timer.stop()
        self.retry_timer.stop()
        self.voice.stop()
        self.speaker.close()
        self._save()
        self.manager.shutdown()
        self.tray.hide()
        self.instance.close()
        LOG.info('Application stopped')
        self.app.quit()


def main():
    if sys.platform != 'win32':
        raise SystemExit('Программа предназначена для Windows 11.')
    setup_logging()
    if '--reset-brightness' in sys.argv:
        config = load()
        config['brightness'] = {}
        save(config)
        return 0
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, 'Brightness Voice Control', 'Системный трей недоступен.')
        return 1
    instance = SingleInstance()
    if not instance.acquire('settings' if '--settings' in sys.argv else 'panel'):
        return 0
    controller = Controller(app, instance)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
