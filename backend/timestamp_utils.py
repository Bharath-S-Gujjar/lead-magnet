"""Canonical timestamp normalization and sorting utilities.

Provides consistent parsing, UTC normalization, and deterministic chronological
ordering for timestamps across customer journeys, live activity feeds, and intelligence services.
"""

from datetime import datetime, timezone
from typing import Any, Optional, Tuple


def parse_and_normalize_timestamp(ts: Any) -> Tuple[Optional[datetime], Optional[str]]:
    """Parse any timestamp representation into a UTC datetime and ISO-8601 string.

    Supports:
        - Python/BSON datetime objects (naive or timezone-aware)
        - Numeric Unix timestamps in seconds or milliseconds
        - Numeric strings representing Unix epoch
        - ISO-8601 strings with Z, UTC offset, or space separators
        - Common date and datetime string formats

    Returns:
        (datetime_utc, iso_string) or (None, None) if timestamp is unparseable.
    """
    if ts is None:
        return None, None

    dt = None

    if isinstance(ts, datetime):
        dt = ts
    elif isinstance(ts, (int, float)):
        try:
            val = float(ts)
            # If timestamp is > 1e11, it is in milliseconds (1e11 ms is in 1973)
            sec = val / 1000.0 if abs(val) > 1e11 else val
            dt = datetime.fromtimestamp(sec, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None, None
    elif isinstance(ts, str):
        s = ts.strip()
        if not s:
            return None, None

        # Check if numeric epoch string
        try:
            val = float(s)
            sec = val / 1000.0 if abs(val) > 1e11 else val
            dt = datetime.fromtimestamp(sec, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            # Parse ISO or standard string
            clean_s = s.replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(clean_s)
            except Exception:
                for fmt in (
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d %H:%M:%S.%f",
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S.%f",
                    "%Y-%m-%d",
                ):
                    try:
                        dt = datetime.strptime(s, fmt)
                        break
                    except Exception:
                        pass

    if dt is None:
        return None, None

    # Guarantee timezone awareness in UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return dt, dt.isoformat()


def sort_events_chronological(events, timestamp_key="timestamp", reverse=True, id_keys=None):
    """Sort event dictionaries chronologically by actual event time.

    Args:
        events (list[dict]): List of event dictionaries.
        timestamp_key (str): Key holding the raw timestamp.
        reverse (bool): If True, newest first (default).
        id_keys (list[str]): Fallback keys for deterministic tie-breaking.

    Returns:
        list[dict]: Sorted event list with normalized ISO timestamps.
    """
    if not events:
        return []

    if id_keys is None:
        id_keys = ["_id", "order_id", "customer_id", "event_type", "type", "description"]

    # Minimum fallback UTC datetime for entries missing timestamps
    fallback_dt = datetime.min.replace(tzinfo=timezone.utc)

    decorated = []
    for idx, item in enumerate(events):
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        raw_ts = entry.get(timestamp_key)
        dt, iso_str = parse_and_normalize_timestamp(raw_ts)

        # Update entry with normalized ISO timestamp
        entry[timestamp_key] = iso_str

        # Deterministic secondary key
        tie_breaker = ""
        for k in id_keys:
            val = entry.get(k)
            if val is not None:
                tie_breaker = str(val)
                break
        if not tie_breaker:
            tie_breaker = str(idx)

        sort_dt = dt if dt is not None else fallback_dt
        decorated.append((sort_dt, tie_breaker, entry))

    decorated.sort(key=lambda x: (x[0], x[1]), reverse=reverse)
    return [d[2] for d in decorated]
