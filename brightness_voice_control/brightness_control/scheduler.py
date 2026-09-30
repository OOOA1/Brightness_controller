"""Daily profile rules; called on Qt main thread by a low-frequency timer."""
from datetime import datetime, timedelta


def due_rules(rules: list[dict], now: datetime, fired: set[str]) -> list[dict]:
    due = []
    minute = now.strftime('%H:%M')
    weekday = now.weekday()  # Monday == 0
    for index, rule in enumerate(rules):
        if not rule.get('enabled', True) or rule.get('time') != minute:
            continue
        if weekday not in rule.get('days', list(range(7))):
            continue
        identifier = str(rule.get('id', index)) + ':' + now.strftime('%Y-%m-%d')
        if identifier not in fired:
            fired.add(identifier)
            due.append(rule)
    if len(fired) > 100:
        date = now.strftime('%Y-%m-%d')
        fired.intersection_update({entry for entry in fired if entry.endswith(date)})
    return due


def latest_due_since(rules: list[dict], earlier: datetime, now: datetime,
                     fired: set[str]) -> dict | None:
    """Apply only the most recent missed rule after sleep/resume."""
    candidates = []
    day = max(earlier.date(), (now - timedelta(days=2)).date())
    while day <= now.date():
        for rule in rules:
            try:
                hour, minute = map(int, rule['time'].split(':'))
                when = datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute)
            except (KeyError, ValueError, TypeError):
                continue
            if earlier < when <= now and rule.get('enabled', True) and day.weekday() in rule.get('days', list(range(7))):
                ident = str(rule.get('id', rules.index(rule))) + ':' + day.isoformat()
                if ident not in fired:
                    candidates.append((when, ident, rule))
        day += timedelta(days=1)
    if not candidates:
        return None
    when, ident, rule = max(candidates, key=lambda item: item[0])
    fired.update(item[1] for item in candidates)
    return rule
