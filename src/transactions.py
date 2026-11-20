"""Build reproducible author and author-year conference transactions (Task 3)."""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import duckdb
import pandas as pd

from src.config import CLEAN_PAPER_AUTHOR, DATA_DIR, TABLES_DIR


AUTHOR_FILE = DATA_DIR / "author_transactions.parquet"
AUTHOR_YEAR_FILE = DATA_DIR / "author_year_transactions.parquet"


def _sql_path(path: Path) -> str:
    """Quote a trusted local path as a DuckDB string literal."""
    return "'" + path.resolve().as_posix().replace("'", "''") + "'"


def _copy_query(con: duckdb.DuckDBPyConnection, query: str, destination: Path) -> None:
    tmp = destination.with_name(destination.stem + ".part.parquet")
    try:
        con.execute(f"COPY ({query}) TO {_sql_path(tmp)} (FORMAT PARQUET, COMPRESSION ZSTD)")
        tmp.replace(destination)
    finally:
        tmp.unlink(missing_ok=True)


def build_transactions(source: Path = CLEAN_PAPER_AUTHOR) -> None:
    """Create one sorted, unique venue list per author and per author-year."""
    if not source.exists():
        raise FileNotFoundError(f"Dataset bersih tidak ditemukan: {source}")

    tmp_dir = DATA_DIR / ".duckdb_tmp"
    tmp_dir.mkdir(exist_ok=True)
    con = duckdb.connect()
    try:
        con.execute("SET memory_limit = '1536MB'")
        con.execute("SET threads = 1")
        con.execute("SET preserve_insertion_order = false")
        con.execute(f"SET temp_directory = {_sql_path(tmp_dir)}")
        source_sql = f"read_parquet({_sql_path(source)})"

        for dimensions, destination in [
            ("author", AUTHOR_FILE),
            ("author, year", AUTHOR_YEAR_FILE),
        ]:
            query = f"""
                SELECT {dimensions}, list_sort(list(venue_id)) AS venue_ids,
                       count(*)::INTEGER AS n_items
                FROM (
                    SELECT DISTINCT {dimensions}, venue_id
                    FROM {source_sql}
                )
                GROUP BY {dimensions}
            """
            print(f"Membangun {destination.name} ...", flush=True)
            _copy_query(con, query, destination)

        summarize(con)
    finally:
        con.close()
        try:
            tmp_dir.rmdir()
        except OSError:
            pass


def summarize(con: duckdb.DuckDBPyConnection) -> None:
    rows = []
    for label, path in [("author", AUTHOR_FILE), ("author_year", AUTHOR_YEAR_FILE)]:
        data = f"read_parquet({_sql_path(path)})"
        stats = con.execute(f"""
            SELECT count(*) AS n_transactions, sum(n_items) AS n_item_occurrences,
                   count(*) FILTER (WHERE n_items = 1) AS n_single_item,
                   round(avg(n_items), 3) AS mean_items,
                   median(n_items) AS median_items,
                   max(n_items) AS max_items
            FROM {data}
        """).fetchone()
        unique_items = con.execute(f"""
            SELECT count(DISTINCT venue_id)
            FROM {data}, UNNEST(venue_ids) AS v(venue_id)
        """).fetchone()[0]
        rows.append((label, *stats, unique_items))

        distribution = con.execute(f"""
            SELECT n_items, count(*) AS n_transactions
            FROM {data} GROUP BY n_items ORDER BY n_items
        """).df()
        distribution.to_csv(TABLES_DIR / f"{label}_transaction_length.csv", index=False)

        columns = "author, venue_ids, n_items" if label == "author" else "author, year, venue_ids, n_items"
        sample_key = "hash(author)" if label == "author" else "hash(author, year)"
        examples = con.execute(f"""
            SELECT {columns} FROM {data}
            ORDER BY {sample_key}
            LIMIT 10
        """).df()
        examples["venue_ids"] = examples["venue_ids"].map(lambda items: " | ".join(items))
        examples.to_csv(TABLES_DIR / f"{label}_transaction_examples.csv", index=False)

    pd.DataFrame(rows, columns=[
        "representation", "n_transactions", "n_item_occurrences", "n_single_item",
        "mean_items", "median_items", "max_items", "n_unique_items",
    ]).to_csv(TABLES_DIR / "transaction_statistics.csv", index=False)


if __name__ == "__main__":
    build_transactions()
