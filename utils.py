from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_hash(value: str, length: int = 16) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def normalize_text(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "")
    return value.strip()


def slug_text(value: str) -> str:
    value = normalize_text(value).lower()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def model_to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [model_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: model_to_jsonable(item) for key, item in value.items()}
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(model_to_jsonable(value), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(model_to_jsonable(value), ensure_ascii=False) + "\n")


def prompt_hash(system_prompt: str, payload: Any) -> str:
    canonical = json.dumps(
        {"system": system_prompt, "payload": model_to_jsonable(payload)},
        sort_keys=True,
        ensure_ascii=False,
    )
    return stable_hash(canonical, length=32)


def first_sentence(text: str, max_chars: int = 240) -> str:
    text = normalize_text(text)
    if not text:
        return ""
    sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
    if len(sentence) <= max_chars:
        return sentence
    return sentence[: max_chars - 3].rstrip() + "..."
