"""Read the raw Kaggle files with flexible column matching (sources.yaml). Large files are sampled
while reading (`max_rows`) so the pipeline runs on a laptop."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
SOURCES = yaml.safe_load((Path(__file__).parent / "sources.yaml").read_text(encoding="utf-8"))["sources"]


def files_for(key: str) -> list[Path]:
    """Data files of a source. `files` in sources.yaml (glob list) restricts which ones are read,
    e.g. to skip an .xlsx copy of a .csv or an unlabelled companion file."""
    d = RAW / key
    if not d.exists():
        return []
    globs = SOURCES.get(key, {}).get("files")
    if globs:
        found = {p for g in globs for p in d.rglob(g)}
    else:
        found = {p for p in d.rglob("*") if p.suffix.lower() in (".csv", ".parquet", ".json", ".jsonl", ".xlsx")}
    return sorted(found)


def read_any(path: Path, max_rows: int | None = None) -> pd.DataFrame:
    s = path.suffix.lower()
    if s == ".csv":
        return pd.read_csv(path, nrows=max_rows, low_memory=False, on_bad_lines="skip", encoding_errors="replace")
    if s == ".parquet":
        df = pd.read_parquet(path)
        return df.head(max_rows) if max_rows else df
    if s in (".json", ".jsonl"):
        df = pd.read_json(path, lines=s == ".jsonl")
        return df.head(max_rows) if max_rows else df
    df = pd.read_excel(path)
    return df.head(max_rows) if max_rows else df


def resolve_columns(df: pd.DataFrame, key: str) -> dict[str, str | None]:
    lower = {c.lower().strip(): c for c in df.columns}
    out = {}
    for field, candidates in SOURCES[key]["columns"].items():
        if isinstance(candidates, dict):  # {join: [col, ...]} -> several columns merged into one list field
            cols = [lower[c.lower()] for c in candidates.get("join", []) if c.lower() in lower]
            out[field] = cols or None
            continue
        out[field] = next((lower[c.lower()] for c in candidates if c.lower() in lower), None)
    return out


def _column(df: pd.DataFrame, col) -> pd.Series:
    if col is None:
        return pd.Series([None] * len(df))
    if isinstance(col, list):  # joined columns -> "a, b, c" (nulls dropped)
        return df[col].apply(lambda r: ", ".join(str(v).strip() for v in r if pd.notna(v) and str(v).strip()), axis=1)
    return df[col]


def load_source(key: str, max_rows: int | None = None) -> pd.DataFrame:
    """All files of a source, renamed to our field names; unmatched fields become empty columns.
    Adds `_source` and `_file` for provenance."""
    frames = []
    for path in files_for(key):
        df = read_any(path, max_rows)
        cols = resolve_columns(df, key)
        renamed = pd.DataFrame({field: _column(df, col) for field, col in cols.items()})
        renamed["_source"] = key
        renamed["_file"] = path.name
        frames.append(renamed)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
