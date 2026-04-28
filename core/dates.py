from __future__ import annotations

import datetime


def parse_date(value):
    """Convert supported date representations to datetime.date."""
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str):
        text = value.strip()
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
            try:
                return datetime.datetime.strptime(text, fmt).date()
            except ValueError:
                pass
    return None


def format_date(value):
    parsed = parse_date(value)
    return parsed.strftime("%d/%m/%Y") if parsed else (str(value) if value else "-")


def giorni_rimanenti(value, today: datetime.date | None = None):
    parsed = parse_date(value)
    if parsed is None:
        return None
    reference = today or datetime.date.today()
    return (parsed - reference).days
