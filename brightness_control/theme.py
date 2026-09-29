"""Small shared design system for panels, notifications, and settings."""
import ctypes
import sys
from PySide6.QtGui import QColor, QGuiApplication


def accent():
    if sys.platform == 'win32':
        try:
            color = ctypes.c_uint32()
            opaque = ctypes.c_int()
            if ctypes.windll.dwmapi.DwmGetColorizationColor(ctypes.byref(color),
                                                            ctypes.byref(opaque)) == 0:
                rgb = color.value & 0xFFFFFF
                return QColor(rgb).name()
        except (OSError, AttributeError):
            pass
    return '#7AA2FF'


def style(mode='dark'):
    if mode == 'system':
        mode = 'dark' if QGuiApplication.styleHints().colorScheme().name == 'Dark' else 'light'
    dark = mode == 'dark'
    bg, surface, elevated, text, secondary, border = (
        ('#101114', '#17191E', '#1E2127', '#F5F7FA', '#A9B0BC', '#30343D')
        if dark else
        ('#F4F6F9', '#FFFFFF', '#E8ECF2', '#1B2028', '#4E5969', '#CDD3DD'))
    color = accent()
    return f"""
    QWidget {{ background:{bg}; color:{text}; font-family:'Segoe UI Variable','Segoe UI'; font-size:14px; }}
    QDialog, QFrame#card, QWidget#panel {{ background:{surface}; }}
    QLabel#title {{ font-size:23px; font-weight:600; }}
    QLabel#section {{ font-size:17px; font-weight:600; }}
    QLabel#muted {{ color:{secondary}; }}
    QFrame#card {{ border:1px solid {border}; border-radius:14px; }}
    QPushButton {{ background:{elevated}; border:1px solid {border}; border-radius:9px;
                   padding:9px 14px; min-height:20px; }}
    QPushButton:hover {{ border-color:{color}; }}
    QPushButton:pressed {{ background:{color}; color:#101114; }}
    QPushButton#primary {{ background:{color}; color:#101114; font-weight:600; border:0; }}
    QPushButton:disabled {{ color:{secondary}; background:{surface}; }}
    QComboBox, QSpinBox, QDoubleSpinBox, QTimeEdit, QLineEdit {{
        background:{elevated}; border:1px solid {border}; border-radius:8px;
        padding:7px; min-height:22px;
    }}
    QComboBox::drop-down {{ border:0; width:24px; }}
    QSlider::groove:horizontal {{ height:6px; background:{border}; border-radius:3px; }}
    QSlider::sub-page:horizontal {{ background:{color}; border-radius:3px; }}
    QSlider::handle:horizontal {{ background:{text}; width:18px; margin:-6px 0;
                                  border-radius:9px; }}
    QListWidget {{ background:{surface}; border:0; outline:0; }}
    QListWidget::item {{ padding:12px; border-radius:8px; }}
    QListWidget::item:selected {{ background:{elevated}; color:{text}; }}
    QCheckBox {{ spacing:10px; }}
    QToolTip {{ background:{elevated}; color:{text}; border:1px solid {border}; }}
    """
