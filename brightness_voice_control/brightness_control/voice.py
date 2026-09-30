"""Vosk streaming ASR: small wake grammar, full command grammar, yes/no grammar."""
from collections import deque
import json
import logging
import queue
import threading
import time
from pathlib import Path
from PySide6.QtCore import QObject, Signal
from .parser import normalize
from .wake import confirmed_wake

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
    wake_test_result = Signal(bool)

    def __init__(self, wake_phrase='компьютер'):
        super().__init__()
        self.stop_event = threading.Event()
        self.muted = threading.Event()
        self.thread = None
        self.mode = 'wake'
        self.device = None
        self._lock = threading.Lock()
        self.wake_phrase = normalize(wake_phrase) or 'компьютер'
        self.test_phrase = ''
        self._generation = 0
        self._test_origin = None

    @staticmethod
    def devices():
        import sounddevice as sd
        return [(i, f"{i}: {d['name']}") for i, d in enumerate(sd.query_devices())
                if d['max_input_channels'] > 0]

    def set_mode(self, mode):
        with self._lock:
            self.mode = mode

    def set_wake_phrase(self, phrase):
        normalized = normalize(phrase)
        if not normalized:
            raise ValueError('Ключевая фраза не может быть пустой')
        with self._lock:
            self.wake_phrase = normalized
            self._generation += 1
            self.mode = 'wake'

    def _test_stream(self, device, mode, phrase=''):
        if self._test_origin is not None:
            self.cancel_wake_test()
        with self._lock:
            self.test_phrase = phrase
        if not self.is_listening_to(device):
            self._test_origin = (bool(self.thread and self.thread.is_alive()), self.device)
            self.start(device, initial_mode=mode)
        else:
            self.set_mode(mode)

    def is_listening_to(self, device):
        return bool(self.thread and self.thread.is_alive() and
                    not self.stop_event.is_set() and self.device == device)

    def test_wake_phrase(self, phrase, device=None):
        normalized = normalize(phrase)
        if not normalized:
            raise ValueError('Ключевая фраза не может быть пустой')
        self._test_stream(device, 'test', normalized)

    def begin_microphone_test(self, device=None):
        self._test_stream(device, 'meter')

    def cancel_wake_test(self):
        origin = self._test_origin
        self._test_origin = None
        if origin is not None:
            was_running, original_device = origin
            if was_running:
                self.start(original_device)
            else:
                self.stop()
        elif self.mode in ('test', 'meter'):
            self.reset_audio()

    def reset_audio(self):
        """Invalidate recognizer state and queued audio after local speech."""
        with self._lock:
            self._generation += 1
            self.mode = 'wake'

    def start(self, device=None, initial_mode='wake'):
        self.stop()
        self.stop_event = threading.Event()
        self.device = device
        self.set_mode(initial_mode)
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
            def wake_recognizer(phrase):
                grammar = json.dumps([phrase, '[unk]'], ensure_ascii=False)
                recognizer = KaldiRecognizer(model, rate, grammar)
                recognizer.SetWords(True)
                return recognizer

            with self._lock:
                wake_phrase = self.wake_phrase
                generation = self._generation
            wake = wake_recognizer(wake_phrase)
            command = KaldiRecognizer(model, rate)
            command.SetWords(True)
            confirm = KaldiRecognizer(model, rate, json.dumps(
                ['да', 'подтверждаю', 'верно', 'нет', 'отмена', 'не надо', '[unk]'],
                ensure_ascii=False))
            confirm.SetWords(True)
            chunks = queue.Queue(maxsize=32)
            recent = deque(maxlen=max(8, int(rate * 8 / 4000)))
            current_mode = 'wake'
            last_level = 0.
            muted_seen = False
            test_recognizer = None
            test_phrase = ''

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
                        muted_seen = True
                        wake.Reset()
                        command.Reset()
                        confirm.Reset()
                        recent.clear()
                        while not chunks.empty():
                            try:
                                chunks.get_nowait()
                            except queue.Empty:
                                break
                        continue
                    if muted_seen:
                        wake.Reset()
                        command.Reset()
                        confirm.Reset()
                        recent.clear()
                        muted_seen = False
                    with self._lock:
                        mode = self.mode
                        configured = self.wake_phrase
                        new_generation = self._generation
                        candidate = self.test_phrase
                    if new_generation != generation:
                        generation = new_generation
                        wake_phrase = configured
                        wake = wake_recognizer(wake_phrase)
                        command.Reset()
                        confirm.Reset()
                        recent.clear()
                        while not chunks.empty():
                            try:
                                chunks.get_nowait()
                            except queue.Empty:
                                break
                        current_mode = 'wake'
                        continue
                    if mode != current_mode:
                        wake.Reset()
                        command.Reset()
                        confirm.Reset()
                        recent.clear()
                        current_mode = mode
                        if mode == 'test':
                            test_phrase = candidate
                            test_recognizer = wake_recognizer(test_phrase)
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
                        if completed and confirmed_wake(json.loads(wake.Result()), wake_phrase):
                            self.set_mode('command')
                            current_mode = 'command'
                            self.wake_detected.emit()
                            command.Reset()
                            # Replay the wake utterance so an uninterrupted
                            # 'Компьютер, левый 20' is not lost.
                            for part in recent:
                                if command.AcceptWaveform(part):
                                    emit_result(command)
                            recent.clear()
                            wake.Reset()
                        elif completed:
                            recent.clear()
                    elif mode == 'test' and test_recognizer:
                        if test_recognizer.AcceptWaveform(chunk):
                            success = confirmed_wake(json.loads(test_recognizer.Result()), test_phrase)
                            self.wake_test_result.emit(success)
                            self.set_mode('wake')
                    elif mode == 'meter':
                        pass
                    elif mode == 'command':
                        if command.AcceptWaveform(chunk):
                            emit_result(command)
                    elif mode == 'confirm':
                        if confirm.AcceptWaveform(chunk):
                            emit_result(confirm)
        except Exception as exc:
            if not stop_event.is_set():
                LOG.exception('Voice input failed')
                if self.mode in ('test', 'meter'):
                    self.wake_test_result.emit(False)
                else:
                    self.error.emit(str(exc))


from .tts import Speaker  # backward-compatible import
