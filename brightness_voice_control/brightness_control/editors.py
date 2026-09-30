import uuid
from PySide6.QtCore import QTime
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
    QFormLayout, QHBoxLayout, QLineEdit, QPushButton, QSpinBox, QTimeEdit,
    QVBoxLayout, QWidget)

DAYS = ('Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс')


class ProfileEditor(QDialog):
    def __init__(self, manager, profile=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Профиль')
        self.profile = profile or {}
        self.manager = manager
        form = QFormLayout(self)
        self.name = QLineEdit(self.profile.get('name', ''))
        form.addRow('Название', self.name)
        self.icon = QComboBox()
        self.icon.addItems(['moon', 'sun', 'monitor'])
        self.icon.setCurrentText(self.profile.get('icon', 'monitor'))
        form.addRow('Иконка', self.icon)
        self.values = {}
        ids = list(dict.fromkeys([*manager.active_monitor_ids(),
                                  *self.profile.get('monitor_values', {})]))
        for monitor_id in ids:
            spin = QSpinBox()
            spin.setRange(0, 100)
            spin.setSuffix('%')
            spin.setValue(self.profile.get('monitor_values', {}).get(monitor_id, 100))
            name = manager.config['monitors'].get(monitor_id, {}).get('display_name', monitor_id)
            if monitor_id not in manager.states:
                name += ' (не подключён)'
            form.addRow(name, spin)
            self.values[monitor_id] = spin
        self.aliases = QLineEdit(', '.join(self.profile.get('voice_aliases', [])))
        form.addRow('Голосовые фразы через запятую', self.aliases)
        self.duration = QDoubleSpinBox()
        self.duration.setRange(0, 5)
        self.duration.setSingleStep(.1)
        self.duration.setSuffix(' с')
        self.duration.setSpecialValueText('Общий переход')
        self.duration.setValue(self.profile.get('transition_duration') or 0)
        form.addRow('Переход', self.duration)
        buttons = QHBoxLayout()
        save = QPushButton('Сохранить')
        save.setObjectName('primary')
        save.clicked.connect(self._accept)
        cancel = QPushButton('Отмена')
        cancel.clicked.connect(self.reject)
        buttons.addWidget(save)
        buttons.addWidget(cancel)
        form.addRow(buttons)

    def _accept(self):
        if self.name.text().strip():
            self.accept()

    def result_profile(self):
        return {
            'id': self.profile.get('id', uuid.uuid4().hex),
            'name': self.name.text().strip(), 'icon': self.icon.currentText(),
            'monitor_values': {mid: spin.value() for mid, spin in self.values.items()},
            'voice_aliases': [s.strip() for s in self.aliases.text().split(',') if s.strip()],
            'transition_duration': self.duration.value() or None,
            'legacy_monitor_values': self.profile.get('legacy_monitor_values', {}),
        }


class ScheduleEditor(QDialog):
    def __init__(self, profiles, rule=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Правило расписания')
        self.rule = rule or {}
        form = QFormLayout(self)
        self.time = QTimeEdit()
        self.time.setDisplayFormat('HH:mm')
        self.time.setTime(QTime.fromString(self.rule.get('time', '23:30'), 'HH:mm'))
        form.addRow('Время', self.time)
        self.profile = QComboBox()
        for profile in profiles:
            self.profile.addItem(profile['name'], profile['id'])
        current = self.profile.findData(self.rule.get('profile_id'))
        if current >= 0:
            self.profile.setCurrentIndex(current)
        form.addRow('Профиль', self.profile)
        days = QWidget()
        line = QHBoxLayout(days)
        line.setContentsMargins(0, 0, 0, 0)
        self.days = []
        for index, name in enumerate(DAYS):
            check = QCheckBox(name)
            check.setChecked(index in self.rule.get('days', list(range(7))))
            line.addWidget(check)
            self.days.append(check)
        form.addRow('Дни', days)
        self.enabled = QCheckBox('Включено')
        self.enabled.setChecked(self.rule.get('enabled', True))
        form.addRow(self.enabled)
        self.duration = QDoubleSpinBox()
        self.duration.setRange(0, 5)
        self.duration.setSingleStep(.1)
        self.duration.setSpecialValueText('Как у профиля')
        self.duration.setSuffix(' с')
        self.duration.setValue(self.rule.get('duration') or 0)
        form.addRow('Переход', self.duration)
        buttons = QHBoxLayout()
        save = QPushButton('Сохранить')
        save.setObjectName('primary')
        save.clicked.connect(self.accept)
        cancel = QPushButton('Отмена')
        cancel.clicked.connect(self.reject)
        buttons.addWidget(save)
        buttons.addWidget(cancel)
        form.addRow(buttons)

    def result_rule(self):
        return {
            'id': self.rule.get('id', uuid.uuid4().hex),
            'time': self.time.time().toString('HH:mm'),
            'days': [i for i, box in enumerate(self.days) if box.isChecked()],
            'profile_id': self.profile.currentData(), 'enabled': self.enabled.isChecked(),
            'duration': self.duration.value() or None,
        }
