import re


def parse_days_list(value: str) -> list[int]:
    days = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        day = int(item)
        if day < 1 or day > 7:
            raise ValueError("day out of range")
        days.append(day)
    unique_days = sorted(set(days))
    if not unique_days:
        raise ValueError("empty days")
    return unique_days


PHONE_RE = re.compile(r"^\+?\d{7,20}$")


def is_valid_phone(value: str) -> bool:
    return bool(PHONE_RE.match(value.strip()))


FULL_NAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁёЎўҚқҒғҲҳİı'’\- ]+$")
SCHEDULE_RE = re.compile(
    r"^\s*(?P<days>[1-7](?:\s*,\s*[1-7])*)\s+(?P<start>\d{2}:\d{2})\s*-\s*(?P<end>\d{2}:\d{2})\s*$"
)


def is_valid_full_name(value: str) -> bool:
    normalized = " ".join((value or "").strip().split())
    if len(normalized) < 5 or len(normalized) > 255:
        return False
    parts = [part for part in normalized.split(" ") if part]
    if len(parts) < 2:
        return False
    return bool(FULL_NAME_RE.match(normalized))


def parse_rate(value: str) -> float:
    raw = (value or "").strip().replace(",", ".")
    if not raw:
        raise ValueError("empty rate")
    rate = float(raw)
    if rate <= 0:
        raise ValueError("rate must be positive")
    if rate > 10000000:
        raise ValueError("rate too large")
    return round(rate, 2)


def parse_schedule_input(value: str) -> tuple[list[int], str, str]:
    match = SCHEDULE_RE.match((value or "").strip())
    if not match:
        raise ValueError("invalid schedule format")

    days = parse_days_list(match.group("days"))
    start = match.group("start")
    end = match.group("end")

    start_hour, start_minute = map(int, start.split(":"))
    end_hour, end_minute = map(int, end.split(":"))

    if start_hour > 23 or end_hour > 23 or start_minute > 59 or end_minute > 59:
        raise ValueError("invalid time")
    if (end_hour, end_minute) <= (start_hour, start_minute):
        raise ValueError("end must be greater than start")

    return days, start, end
