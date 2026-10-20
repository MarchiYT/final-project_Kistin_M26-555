"""Проверки значений, времени и пересчёт курсов."""

import math
from datetime import UTC, datetime

from valutatrade_hub.core.exceptions import ApiRequestError


def validate_code(code):
    """Проверить формат кода без изменения регистра."""
    if (
        not isinstance(code, str)
        or not 2 <= len(code) <= 5
        or not code.isascii()
        or not code.isalpha()
        or not code.isupper()
    ):
        raise ValueError("Код валюты: от 2 до 5 латинских букв в верхнем регистре")
    return code


def validate_number(value, name="amount", allow_zero=False):
    """Принять только конечное число нужного знака."""
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
        or value < 0
        or (value == 0 and not allow_zero)
    ):
        rule = "неотрицательным" if allow_zero else "положительным"
        raise ValueError(f"'{name}' должен быть {rule} конечным числом")
    return float(value)


def utc_now():
    """Вернуть текущее время UTC для JSON и логов."""
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_time(value):
    """Прочитать ISO-дату, считая дату без зоны временем UTC."""
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (
        result.replace(tzinfo=UTC) if result.tzinfo is None else result.astimezone(UTC)
    )


def is_fresh(timestamp, ttl):
    """Проверить возраст снимка относительно TTL."""
    try:
        age = (datetime.now(UTC) - parse_time(timestamp)).total_seconds()
    except (TypeError, ValueError, AttributeError):
        return False
    return 0 <= age <= ttl


def cached_rate(pairs, from_code, to_code):
    """Получить прямой, обратный или кросс-курс через USD."""
    if from_code == to_code:
        return {"rate": 1.0, "updated_at": utc_now(), "source": "identity"}

    def read_pair(source, target):
        key = f"{source}_{target}"
        inverse_key = f"{target}_{source}"
        entry = pairs.get(key) or pairs.get(inverse_key)
        if not isinstance(entry, dict):
            raise ApiRequestError(
                f"нет курса {source}→{target}. Выполните update-rates"
            )
        try:
            rate = validate_number(entry["rate"], "rate")
            updated = entry["updated_at"]
            parse_time(updated)
        except (KeyError, ValueError, TypeError, AttributeError) as error:
            raise ApiRequestError(f"повреждён курс {key}") from error
        if key not in pairs:
            rate = validate_number(1 / rate, "rate")
        return {
            "rate": rate,
            "updated_at": updated,
            "source": entry.get("source", "cache"),
        }

    if f"{from_code}_{to_code}" in pairs or f"{to_code}_{from_code}" in pairs:
        return read_pair(from_code, to_code)
    left = read_pair(from_code, "USD") if from_code != "USD" else None
    right = read_pair(to_code, "USD") if to_code != "USD" else None
    entries = [entry for entry in (left, right) if entry]
    rate = (left["rate"] if left else 1.0) / (right["rate"] if right else 1.0)
    return {
        "rate": validate_number(rate, "rate"),
        "updated_at": min((entry["updated_at"] for entry in entries), key=parse_time),
        "source": ", ".join(sorted({entry["source"] for entry in entries})),
    }
