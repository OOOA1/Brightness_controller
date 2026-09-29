from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QCursor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class Notice(QWidget):
    decision = Signal(bool)
    settings_requested = Signal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMinimumWidth(380)
        self.setMaximumWidth(420)
        self.placement = 'primary'
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        title = QLabel('Brightness Voice Control')
        title.setObjectName('section')
        layout.addWidget(title)
        self.message = QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.buttons = QWidget()
        row = QHBoxLayout(self.buttons)
        row.setContentsMargins(0, 0, 0, 0)
        cancel = QPushButton('Нет')
        cancel.clicked.connect(lambda: self.decision.emit(False))
        accept = QPushButton('Да')
        accept.setObjectName('primary')
        accept.clicked.connect(lambda: self.decision.emit(True))
        row.addWidget(cancel)
        row.addStretch()
        row.addWidget(accept)
        layout.addWidget(self.buttons)
        self.settings_button = QPushButton('Открыть настройки')
        self.settings_button.clicked.connect(self.settings_requested.emit)
        layout.addWidget(self.settings_button)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)

    def show_message(self, message, confirm=False, error=False, timeout=2500):
        self.message.setText(message)
        self.buttons.setVisible(confirm)
        self.settings_button.setVisible(error)
        screen = (QGuiApplication.screenAt(QCursor.pos()) if self.placement == 'cursor'
                  else QGuiApplication.primaryScreen())
        if screen:
            self.setScreen(screen)
        self.adjustSize()
        area = (screen or self.screen()).availableGeometry()
        self.move(area.right() - self.width() - 24, area.bottom() - self.height() - 24)
        self.show()
        self.raise_()
        self.timer.stop()
        if not confirm:
            self.timer.start(timeout)
