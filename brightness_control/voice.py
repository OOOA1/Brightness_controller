"""Vosk streaming ASR: small wake grammar, full command grammar, yes/no grammar."""
from collections import deque
import json
import logging
import queue
import threading
import time
from pathlib import Path
from PySide6.QtCore import QObject, Signal

LOG = logging.getLogger(__name__)


def model_path() -> Path:
    import sys
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    return root / 'models' / 'vosk-model-small-ru-0.22'


class Voice(QObject):
    wake_detected = Signal()
    recognized = Signal(str, float)
    ready = Signal()
    error = Signal(str)
    level = Signal(float)

    def __init__(self):
        super().__init__()
        self.stop_event = threading.Event()
        self.muted = threading.Event()
        self.thread = None
        self.mode = 'wake'
        self.device = None

    @staticmethod
    def devices():
        import sounddevice as sd
        return [(i, f"{i}: {d['name']}") for i, d in enumerate(sd.query_devices())
                if d['max_input_channels'] > 0]

    def set_mode(self, mode):
        self.mode = mode

    def start(self, device=None):
        self.stop()
        self.stop_event = threading.Event()
        self.device = device
        self.mode = 'wake'
        self.thread = threading.Thread(target=self._listen, args=(self.stop_event, device),
                                       daemon=True, name='Vosk listener')
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=3)
        self.thread = None

    def _listen(self, stop_event, device):
        try:
            import sounddevice as sd
            from vosk import Model, KaldiRecognizer, SetLogLevel
            SetLogLevel(-1)
            path = model_path()
            if not path.is_dir():
                raise FileNotFoundError(f'Модель речи не найдена: {path}')
            model = Model(str(path))
            if stop_event.is_set():
                return
            source = sd.query_devices(device, 'input')
            rate = int(source['default_samplerate'])
            wake = KaldiRecognizer(model, rate, json.dumps(['компьютер', '[unk]'], ensure_ascii=False))
            command = KaldiRecognizer(model, rate)
            command.SetWords(True)
            confirm = KaldiRecognizer(model, rate, json.dumps(
                ['да', 'подтверждаю', 'верно', 'нет', 'отмена', 'не надо', '[unk]'],
                ensure_ascii=False))
            confirm.SetWords(True)
            chunks = queue.Queue(maxsize=32)
            recent = deque(maxlen=max(8, int(rate * 3 / 4000)))
            current_mode = 'wake'
            last_level = 0.

            def callback(indata, frames, timing, status):
                if self.muted.is_set() or stop_event.is_set():
                    return
                try:
                    chunks.put_nowait(bytes(indata))
                except queue.Full:
                    pass

            def emit_result(recognizer, data=None, final=False):
                if data is None:
                    result = json.loads(recognizer.FinalResult() if final else recognizer.Result())
                else:
                    result = data
                phrase = result.get('text', '').strip()
                if phrase:
                    words = result.get('result', [])
                    confidence = min((word.get('conf', 1.) for word in words), default=1.)
                    self.recognized.emit(phrase, confidence)

            with sd.RawInputStream(samplerate=rate, blocksize=4000,
                                   device=device, dtype='int16', channels=1, callback=callback):
                self.ready.emit()
                while not stop_event.is_set():
                    try:
                        chunk = chunks.get(timeout=.25)
                    except queue.Empty:
                        continue
                    if self.muted.is_set():
                        wake.Reset()
                        command.Reset()
                        confirm.Reset()
                        recent.clear()
                        continue
                    mode = self.mode
                    if mode != current_mode:
                        wake.Reset()
                        command.Reset()
                        confirm.Reset()
                        recent.clear()
                        current_mode = mode
                    if time.monotonic() - last_level > .25:
                        # Avoid audioop (removed in newer Python).
                        import array
                        samples = array.array('h', chunk)
                        if samples:
                            rms = (sum(v * v for v in samples) / len(samples)) ** .5
                            self.level.emit(min(1., rms / 5000))
                        last_level = time.monotonic()
                    if mode == 'wake':
                        recent.append(chunk)
                        completed = wake.AcceptWaveform(chunk)
                        text = json.loads(wake.Result() if completed else wake.PartialResult())
                        phrase = text.get('text' if completed else 'partial', '')
                        if 'компьютер' in phrase.split():
                            self.mode = current_mode = 'command'
                            self.wake_detected.emit()
                            command.Reset()
                            # Replay the wake utterance so an uninterrupted
                            # 'Компьютер, левый 20' is not lost.
                            for part in recent:
                                if command.AcceptWaveform(part):
                                    emit_result(command)
                            recent.clear()
                            wake.Reset()
                    elif mode == 'command':
                        if command.AcceptWaveform(chunk):
                            emit_result(command)
                    elif mode == 'confirm':
                        if confirm.AcceptWaveform(chunk):
                            emit_result(confirm)
        except Exception as exc:
            if not stop_event.is_set():
                LOG.exception('Voice input failed')
                self.error.emit(str(exc))


class Speaker:
    def __init__(self, voice: Voice):
        self.voice = voice
        self.items = queue.Queue()
        self.closed = False
        self.thread = threading.Thread(target=self._run, daemon=True, name='Windows TTS')
        self.thread.start()

    def say(self, text, settings=None):
        if not self.closed:
            self.items.put((text, settings or {}))

    def _run(self):
        import pythoncom
        pythoncom.CoInitialize()
        try:
            import pyttsx3
            engine = pyttsx3.init('sapi5')
            voices = engine.getProperty('voices')
            default_voice = next((v.id for v in voices if 'ru' in str(v.languages).lower() or
                                  'russian' in v.name.lower()), None)
            while True:
                item = self.items.get()
                if item is None:
                    break
                message, settings = item
                self.voice.muted.set()
                try:
                    engine.setProperty('voice', settings.get('voice') or default_voice or engine.getProperty('voice'))
                    engine.setProperty('volume', max(0., min(1., settings.get('volume', 100) / 100)))
                    engine.setProperty('rate', 185 + settings.get('rate', 0))
                    engine.say(message)
                    engine.runAndWait()
                except Exception:
                    LOG.exception('TTS failed')
                finally:
                    time.sleep(.2)
                    self.voice.muted.clear()
        except Exception:
            LOG.exception('Could not start Windows TTS')
        finally:
            pythoncom.CoUninitialize()

    def close(self):
        self.closed = True
        self.items.put(None)
        self.thread.join(timeout=3)
