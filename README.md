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
Unduh dengan `python src/download.py`, lalu ekstrak dengan `python src/extract.py`.
Berkas data disimpan di luar repositori, secara bawaan di `~/dblp-data`. Lokasi lain
dapat diatur melalui *environment variable* `DBLP_RAW_DIR`.
