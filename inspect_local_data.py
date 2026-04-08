from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = PROJECT_ROOT / "workspace"
DATA_ROOT = WORKSPACE_ROOT / "data"
UPLOADS_ROOT = WORKSPACE_ROOT / "uploads"
MEMORIES_ROOT = WORKSPACE_ROOT / "memories"


def format_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{int(size)} B"


def print_header(title: str) -> None:
    print(f"\n=== {title} ===")


def iter_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file())


def print_workspace_files(root: Path, *, limit: int | None = None) -> None:
    files = list(iter_files(root))
    print(f"root: {root}")
    print(f"exists: {root.exists()}")
    print(f"file_count: {len(files)}")
    for path in files[: limit or len(files)]:
        rel = path.relative_to(PROJECT_ROOT)
        stat = path.stat()
        print(f"- {rel} | {format_size(stat.st_size)} | modified={stat.st_mtime:.0f}")


def sqlite_connect(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(str(path))


def fetch_table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name"
    ).fetchall()
    return [str(row[0]) for row in rows]


def fetch_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"pragma table_info({table})").fetchall()
    return [str(row[1]) for row in rows]


def print_rows(rows: Sequence[sqlite3.Row]) -> None:
    if not rows:
        print("sample_rows: []")
        return
    print("sample_rows:")
    for row in rows:
        payload = {}
        for key in row.keys():
            value = row[key]
            if isinstance(value, str) and len(value) > 200:
                payload[key] = value[:197] + "..."
            else:
                payload[key] = value
        print(json.dumps(payload, ensure_ascii=False))


def inspect_sqlite_db(path: Path, *, sample_limit: int) -> None:
    print(f"path: {path}")
    print(f"exists: {path.exists()}")
    if not path.exists():
        return

    stat = path.stat()
    print(f"size: {format_size(stat.st_size)}")
    print("signature:", path.open("rb").read(16))

    try:
        conn = sqlite_connect(path)
    except Exception as exc:
        print(f"open_error: {type(exc).__name__}: {exc}")
        return

    try:
        conn.row_factory = sqlite3.Row
        try:
            integrity = conn.execute("pragma integrity_check").fetchone()
            print(f"integrity_check: {integrity[0] if integrity else 'unknown'}")
        except Exception as exc:
            print(f"integrity_check_error: {type(exc).__name__}: {exc}")

        try:
            tables = fetch_table_names(conn)
        except Exception as exc:
            print(f"schema_error: {type(exc).__name__}: {exc}")
            return
        print(f"tables: {tables}")
        for table in tables:
            print(f"\n[{table}]")
            try:
                count = conn.execute(f"select count(*) from {table}").fetchone()[0]
                print(f"row_count: {count}")
                print(f"columns: {fetch_columns(conn, table)}")
                rows = conn.execute(f"select * from {table} limit ?", (sample_limit,)).fetchall()
                print_rows(rows)
            except Exception as exc:
                print(f"table_error: {type(exc).__name__}: {exc}")
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect locally stored MyAgent data.")
    parser.add_argument("--sample-limit", type=int, default=3, help="Number of sample rows per table.")
    parser.add_argument(
        "--list-limit",
        type=int,
        default=20,
        help="Maximum number of filesystem entries to print per directory.",
    )
    args = parser.parse_args()

    print_header("Workspace Overview")
    print(f"project_root: {PROJECT_ROOT}")
    print(f"workspace_root: {WORKSPACE_ROOT}")
    print(f"data_root: {DATA_ROOT}")

    print_header("Uploads")
    print_workspace_files(UPLOADS_ROOT, limit=args.list_limit)

    print_header("Memories")
    print_workspace_files(MEMORIES_ROOT, limit=args.list_limit)

    print_header("Knowledge DB")
    inspect_sqlite_db(DATA_ROOT / "knowledge.db", sample_limit=args.sample_limit)

    print_header("Conversation DB")
    inspect_sqlite_db(DATA_ROOT / "conversations.db", sample_limit=args.sample_limit)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
