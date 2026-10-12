"""Small helpers shared by the platform adapters."""

from __future__ import annotations
from datetime import datetime, timezone
import io
import json
from pathlib import Path
from typing import Any, Iterator, Optional


def parse_ts(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into a timezone-aware local datetime."""
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone()


def file_mtime(path: Path) -> datetime:
    """Return a file's modification time as a timezone-aware local datetime."""
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone()


def utc_iso(dt: Optional[datetime] = None) -> str:
    """Format a datetime as UTC ISO-8601 with millisecond precision and a Z suffix."""
    dt = dt or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def open_text(path: Path) -> io.TextIOBase:
    """Open a JSONL file for reading, transparently decompressing `.zst` files."""
    if path.suffix == ".zst":
        try:
            import zstandard
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError("Reading compressed sessions needs the 'zstandard' package") from exc
        raw = open(path, "rb")
        reader = zstandard.ZstdDecompressor().stream_reader(raw, closefd=True)
        return io.TextIOWrapper(reader, encoding="utf-8", errors="replace")
    return open(path, "r", encoding="utf-8", errors="replace")


def iter_jsonl(path: Path) -> Iterator[dict]:
    """Yield each JSON object in a JSONL file, skipping blank or malformed lines."""
    with open_text(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                yield data


def stringify(value: Any) -> str:
    """Render tool input/output payloads (strings, content blocks, JSON) as plain text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict) and item.get("type") in ("text", "input_text", "output_text"):
                parts.append(item.get("text", ""))
            elif isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(stringify(item))
        return "\n".join(p for p in parts if p)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def first_line_title(text: str, limit: int = 60) -> str:
    """Collapse a prompt into a one-line title."""
    for line in text.strip().splitlines():
        line = line.strip()
        if line:
            return line if len(line) <= limit else line[: limit - 3] + "..."
    return ""
