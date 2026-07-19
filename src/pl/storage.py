"""Load/save the repo's YAML data files.

Layout (relative to repo root):
    data/athlete.yaml               Athlete
    data/exercises.yaml             list[Exercise]
    data/blocks/<id>/block.yaml     Block
    data/blocks/<id>/sessions/*.yaml  SessionLog (one file per session)
    knowledge/pain-log.yaml         list[PainEvent]

Set PL_ROOT to point somewhere else (used by tests and demos).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

import yaml
from pydantic import BaseModel

from .models import Athlete, Block, BlockReview, Exercise, PainEvent, SessionLog


def repo_root() -> Path:
    env = os.environ.get("PL_ROOT")
    if env:
        return Path(env)
    cur = Path.cwd()
    for p in [cur, *cur.parents]:
        if (p / "data").is_dir() or (p / ".git").exists():
            return p
    return cur


def _load_yaml(path: Path):
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _dump_yaml(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(obj, f, sort_keys=False, allow_unicode=True)


def _model_to_plain(m: BaseModel) -> dict:
    return m.model_dump(mode="json", exclude_none=True)


# --------------------------------------------------------------------------- loaders


def load_athlete(root: Path | None = None) -> Athlete:
    root = root or repo_root()
    raw = _load_yaml(root / "data" / "athlete.yaml")
    return Athlete(**raw) if raw else Athlete()


def load_exercises(root: Path | None = None) -> dict[str, Exercise]:
    root = root or repo_root()
    raw = _load_yaml(root / "data" / "exercises.yaml") or []
    exs = [Exercise(**e) for e in raw]
    return {e.id: e for e in exs}


def resolve_exercise(name: str, catalog: dict[str, Exercise]) -> str | None:
    """Map a free-form name (sheet cell, chat) to a catalog id."""
    needle = name.strip().lower().replace(" ", "-").replace("_", "-")
    if needle in catalog:
        return needle
    for ex in catalog.values():
        candidates = [ex.name.lower(), *[a.lower() for a in ex.aliases]]
        if name.strip().lower() in candidates:
            return ex.id
    return None


def blocks_dir(root: Path | None = None) -> Path:
    return (root or repo_root()) / "data" / "blocks"


def load_block(block_id: str, root: Path | None = None) -> Block:
    raw = _load_yaml(blocks_dir(root) / block_id / "block.yaml")
    if raw is None:
        raise FileNotFoundError(f"no block '{block_id}' under data/blocks/")
    return Block(**raw)


def load_blocks(root: Path | None = None) -> list[Block]:
    out: list[Block] = []
    bdir = blocks_dir(root)
    if not bdir.is_dir():
        return out
    for d in sorted(bdir.iterdir()):
        if (d / "block.yaml").exists():
            out.append(Block(**_load_yaml(d / "block.yaml")))
    return out


def save_block(block: Block, root: Path | None = None) -> Path:
    path = blocks_dir(root) / block.id / "block.yaml"
    _dump_yaml(_model_to_plain(block), path)
    return path


def load_sessions(root: Path | None = None, block_id: str | None = None) -> list[SessionLog]:
    root = root or repo_root()
    out: list[SessionLog] = []
    bdir = blocks_dir(root)
    if not bdir.is_dir():
        return out
    for d in sorted(bdir.iterdir()):
        if block_id and d.name != block_id:
            continue
        sdir = d / "sessions"
        if not sdir.is_dir():
            continue
        for f in sorted(sdir.glob("*.yaml")):
            out.append(SessionLog(**_load_yaml(f)))
    return sorted(out, key=lambda s: s.date)


def save_session(session: SessionLog, root: Path | None = None) -> Path:
    if not session.block:
        raise ValueError("session needs a block id to be saved")
    day = f"-day{session.day}" if session.day else ""
    path = blocks_dir(root) / session.block / "sessions" / f"{session.date.isoformat()}{day}.yaml"
    _dump_yaml(_model_to_plain(session), path)
    return path


def review_path(block_id: str, root: Path | None = None) -> Path:
    return blocks_dir(root) / block_id / "review.yaml"


def load_review(block_id: str, root: Path | None = None) -> BlockReview | None:
    raw = _load_yaml(review_path(block_id, root))
    return BlockReview(**raw) if raw else None


def load_reviews(root: Path | None = None) -> list[BlockReview]:
    out: list[BlockReview] = []
    bdir = blocks_dir(root)
    if not bdir.is_dir():
        return out
    for d in sorted(bdir.iterdir()):
        rev = load_review(d.name, root)
        if rev:
            out.append(rev)
    return out


def save_review(review: BlockReview, root: Path | None = None) -> Path:
    path = review_path(review.block, root)
    _dump_yaml(_model_to_plain(review), path)
    return path


def load_pain_log(root: Path | None = None) -> list[PainEvent]:
    root = root or repo_root()
    raw = _load_yaml(root / "knowledge" / "pain-log.yaml") or []
    return [PainEvent(**p) for p in raw]


def save_pain_log(events: Iterable[PainEvent], root: Path | None = None) -> Path:
    root = root or repo_root()
    path = root / "knowledge" / "pain-log.yaml"
    _dump_yaml([_model_to_plain(e) for e in events], path)
    return path
