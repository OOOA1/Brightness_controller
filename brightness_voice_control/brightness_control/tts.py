"""Local speech provider boundary; add future engines without changing Controller."""
import logging
import queue
import threading
import time
from typing import Protocol
from PySide6.QtCore import QObject, Signal

LOG = logging.getLogger(__name__)


class TTSProvider(Protocol):
    def list_voices(self) -> list[tuple[str, str]]: ...
    def speak(self, text: str, settings: dict) -> None: ...
    def stop(self) -> None: ...
    def preview(self, text: str, settings: dict) -> None: ...
    def is_available(self) -> bool: ...


class WindowsSAPIProvider:
    def __init__(self):
        import pyttsx3
        self.engine = pyttsx3.init('sapi5')

    @staticmethod
    def list_voices() -> list[tuple[str, str]]:
        import pythoncom
        pythoncom.CoInitialize()
        try:
            import win32com.client
            collection = win32com.client.Dispatch('SAPI.SpVoice').GetVoices()
            return [(collection.Item(i).Id, collection.Item(i).GetDescription())
                    for i in range(collection.Count)]
        except Exception:
            LOG.exception('Cannot enumerate SAPI voices')
            return []
        finally:
            pythoncom.CoUninitialize()

    def is_available(self) -> bool:
        return bool(self.engine)

    def speak(self, text: str, settings: dict) -> None:
        voices = self.engine.getProperty('voices')
        selected = settings.get('voice', '')
        ids = {voice.id for voice in voices}
        fallback = next((v.id for v in voices if 'ru' in str(v.languages).lower() or
                         'russian' in v.name.lower()), voices[0].id if voices else None)
        if selected not in ids:
            selected = fallback
        if selected:
            self.engine.setProperty('voice', selected)
        self.engine.setProperty('volume', max(0., min(1., settings.get('volume', 100) / 100)))
        self.engine.setProperty('rate', 185 + settings.get('rate', 0))
        self.engine.say(text)
        self.engine.runAndWait()

    def preview(self, text: str, settings: dict) -> None:
        self.speak(text, settings)

    def stop(self) -> None:
        self.engine.stop()


class Speaker(QObject):
    started = Signal()
    finished = Signal()

    def __init__(self, voice):
        super().__init__()
        self.voice = voice
        self.items = queue.Queue()
        self.closed = False
        self.thread = threading.Thread(target=self._run, daemon=True, name='Windows TTS')
        self.thread.start()

    @staticmethod
    def list_voices() -> list[tuple[str, str]]:
        return WindowsSAPIProvider.list_voices()

    def say(self, text, settings=None):
        if not self.closed:
            self.items.put((text, settings or {}))

    def preview(self, text, settings=None):
        self.say(text, settings)

    def _run(self):
        import pythoncom
        pythoncom.CoInitialize()
        try:
            provider: TTSProvider = WindowsSAPIProvider()
            while True:
                item = self.items.get()
                if item is None:
                    break
                message, settings = item
                self.voice.muted.set()
                self.started.emit()
                try:
                    provider.speak(message, settings)
                except Exception:
                    LOG.exception('TTS failed')
                finally:
                    time.sleep(.2)
                    self.voice.reset_audio()
                    self.voice.muted.clear()
                    self.finished.emit()
            provider.stop()
        except Exception:
            LOG.exception('Could not start Windows TTS')
        finally:
            pythoncom.CoUninitialize()

    def close(self):
        self.closed = True
        self.items.put(None)
        self.thread.join(timeout=3)
