# Dataset Bersih

Makalah konferensi dan workshop (*inproceedings*) DBLP tahun 2015–2025 hasil preprocessing,
bersumber dari rilis DBLP 2026-11-01. Semua eksperimen menggunakan dataset ini.

| File | Isi | Baris |
|------|-----|-------|
| `dblp_clean.parquet` | Satu baris per makalah | 1.996.703 |
| `paper_author.parquet` | Satu baris per pasangan makalah–penulis | 7.868.451 |
| `*.csv` | Isi yang sama dalam format CSV | |
| `SHA256SUMS` | Checksum seluruh file | |

Notebook membaca file parquet. File CSV disediakan sebagai salinan, ditulis dengan UTF-8,
pemisah koma, dan tanda kutip pada setiap nilai teks.

## `dblp_clean`

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| `paper_key` | string | Key DBLP, unik per makalah |
| `title` | string | Judul makalah |
| `year` | int16 | Tahun terbit, 2015–2025 |
| `venue_id` | string | ID venue hasil normalisasi, misalnya `cvpr` atau `cvpr_workshops` |
| `venue_name` | string | Nama tampilan venue, misalnya `CVPR` atau `CVPR Workshops` |
| `track` | string | `main`, `workshop`, atau `companion` |
| `booktitle` | string | Nama prosiding asli dari DBLP; kosong pada 190 makalah |
| `n_authors` | int16 | Jumlah penulis |

## `paper_author`

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| `paper_key` | string | Merujuk ke `dblp_clean.paper_key` |
| `author` | string | Nama penulis hasil normalisasi, berfungsi sebagai ID penulis |
| `author_pos` | int16 | Urutan penulis pada makalah, dimulai dari 1 |
| `year` | int16 | Tahun terbit makalah |
| `venue_id` | string | Venue makalah |

## Catatan

- `venue_id` diturunkan dari seri pada `paper_key` (`conf/<seri>/...`). Terdapat 4.876 venue:
  4.372 konferensi dan 504 kelompok workshop. Makalah workshop dipisah ke `<seri>_workshops`,
  sedangkan trek pendamping (findings, poster, demo, dan sejenisnya) tetap pada venue induknya.
  Pemetaan lengkap tersedia di `results/tables/venue_mapping.csv`.
- Nama penulis mempertahankan nomor pembeda homonim dari DBLP, misalnya `Jian Sun 0001`.
  Terdapat 1.817.265 penulis unik.

## Memperoleh Dataset

File dapat diunduh dari folder Google Drive kelompok, lalu diletakkan di folder ini.
Keasliannya diperiksa dengan:

```bash
cd data
sha256sum -c SHA256SUMS
```

Dataset juga dapat dibuat ulang dari data mentah DBLP:

```bash
python src/download.py
python src/extract.py
python src/export.py
```

Dengan versi library pada `requirements.txt`, hasilnya identik dengan checksum di
`results/tables/dataset_files.csv`.
