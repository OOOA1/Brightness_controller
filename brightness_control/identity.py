"""Best-effort stable display identity; never silently choose between duplicates."""
import ctypes
import sys
from ctypes import wintypes


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [
        ('cb', wintypes.DWORD), ('DeviceName', wintypes.WCHAR * 32),
        ('DeviceString', wintypes.WCHAR * 128), ('StateFlags', wintypes.DWORD),
        ('DeviceID', wintypes.WCHAR * 128), ('DeviceKey', wintypes.WCHAR * 128),
    ]


def device_details(screen) -> dict:
    name = screen.name()
    info = {
        'screen_name': name, 'manufacturer': screen.manufacturer() or '',
        'model': screen.model() or '', 'serial': screen.serialNumber() or '',
        'friendly_name': screen.model() or name, 'device_path': '',
        'geometry': [screen.geometry().x(), screen.geometry().y(),
                     screen.geometry().width(), screen.geometry().height()],
    }
    if sys.platform == 'win32':
        try:
            device = DISPLAY_DEVICEW()
            device.cb = ctypes.sizeof(DISPLAY_DEVICEW)
            if ctypes.windll.user32.EnumDisplayDevicesW(name, 0, ctypes.byref(device), 0):
                info['device_path'] = device.DeviceID.strip()
                info['friendly_name'] = device.DeviceString.strip() or info['friendly_name']
        except (OSError, ValueError):
            pass
    if info['serial']:
        info['stable_id'] = ':'.join(
            ['edid', info['manufacturer'], info['model'], info['serial']]).lower()
    elif info['device_path']:
        info['stable_id'] = 'device:' + info['device_path'].lower()
    else:
        info['stable_id'] = 'screen:' + name.lower()
    return info
