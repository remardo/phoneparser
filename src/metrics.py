import datetime as dt
import json
import os
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

LOG_PATH = os.path.join("src", "logs.log")


def _parse_log_time(line: str) -> Optional[dt.datetime]:
    # Format: 2025-08-16 13:22:26 | LEVEL    | line - message
    try:
        ts = line.split("|")[0].strip()
        return dt.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _iter_metric_lines() -> List[Tuple[dt.datetime, str]]:
    if not os.path.exists(LOG_PATH):
        return []
    out: List[Tuple[dt.datetime, str]] = []
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if "[METRIC]" not in line:
                continue
            t = _parse_log_time(line)
            if not t:
                continue
            out.append((t, line.rstrip()))
    return out


def summarize() -> Dict[str, Any]:
    now = dt.datetime.now()
    today = now.date()
    yesterday = today - dt.timedelta(days=1)
    week_ago = today - dt.timedelta(days=7)

    lines = _iter_metric_lines()

    counts = {
        "today": 0,
        "yesterday": 0,
        "week": 0,
        "errors_today": 0,
    }

    per_session = Counter()
    per_session_errors = Counter()
    errors_by_row = Counter()

    for ts, line in lines:
        date = ts.date()
        if "processed row=" in line:
            if date >= week_ago:
                counts["week"] += 1
            if date == today:
                counts["today"] += 1
            if date == yesterday:
                counts["yesterday"] += 1
            try:
                payload = line.split("[METRIC]", 1)[1]
                js = payload.split("row=", 1)[1]
                js = js[js.find("{") : js.rfind("}") + 1]
                data = json.loads(js.replace("'", '"'))
                session = data.get("session") or "unknown"
                per_session[session] += 1
            except Exception:
                pass
        elif "error row=" in line:
            if date == today:
                counts["errors_today"] += 1
            try:
                payload = line.split("[METRIC]", 1)[1]
                if "row={" in payload:
                    js = payload.split("row=", 1)[1]
                    js = js[js.find("{") : js.rfind("}") + 1]
                    data = json.loads(js.replace("'", '"'))
                    errors_by_row[data.get("row", 0)] += 1
                    session = data.get("session") or "unknown"
                    per_session_errors[session] += 1
            except Exception:
                pass

    return {
        "counts": counts,
    "sessions": per_session,
    "session_errors": per_session_errors,
        "errors_by_row": errors_by_row,
        "updated_at": now.isoformat(),
    }


def tail(n: int = 200) -> List[str]:
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
    return lines[-n:]
