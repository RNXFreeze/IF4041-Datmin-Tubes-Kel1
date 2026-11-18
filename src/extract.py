import gzip
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from lxml import etree

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import DBLP_DTD, DBLP_XML, INPROC_RAW, TABLES_DIR

RECORD_TAGS = (
    "article", "inproceedings", "proceedings", "book", "incollection",
    "phdthesis", "mastersthesis", "www", "person", "data",
)

SCHEMA = pa.schema([
    ("key", pa.string()),
    ("mdate", pa.string()),
    ("publtype", pa.string()),
    ("title", pa.string()),
    ("authors", pa.list_(pa.string())),
    ("year", pa.string()),
    ("booktitle", pa.string()),
    ("crossref", pa.string()),
])


class _LocalDtdResolver(etree.Resolver):
    def resolve(self, system_url, public_id, context):
        if system_url and system_url.endswith(".dtd"):
            return self.resolve_filename(str(DBLP_DTD), context)
        return None


def _text(elem, tag):
    child = elem.find(tag)
    return None if child is None else "".join(child.itertext())


def _inproceedings_row(elem):
    return {
        "key": elem.get("key"),
        "mdate": elem.get("mdate"),
        "publtype": elem.get("publtype"),
        "title": _text(elem, "title"),
        "authors": ["".join(a.itertext()) for a in elem.iterfind("author")],
        "year": _text(elem, "year"),
        "booktitle": _text(elem, "booktitle"),
        "crossref": _text(elem, "crossref"),
    }


def extract(xml_path=DBLP_XML, out_path=INPROC_RAW, batch_size=200_000, limit=None):
    type_counts = Counter()
    field_counts = Counter()
    year_counts = Counter()
    batch = []
    writer = pq.ParquetWriter(out_path, SCHEMA)
    start = time.time()

    source = gzip.open(xml_path, "rb")
    context = etree.iterparse(
        source, events=("end",), tag=RECORD_TAGS,
        load_dtd=True, resolve_entities=True, huge_tree=True,
    )
    context.resolvers.add(_LocalDtdResolver())
    try:
        for _, elem in context:
            rtype = elem.tag
            type_counts[rtype] += 1
            for field in {child.tag for child in elem}:
                field_counts[(rtype, field)] += 1
            year_counts[(rtype, _text(elem, "year"))] += 1

            if rtype == "inproceedings":
                batch.append(_inproceedings_row(elem))
                if len(batch) >= batch_size:
                    writer.write_table(pa.Table.from_pylist(batch, SCHEMA))
                    batch.clear()

            elem.clear()
            while elem.getprevious() is not None:
                del elem.getparent()[0]

            total = type_counts.total()
            if total % 1_000_000 == 0:
                print(f"{total:,} record, {time.time() - start:.0f} s", flush=True)
            if limit and total >= limit:
                break
        if batch:
            writer.write_table(pa.Table.from_pylist(batch, SCHEMA))
    finally:
        writer.close()
        source.close()
        del context

    elapsed = time.time() - start
    types = (pd.Series(type_counts, name="n_records").rename_axis("record_type")
             .sort_values(ascending=False).reset_index())
    fields = pd.Series(field_counts, name="n_records_with_field").rename_axis(["record_type", "field"]).reset_index()
    fields["pct"] = 100 * fields["n_records_with_field"] / fields["record_type"].map(type_counts)
    fields = fields.sort_values(["record_type", "pct"], ascending=[True, False])
    years = pd.Series(year_counts, name="n_records").rename_axis(["record_type", "year"]).reset_index()

    if limit is None:
        types.to_csv(TABLES_DIR / "dblp_record_types.csv", index=False)
        fields.to_csv(TABLES_DIR / "dblp_field_presence.csv", index=False)
        years.to_csv(TABLES_DIR / "dblp_year_by_type.csv", index=False)

    print(f"Selesai: {type_counts.total():,} record dalam {elapsed / 60:.1f} menit")
    return types, fields, years


if __name__ == "__main__":
    extract()
