"""Run once while online; recognition itself never uses the network."""
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile
import io

URL = 'https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip'
ROOT = Path(__file__).resolve().parent
TARGET = ROOT / 'models' / 'vosk-model-small-ru-0.22'


def main():
    if (TARGET / 'am').is_dir():
        print('Модель уже установлена:', TARGET)
        return
    print('Загрузка модели Vosk, около 45 МБ...')
    with urlopen(URL, timeout=90) as response:
        archive = io.BytesIO(response.read())
    (ROOT / 'models').mkdir(exist_ok=True)
    with ZipFile(archive) as zip_file:
        for member in zip_file.infolist():
            path = (ROOT / 'models' / member.filename).resolve()
            if not path.is_relative_to((ROOT / 'models').resolve()):
                raise ValueError('Небезопасный путь в архиве модели')
        zip_file.extractall(ROOT / 'models')
    if not (TARGET / 'am').is_dir():
        raise RuntimeError('Архив модели неполный')
    print('Модель установлена:', TARGET)


if __name__ == '__main__':
    main()
