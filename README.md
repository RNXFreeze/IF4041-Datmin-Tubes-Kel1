# IF4041-Datmin-Tubes-Kel1
IF4041 - Penambangan Data - Tugas Besar - Kelompok 1

Analisis popularitas konferensi dan pola asosiasi antarkonferensi pada publikasi
*inproceedings* DBLP periode 2015–2025 menggunakan algoritma Apriori dan FP-Growth.

## Struktur Repositori

| Folder | Isi |
|--------|-----|
| `data/` | Dataset hasil preprocessing (tidak disimpan di repositori) |
| `notebooks/` | Notebook setiap tahap pengerjaan |
| `src/` | Modul Python bersama |
| `results/` | Tabel, grafik, dan hasil eksperimen |
| `report/` | Laporan dan presentasi |

## Persiapan

Gunakan Python 3.13, lalu pasang dependensi dengan `pip install -r requirements.txt`.

Dataset yang digunakan adalah rilis DBLP 2026-11-01
([10.4230/dblp.xml.2026-11-01](https://doi.org/10.4230/dblp.xml.2026-11-01)).
Unduh dengan `python src/download.py`, ekstrak dengan `python src/extract.py`, lalu buat
dataset bersih dengan `python src/export.py`. Data mentah disimpan di luar repositori,
secara bawaan di `~/dblp-data`. Lokasi lain dapat diatur melalui *environment variable*
`DBLP_RAW_DIR`.

Dataset bersih tersimpan di `data/`. Struktur kolom dan cara memperolehnya dijelaskan di
[`data/README.md`](data/README.md).

## Task 3 — Transactional Database

Jalankan `python src/transactions.py` setelah dataset bersih tersedia. Skrip ini membentuk
`data/author_transactions.parquet` (satu transaksi per penulis) dan
`data/author_year_transactions.parquet` (satu transaksi per penulis dan tahun) dari
`paper_author.parquet`. Item transaksi adalah `venue_id` unik, termasuk konferensi dan
workshop; setiap daftar item diurutkan. Statistik, distribusi panjang transaksi, dan
masing-masing 10 contoh tersedia di `results/tables/`. Analisis dan visualisasi ada di
`notebooks/03_transactional_database.ipynb`.

## Task 4 dan 5 — Apriori

Jalankan `python src/apriori.py` setelah transaksi per penulis tersedia. Implementasi
Apriori membuat frequent itemsets pada minimum support 0,1%, 0,5%, 1%, dan 2%, lalu
membangkitkan association rules dengan minimum confidence 50%. Seluruh itemset dan
rules disimpan di `results/experiments/`; tabel ringkasan dan hingga 10 teratas per ambang
ada di `results/tables/`. Metode, visualisasi, dan interpretasi terdapat di
`notebooks/04_05_apriori_and_rules.ipynb`. Pengujian implementasi dapat dijalankan
dengan `python -m unittest discover -s tests`.

## Task 4 dan 5 — FP-Growth

Jalankan `python -m src.fp_growth` dari folder root repositori setelah transaksi per penulis tersedia.
Implementasi FP-Growth (FP-tree, header table, conditional pattern base, dan conditional FP-tree,
tanpa library frequent-pattern mining) memakai input dan ambang yang sama dengan Apriori
(`minimum_count` pada `src/apriori.py`). Association rules dibangkitkan dengan rumus support,
confidence, dan lift yang sama seperti Apriori. Hasil disimpan di `results/experiments/fpgrowth_*.csv`
dan `results/tables/fpgrowth_*.csv`. Analisis dan interpretasi terdapat di
`notebooks/04_05_fpgrowth_and_rules.ipynb`.

## Task 6 — Perbandingan Performa

Jalankan `notebooks/06_performance_comparison.ipynb` setelah transaksi per penulis tersedia.
Apriori dan FP-Growth dijalankan pada file Parquet dan minimum support yang sama, lalu
dibandingkan jumlah frequent itemsets, jumlah rules, kesamaan hasil, dan waktu eksekusi.
Hasilnya disimpan di `results/tables/performance_*.csv`.

## Bagian E — Temporal Association Analysis

Jalankan `python -m src.temporal` dari folder root repositori setelah transaksi per penulis dan
tahun tersedia. Transaksi author-year dibagi ke periode 2015-2017, 2018-2020, 2021-2023, dan
2024-2025, lalu setiap periode ditambang dengan FP-Growth (support 0,1%, confidence 50%).
Hasil per periode dan perbandingan rules antarperiode tersimpan di `results/experiments/temporal_*.csv`
dan `results/tables/temporal_*.csv`. Analisis, termasuk perbandingan Author-Based dan
Author-Year-Based, ada di `notebooks/07_temporal_analysis.ipynb`.
