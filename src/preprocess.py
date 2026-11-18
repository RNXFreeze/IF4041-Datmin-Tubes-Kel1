import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from src.config import INPROC_RAW, TABLES_DIR, YEAR_MAX, YEAR_MIN


class Funnel:
    def __init__(self):
        self.steps = []

    def add(self, task, step, before, after):
        self.steps.append({"task": task, "langkah": step, "sebelum": before,
                           "sesudah": after, "dihapus": before - after})

    def table(self):
        return pd.DataFrame(self.steps)


def select_scope(funnel: Funnel) -> pa.Table:
    n_all = int(pd.read_csv(TABLES_DIR / "dblp_record_types.csv")["n_records"].sum())
    n_inproc = pq.ParquetFile(INPROC_RAW).metadata.num_rows
    funnel.add("PRE-01", "Jenis publikasi inproceedings", n_all, n_inproc)

    years = [str(y) for y in range(YEAR_MIN, YEAR_MAX + 1)]
    table = pq.read_table(INPROC_RAW, filters=[("year", "in", years)])
    funnel.add("PRE-01", f"Tahun {YEAR_MIN}–{YEAR_MAX}", n_inproc, table.num_rows)

    before = table.num_rows
    table = table.filter(pc.starts_with(table["key"], "conf/"))
    funnel.add("PRE-01", "Seri konferensi/workshop (key conf/)", before, table.num_rows)

    before = table.num_rows
    withdrawn = pc.fill_null(pc.match_substring(table["publtype"], "withdrawn"), False)
    table = table.filter(pc.invert(withdrawn))
    funnel.add("PRE-01", "Bukan makalah yang ditarik (publtype withdrawn)", before, table.num_rows)
    return table


def missing_report(table: pa.Table) -> pd.DataFrame:
    def blank(col):
        return pc.sum(pc.equal(pc.utf8_trim_whitespace(pc.fill_null(col, "")), "")).as_py()

    authors = pc.list_flatten(table["authors"])
    rows = {
        "authors (tanpa penulis)": pc.sum(pc.equal(pc.list_value_length(table["authors"]), 0)).as_py(),
        "authors (nama kosong)": blank(authors),
        "title": blank(table["title"]),
        "year": blank(table["year"]),
        "booktitle": blank(table["booktitle"]),
        "crossref": blank(table["crossref"]),
    }
    report = pd.Series(rows, name="n_missing").to_frame()
    report["pct"] = (100 * report["n_missing"] / table.num_rows).round(3)
    return report


def handle_missing(table: pa.Table, funnel: Funnel) -> pa.Table:
    before = table.num_rows
    table = table.filter(pc.greater(pc.list_value_length(table["authors"]), 0))
    funnel.add("PRE-02", "Memiliki minimal satu penulis", before, table.num_rows)
    return table
