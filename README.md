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
