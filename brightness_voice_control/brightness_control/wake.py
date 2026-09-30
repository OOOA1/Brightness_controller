"""Pure strict wake acceptance, independent of Qt and microphone devices."""
from .parser import normalize


def confirmed_wake(result: dict, phrase: str, threshold: float = .82,
                   final: bool = True) -> bool:
    if not final:
        return False
    expected = normalize(phrase).split()
    heard = normalize(result.get('text', '')).split()
    if not expected or heard[:len(expected)] != expected:
        return False
    words = result.get('result', [])
    if words:
        wake_words = words[:len(expected)]
        if [normalize(w.get('word', '')) for w in wake_words] != expected:
            return False
        return min((w.get('conf', 0.) for w in wake_words), default=0.) >= threshold
    return heard == expected
