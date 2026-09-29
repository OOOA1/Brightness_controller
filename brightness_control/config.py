import json
import os
from pathlib import Path


def config_path() -> Path:
    return Path(os.environ.get("APPDATA", str(Path.home()))) / "BrightnessVoiceControl" / "config.json"


DEFAULT = {
    "monitors": {}, "brightness": {}, "voice_enabled": True, "tts_enabled": True,
    "microphone": None, "duration": 1.5, "remember_brightness": True,
    "autostart": False, "start_in_tray": True,
}


def load() -> dict:
    result = {**DEFAULT}
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            result.update({key: data[key] for key in DEFAULT if key in data and
                           isinstance(data[key], type(DEFAULT[key]))})
            if data.get("microphone") is None or isinstance(data.get("microphone"), int):
                result["microphone"] = data.get("microphone")
    except (OSError, ValueError, TypeError):
        pass
    result["duration"] = min(10., max(.1, float(result["duration"])))
    return result


def save(data: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
