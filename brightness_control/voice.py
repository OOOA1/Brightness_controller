"""Local streaming recognition and Windows local speech synthesis."""
import json
import queue
import threading
import time
from pathlib import Path
from PySide6.QtCore import QObject, Signal


def model_path() -> Path:
    import sys
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return root / "models" / "vosk-model-small-ru-0.22"


class Voice(QObject):
    recognized = Signal(str, float)
    error = Signal(str)
    level = Signal(float)

    def __init__(self):
        super().__init__()
        self.stop_event = threading.Event()
        self.muted = threading.Event()
        self.thread = None
        self.device = None

    @staticmethod
    def devices():
        import sounddevice as sd
        return [(i, f"{i}: {d['name']}") for i, d in enumerate(sd.query_devices()) if d['max_input_channels'] > 0]

    def start(self, device=None):
        self.stop()
        self.stop_event = threading.Event()
        self.device = device
        self.thread = threading.Thread(target=self._listen, args=(self.stop_event, device), daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=2)
        self.thread = None

    def _listen(self, stop_event, device):
        try:
            import sounddevice as sd
            from vosk import Model, KaldiRecognizer, SetLogLevel
            SetLogLevel(-1)
            path = model_path()
            if not path.is_dir():
                raise FileNotFoundError(f"Модель речи отсутствует: {path}. Запустите download_model.py")
            model = Model(str(path))
            source = sd.query_devices(device, 'input')
            sample_rate = int(source['default_samplerate'])
            recognizer = KaldiRecognizer(model, sample_rate)
            recognizer.SetWords(True)
            chunks = queue.Queue(maxsize=30)

            def callback(indata, frames, timing, status):
                if self.muted.is_set():
                    return
                try:
                    chunks.put_nowait(bytes(indata))
                except queue.Full:
                    pass

            with sd.RawInputStream(samplerate=sample_rate, blocksize=4000,
                                   device=device, dtype='int16', channels=1, callback=callback):
                last_level = 0.
                while not stop_event.is_set():
                    try:
                        chunk = chunks.get(timeout=.2)
                    except queue.Empty:
                        continue
                    if self.muted.is_set():
                        recognizer.Reset()
                        continue
                    if time.monotonic() - last_level > .25:
                        import audioop
                        self.level.emit(min(1., audioop.rms(chunk, 2) / 5000))
                        last_level = time.monotonic()
                    if recognizer.AcceptWaveform(chunk):
                        result = json.loads(recognizer.Result())
                        words = result.get('result', [])
                        phrase = result.get('text', '').strip()
                        if phrase:
                            confidence = min((w.get('conf', 1.) for w in words), default=1.)
                            self.recognized.emit(phrase, confidence)
        except Exception as exc:
            if not stop_event.is_set():
                self.error.emit(f"Микрофон или распознавание: {exc}")


class Speaker:
    def __init__(self, voice: Voice):
        self.voice = voice
        self.items = queue.Queue()
        self.closed = False
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def say(self, text):
        if not self.closed:
            self.items.put(text)

    def _run(self):
        # pyttsx3 uses SAPI5 locally on Windows; one engine stays on one thread.
        import pythoncom
        pythoncom.CoInitialize()
        try:
            import pyttsx3
            engine = pyttsx3.init('sapi5')
            voices = engine.getProperty('voices')
            for voice in voices:
                if 'ru' in str(voice.languages).lower() or 'russian' in voice.name.lower():
                    engine.setProperty('voice', voice.id)
                    break
            while True:
                message = self.items.get()
                if message is None:
                    break
                self.voice.muted.set()
                try:
                    engine.say(message)
                    engine.runAndWait()
                except Exception:
                    pass
                finally:
                    time.sleep(.15)
                    self.voice.muted.clear()
        finally:
            pythoncom.CoUninitialize()

    def close(self):
        self.closed = True
        self.items.put(None)
