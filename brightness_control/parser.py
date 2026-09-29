"""Side-effect-free parser for supported Russian brightness phrases."""
from dataclasses import dataclass
import re

NAMES = ("Левый", "Центральный", "Правый")
ONES = {
    "ноль": 0, "один": 1, "одна": 1, "одного": 1, "первый": 1, "первого": 1,
    "два": 2, "две": 2, "двух": 2, "второй": 2, "второго": 2,
    "три": 3, "трех": 3, "третий": 3, "третьего": 3, "четыре": 4,
    "четырех": 4, "пять": 5, "пяти": 5, "шесть": 6, "шести": 6,
    "семь": 7, "семи": 7, "восемь": 8, "восьми": 8, "девять": 9, "девяти": 9,
}
TEENS = {
    "десять": 10, "десяти": 10, "одиннадцать": 11, "одиннадцати": 11,
    "двенадцать": 12, "двенадцати": 12, "тринадцать": 13, "тринадцати": 13,
    "четырнадцать": 14, "четырнадцати": 14, "пятнадцать": 15, "пятнадцати": 15,
    "шестнадцать": 16, "шестнадцати": 16, "семнадцать": 17, "семнадцати": 17,
    "восемнадцать": 18, "восемнадцати": 18, "девятнадцать": 19, "девятнадцати": 19,
}
TENS = {
    "двадцать": 20, "двадцати": 20, "тридцать": 30, "тридцати": 30,
    "сорок": 40, "пятьдесят": 50, "пятидесяти": 50,
    "шестьдесят": 60, "шестидесяти": 60, "семьдесят": 70,
    "семидесяти": 70, "восемьдесят": 80, "восьмидесяти": 80,
    "девяносто": 90, "девяноста": 90,
}
WORD = {**ONES, **TEENS, **TENS, "сто": 100}
TARGETS = {
    "Левый": r"\b(?:лев\w*|слева)\b",
    "Центральный": r"\b(?:центральн\w*|центр\w*|посередине|средн\w*)\b",
    "Правый": r"\b(?:прав\w*|справа)\b",
}
WAKE = re.compile(r"\bкомпьютер\b")
NUMBER_MONITOR = re.compile(r"\bмонитор(?:а|у|ом|ы|ов)?\s+(1|2|3|один|два|три|первый|второй|третий)\b|\b(первый|второй|третий)\s+(?:монитор|экран)\b")


@dataclass(frozen=True)
class Command:
    intent: str
    target: str | None = None  # logical name, '#1' ordinal, or all
    value: int | None = None
    confidence: float = 1.0
    requires_confirmation: bool = False
    raw_text: str = ""
    profile_id: str | None = None

    @property
    def mode(self):
        return 'relative' if self.intent == 'change_brightness' else 'set'

    @property
    def uncertain(self):
        return self.requires_confirmation


def normalize(text: str) -> str:
    return ' '.join(re.sub(r"[^\w\s]", ' ', text.lower().replace('ё', 'е')).split())


def split_wake(text: str) -> tuple[bool, str]:
    clean = normalize(text)
    match = WAKE.search(clean)
    return bool(match), clean[match.end():].strip() if match else ''


def _numbers(words: list[str]) -> list[int]:
    values = []
    i = 0
    while i < len(words):
        word = words[i]
        if word.isdecimal():
            values.append(int(word))
        elif word in WORD:
            value = WORD[word]
            if word in TENS and i + 1 < len(words) and words[i + 1] in ONES and ONES[words[i + 1]] < 10:
                value += ONES[words[i + 1]]
                i += 1
            values.append(value)
        i += 1
    return values


def parse(text: str, confidence: float = 1., step: int = 10,
          minimum: int = 5, profiles: list[dict] | None = None,
          aliases: dict[str, str] | None = None) -> Command | None:
    raw = normalize(text)
    if not raw:
        return None
    confidence = max(0., min(1., float(confidence)))
    def command(intent, target=None, value=None, profile_id=None):
        return Command(intent, target, value, confidence, .60 <= confidence < .82,
                       raw, profile_id)
    if raw in ('да', 'подтверждаю', 'верно'):
        return command('confirm')
    if raw in ('нет', 'отмена', 'не надо'):
        return command('cancel')
    targets = [name for name, pattern in TARGETS.items() if re.search(pattern, raw)]
    for alias, name in (aliases or {}).items():
        alias = normalize(alias)
        if alias and re.search(r'\b' + re.escape(alias) + r'\b', raw):
            targets.append(name)
    ordinal = NUMBER_MONITOR.search(raw)
    if ordinal:
        word = next(g for g in ordinal.groups() if g is not None)
        idx = int(word) if word.isdecimal() else ONES[word]
        targets.append(f'#{idx}')
        raw_without_ordinal = raw[:ordinal.start()] + ' ' + raw[ordinal.end():]
    else:
        raw_without_ordinal = raw
    if len(set(targets)) > 1:
        return None
    target = targets[0] if targets else None
    values = _numbers(raw_without_ordinal.split())
    if len(values) > 1 or (values and values[0] > 100):
        return None
    if re.search(r'\b(?:статус|текущ\w*|сколько|какая сейчас яркость)\b', raw):
        return command('show_status', target)
    for profile in profiles or []:
        aliases = [profile.get('name', ''), *(profile.get('voice_aliases') or [])]
        if normalize(profile.get('name', '')) == 'сон':
            aliases.append('сна')
        for alias in aliases:
            alias = normalize(str(alias))
            if alias and raw in (alias, 'режим ' + alias, 'включи режим ' + alias,
                                 'активируй ' + alias):
                return command('activate_profile', profile_id=profile.get('id'))
    if re.search(r'\b(?:выключ\w*|погаси|потуши)\b', raw) and target:
        return command('blackout', target) if not values else None
    if re.search(r'\b(?:включ\w*|верни|восстанов\w*)\b', raw) and target:
        return command('restore', target) if not values else None
    if re.search(r'\b(?:минимум|минимальн\w*)\b', raw) or 'максимально темно' in raw:
        return command('min_brightness', target, minimum) if not values else None
    if re.search(r'\b(?:максимум|максимальн\w*|полную)\b', raw):
        return command('max_brightness', target) if not values else None
    dark = bool(re.search(r'\b(?:темнее|потемнее|убав\w*|уменьш\w*|сниз\w*|затемн\w*)\b', raw))
    light = bool(re.search(r'\b(?:ярче|посветлее|светлее|добав\w*|увелич\w*|повысь|прибав\w*)\b', raw))
    if dark and light:
        return None
    absolute_marker = bool(re.search(r'\b(?:до|постав\w*|установ\w*)\b', raw))
    relative_marker = bool(re.search(r'\b(?:темнее|ярче|убав\w*|добав\w*|уменьш\w*|увелич\w*|прибав\w*)\b', raw))
    if (dark or light) and (not values or (relative_marker and not absolute_marker) or
                             (re.search(r'\b(?:сниз\w*|затемн\w*|повысь)\b', raw) and
                              re.search(r'\bна\s+', raw) and not absolute_marker)):
        return command('change_brightness', target, (1 if light else -1) * (values[0] if values else step))
    context = bool(target or re.search(r'\b(?:ярк\w*|монитор\w*|экран\w*|постав\w*|установ\w*|сдела\w*|сниз\w*|затемн\w*)\b', raw))
    if values and context:
        return command('set_brightness', target, values[0])
    return None


def describe(command: Command, values: dict[str, int | float]) -> str:
    label = command.target or 'Все мониторы'
    if command.intent == 'activate_profile':
        return 'Профиль активирован'
    if command.intent == 'show_status':
        return ', '.join(f'{k}: {round(v)}%' for k, v in values.items())
    if command.intent == 'restore':
        return f'{label} → прежняя яркость'
    if command.intent == 'blackout':
        return f'{label} → 0%'
    if command.intent == 'max_brightness':
        return f'{label} → 100%'
    if command.intent in ('set_brightness', 'min_brightness'):
        return f'{label} → {command.value}%'
    names = [label] if command.target else list(values)
    return ', '.join(f'{n} → {max(0, min(100, round(values[n] + command.value)))}%' for n in names if n in values)


def spoken(command: Command, values: dict[str, int | float], question=False, short=True) -> str:
    summary = describe(command, values).replace('→', ' — ').replace('%', ' процентов')
    if question:
        return 'Я правильно понял: ' + summary + '?'
    if command.intent == 'max_brightness' and command.target is None:
        return 'Хорошо. Яркость максимальная.'
    return summary + '.' if short else 'Хорошо, ' + summary + '.'
