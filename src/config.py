import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RAW_DIR = Path(os.environ.get("DBLP_RAW_DIR", Path.home() / "dblp-data"))

DATA_DIR = ROOT / "data" 
RESULTS_DIR = ROOT / "results"
TABLES_DIR = RESULTS_DIR / "tables"
FIGURES_DIR = RESULTS_DIR / "figures"
EXPERIMENTS_DIR = RESULTS_DIR / "experiments"

YEAR_MIN, YEAR_MAX = 2015, 2025

for _d in (RAW_DIR, DATA_DIR, TABLES_DIR, FIGURES_DIR, EXPERIMENTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
