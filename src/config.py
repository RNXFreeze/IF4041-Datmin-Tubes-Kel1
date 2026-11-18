import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RAW_DIR = Path(os.environ.get("DBLP_RAW_DIR", Path.home() / "dblp-data"))

DBLP_RELEASE = "2026-11-01"
DBLP_DTD_RELEASE = "2023-06-28"
DBLP_XML = RAW_DIR / f"dblp-{DBLP_RELEASE}.xml.gz"
DBLP_DTD = RAW_DIR / f"dblp-{DBLP_DTD_RELEASE}.dtd"
INPROC_RAW = RAW_DIR / f"inproceedings-{DBLP_RELEASE}.parquet"

DATA_DIR = ROOT / "data" 
RESULTS_DIR = ROOT / "results"
TABLES_DIR = RESULTS_DIR / "tables"
FIGURES_DIR = RESULTS_DIR / "figures"
EXPERIMENTS_DIR = RESULTS_DIR / "experiments"

YEAR_MIN, YEAR_MAX = 2015, 2025

for _d in (RAW_DIR, DATA_DIR, TABLES_DIR, FIGURES_DIR, EXPERIMENTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
