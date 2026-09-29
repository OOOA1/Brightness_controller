"""Conservative Russian command parser; no side effects."""
from dataclasses import dataclass
import re

NAMES = ("Левый", "Центральный", "Правый")
ONES = {"ноль": 0, "один": 1, "одна": 1, "два": 2, "две": 2, "три": 3,
        "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9}
TEENS = {"десять": 10, "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13,
         "четырнадцать": 14, "пятнадцать": 15, "шестнадцать": 16, "семнадцать": 17,
         "восемнадцать": 18, "девятнадцать": 19}
TENS = {"двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50,
        "шестьдесят": 60, "семьдесят": 70, "восемьдесят": 80, "девяносто": 90}
WORD = {**ONES, **TEENS, **TENS, "сто": 100}
TARGETS = {
    "Левый": r"\b(?:лев\w*|слева)\b",
    "Центральный": r"\b(?:центральн\w*|центр\w*|посередине|средн\w*)\b",
    "Правый": r"\b(?:прав\w*|справа)\b",
}
WAKE = re.compile(r"\bкомпьютер\b", re.I)


@dataclass(frozen=True)
class Command:
    target: str | None
    mode: str  # set or relative
    value: int
    uncertain: bool = False


def normalize(text: str) -> str:
    return re.sub(r"[^\w\s]", " ", text.lower().replace("ё", "е")).strip()


def split_wake(text: str) -> tuple[bool, str]:
    clean = normalize(text)
    match = WAKE.search(clean)
    return (bool(match), clean[match.end():].strip() if match else "")


def _numbers(words: list[str]) -> list[int]:
    result = []
    i = 0
    while i < len(words):
        word = words[i]
        if word.isdecimal():
            result.append(int(word))
        elif word in WORD:
            value = WORD[word]
            if word in TENS and i + 1 < len(words) and words[i + 1] in ONES:
                value += ONES[words[i + 1]]
                i += 1
            result.append(value)
        i += 1
    return result


def parse(text: str, confidence: float = 1.0) -> Command | None:
    clean = normalize(text)
    targets = [name for name, pattern in TARGETS.items() if re.search(pattern, clean)]
    if len(targets) > 1:
        return None
    target = targets[0] if targets else None
    if re.search(r"\b(?:максимум|максимальн\w*|полную)\b", clean):
        if _numbers(clean.split()):
            return None
        return Command(target, "set", 100, confidence < .78)
    values = _numbers(clean.split())
    # Ignore ordinary prose containing a number without a brightness/monitor verb.
    context = bool(target or re.search(r"\b(?:ярк\w*|монитор\w*|экран\w*|затемн\w*|сниз\w*|постав\w*|установ\w*|сдела\w*|убав\w*|добав\w*)\b", clean))
    if values:
        if len(values) != 1 or values[0] > 100 or not context:
            return None
        return Command(target, "set", values[0], confidence < .78)
    dark = bool(re.search(r"\b(?:темнее|потемнее|убав\w*|уменьш\w*|сниз\w*|затемн\w*)\b", clean))
    light = bool(re.search(r"\b(?:ярче|посветлее|светлее|добав\w*|увелич\w*|повысь)\b", clean))
    if dark == light:
        return None
    return Command(target, "relative", -10 if dark else 10, confidence < .78)


def describe(command: Command, values: dict[str, int]) -> str:
    names = [command.target] if command.target else list(values)
    if command.mode == "set":
        if command.value == 100 and not command.target:
            return "Все мониторы → 100%"
        return f"{command.target or 'Все мониторы'} → {command.value}%"
    return ", ".join(f"{name} → {max(0, min(100, values[name] + command.value))}%" for name in names)


def spoken(command: Command, values: dict[str, int], question: bool = False) -> str:
    if command.mode == "set" and command.value == 100 and not command.target and not question:
        return "Хорошо, яркость максимальная."
    if command.mode == "set":
        part = f"{command.target.lower()} монитор" if command.target else "все мониторы"
        return (f"Я правильно понял: {part}, {command.value} процентов?" if question else
                f"Хорошо, устанавливаю яркость: {part}, {command.value} процентов.")
    return ("Я правильно понял: " if question else "Хорошо, ") + describe(command, values).replace("→", "до") + "."
