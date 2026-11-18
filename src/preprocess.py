import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from src.config import INPROC_RAW, TABLES_DIR, YEAR_MAX, YEAR_MIN


class Funnel:
    def __init__(self):
        self.steps = []

    def add(self, stage, step, before, after):
        self.steps.append({"tahap": stage, "langkah": step, "sebelum": before,
                           "sesudah": after, "dihapus": before - after})

    def table(self):
        return pd.DataFrame(self.steps)


def select_scope(funnel: Funnel) -> pa.Table:
    n_all = int(pd.read_csv(TABLES_DIR / "dblp_record_types.csv")["n_records"].sum())
    n_inproc = pq.ParquetFile(INPROC_RAW).metadata.num_rows
    funnel.add("Seleksi cakupan", "Jenis publikasi inproceedings", n_all, n_inproc)

    years = [str(y) for y in range(YEAR_MIN, YEAR_MAX + 1)]
    table = pq.read_table(INPROC_RAW, filters=[("year", "in", years)])
    funnel.add("Seleksi cakupan", f"Tahun {YEAR_MIN}–{YEAR_MAX}", n_inproc, table.num_rows)

    before = table.num_rows
    table = table.filter(pc.starts_with(table["key"], "conf/"))
    funnel.add("Seleksi cakupan", "Seri konferensi/workshop (key conf/)", before, table.num_rows)

    before = table.num_rows
    withdrawn = pc.fill_null(pc.match_substring(table["publtype"], "withdrawn"), False)
    table = table.filter(pc.invert(withdrawn))
    funnel.add("Seleksi cakupan", "Bukan makalah yang ditarik (publtype withdrawn)", before, table.num_rows)
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


def dedupe_authors(table: pa.Table) -> tuple[pa.Table, int]:
    authors = table["authors"].combine_chunks()
    long = pd.DataFrame({"paper": pc.list_parent_indices(authors).to_numpy(),
                         "author": authors.flatten().to_pandas()})
    keep = ~long.duplicated(["paper", "author"])
    long = long[keep]
    offsets = pa.array([0, *long.groupby("paper", sort=True).size().cumsum()], pa.int32())
    deduped = pa.ListArray.from_arrays(offsets, pa.array(long["author"], pa.string()))
    idx = table.schema.get_field_index("authors")
    return table.set_column(idx, "authors", deduped), int((~keep).sum())


def normalize_authors(table: pa.Table) -> tuple[pa.Table, pd.DataFrame]:
    authors = table["authors"].combine_chunks()
    raw = authors.flatten().to_pandas()
    clean = raw.str.normalize("NFC").str.strip().str.replace(r"\s+", " ", regex=True)
    folded = clean.str.casefold()

    variants = (pd.DataFrame({"folded": folded, "name": clean})
                .value_counts().reset_index(name="n")
                .sort_values(["folded", "n", "name"], ascending=[True, False, True]))
    canonical = variants.drop_duplicates("folded").set_index("folded")["name"]
    names = folded.map(canonical)

    lengths = pc.list_value_length(authors).to_numpy()
    offsets = pa.array([0, *lengths.cumsum()], pa.int32())
    normalized = pa.ListArray.from_arrays(offsets, pa.array(names, pa.string()))
    idx = table.schema.get_field_index("authors")
    table = table.set_column(idx, "authors", normalized)

    report = pd.DataFrame({
        "tahap": ["Nama asli", "Setelah trim, spasi, dan NFC", "Setelah penggabungan varian kapitalisasi"],
        "nama_unik": [raw.nunique(), clean.nunique(), names.nunique()],
    })
    report["kemunculan_berubah"] = [0, int((raw != clean).sum()), int((raw != names).sum())]
    return table, report


def merged_case_variants(table: pa.Table, n=10) -> pd.DataFrame:
    raw = pd.Series(pc.list_flatten(table["authors"]).to_pandas())
    counts = raw.value_counts().rename_axis("name").reset_index(name="n")
    counts["folded"] = counts["name"].str.casefold()
    groups = counts[counts.duplicated("folded", keep=False)].sort_values(["folded", "n"], ascending=[True, False])
    return groups.groupby("folded").agg(varian=("name", list), kemunculan=("n", list)).head(n).reset_index(drop=True)


def normalized_title(table: pa.Table) -> pd.Series:
    title = pc.utf8_lower(table["title"]).to_pandas()
    return title.str.replace(r"[^0-9a-z]+", " ", regex=True).str.strip()


def remove_duplicates(table: pa.Table, funnel: Funnel) -> pa.Table:
    before = table.num_rows
    order = pc.sort_indices(table["key"])
    table = table.take(order)
    keys = table["key"].to_pandas()
    table = table.filter(pa.array(~keys.duplicated().to_numpy()))
    funnel.add("Duplikat", "Key unik", before, table.num_rows)

    before = table.num_rows
    content = pd.DataFrame({
        "title": normalized_title(table),
        "year": table["year"].to_pandas(),
        "series": table["key"].to_pandas().str.rsplit("/", n=1).str[0],
        "authors": pc.binary_join(table["authors"], "|").to_pandas(),
    })
    table = table.filter(pa.array(~content.duplicated().to_numpy()))
    funnel.add("Duplikat", "Makalah unik (judul, tahun, seri venue, penulis)", before, table.num_rows)
    return table


WORKSHOP_PATTERN = r"(?i)workshop|wokshop|wkshps|@"
COMPANION_PATTERN = (r"(?i)findings|companion|adjunct|extended abstract|poster|demo|industry|"
                     r"selected papers|position paper|satellite|supplement|doctoral|student|tiny paper|talks")


def _mode(values: pd.Series) -> str:
    counts = values.value_counts().reset_index()
    counts.columns = ["value", "n"]
    return counts.sort_values(["n", "value"], ascending=[False, True])["value"].iloc[0]


def classify_venues(table: pa.Table) -> pd.DataFrame:
    papers = pd.DataFrame({
        "series": table["key"].to_pandas().str.rsplit("/", n=1).str[0],
        "booktitle": table["booktitle"].to_pandas().fillna(""),
    })
    booktitle = papers["booktitle"]
    base = booktitle.str.replace(r"\s*\(\d+\)$", "", regex=True).str.strip()
    workshop_mark = booktitle.str.contains(WORKSHOP_PATTERN)
    companion_mark = booktitle.str.contains(COMPANION_PATTERN)
    plain = (booktitle != "") & ~workshop_mark & ~companion_mark

    main = base[plain].groupby(papers["series"][plain]).agg(_mode)
    fallback = base[booktitle != ""].groupby(papers["series"][booktitle != ""]).agg(_mode)
    main_name = papers["series"].map(main)
    has_main = main_name.notna()

    is_workshop = has_main & (workshop_mark | (booktitle == main_name + "W") | (booktitle == main_name + "-W"))
    papers["track"] = "main"
    papers.loc[has_main & companion_mark & ~is_workshop, "track"] = "companion"
    papers.loc[is_workshop, "track"] = "workshop"

    series_id = papers["series"].str.removeprefix("conf/")
    name = main_name.fillna(papers["series"].map(fallback)).fillna(series_id.str.upper())
    papers["venue_id"] = series_id.where(~is_workshop, series_id + "_workshops")
    papers["venue_name"] = name.where(~is_workshop, name + " Workshops")
    clash = set(papers.loc[is_workshop, "venue_id"]) & set(series_id[~is_workshop])
    if clash:
        raise ValueError(f"venue_id workshop bentrok dengan seri lain: {sorted(clash)}")
    return papers


def venue_mapping(venues: pd.DataFrame) -> pd.DataFrame:
    return (venues.groupby(["series", "booktitle", "track", "venue_id", "venue_name"])
            .size().rename("n_papers").reset_index()
            .sort_values(["series", "n_papers"], ascending=[True, False]))


def apply_venues(table: pa.Table, venues: pd.DataFrame) -> pa.Table:
    for column in ["venue_id", "venue_name", "track"]:
        table = table.append_column(column, pa.array(venues[column], pa.string()))
    return table


def handle_missing(table: pa.Table, funnel: Funnel) -> pa.Table:
    before = table.num_rows
    table = table.filter(pc.greater(pc.list_value_length(table["authors"]), 0))
    funnel.add("Missing values", "Memiliki minimal satu penulis", before, table.num_rows)
    return table
