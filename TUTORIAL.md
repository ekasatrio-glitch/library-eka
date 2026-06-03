# Tutorial library-eka — Setup & Pemakaian

Panduan langkah demi langkah untuk menjalankan **library-eka** di laptop (macOS/Linux):
perpustakaan PDF akademik lokal dengan RAG (tanya-jawab bersitasi), draft paragraf,
mindmap, proyek/workspace, matriks sintesis literatur, dan rename PDF otomatis.

Semua jalan **lokal**. Yang keluar internet hanya: panggilan LLM (DeepSeek/Jatevo) dan
opsional Crossref saat rename. Embedding & pencarian jalan di mesin sendiri.

---

## 0. Gambaran Singkat

```
PDF  ──►  Extract (Docling)  ──►  Chunk  ──►  Embed (Ollama/nomic)  ──►  SQLite (sqlite-vec + FTS5)
                                                                              │
Tanya ──► Hybrid search (vektor + keyword) ──► Rerank ──► LLM ──► Jawaban + sitasi klik-ke-halaman
```

- **Extractor**: Docling (urutan baca multi-kolom benar, tabel jadi markdown, OCR opsional).
- **Embedding**: Ollama `nomic-embed-text` (768 dim) — lokal, gratis.
- **LLM**: DeepSeek (default) atau Jatevo — perlu API key.
- **DB**: satu file SQLite (`data/library.db`).

---

## 1. Prasyarat

| Kebutuhan | Kenapa |
|-----------|--------|
| **Python 3.11+** (teruji 3.14) | Menjalankan aplikasi |
| **Ollama** | Embedding lokal (`nomic-embed-text`) |
| **API key LLM** | DeepSeek (`https://platform.deepseek.com`) atau Jatevo |
| ~2 GB disk | Model Docling + Ollama (sekali unduh) |

Cek Python:
```bash
python3 --version
```

---

## 2. Install

```bash
cd "library-eka"

# 1) Virtualenv
python3 -m venv venv
source venv/bin/activate

# 2) Dependencies (fastapi, docling, sqlite-vec, flashrank, dll)
pip install -r requirements.txt
```

> Catatan: `pip install -r requirements.txt` menarik `torch` + model Docling cukup besar.
> **Run pertama** ekstraksi akan mengunduh model layout/tabel Docling (ratusan MB) — sekali saja.

---

## 3. Ollama (embedding lokal)

```bash
# Install (macOS): https://ollama.com/download  — atau:
curl -fsSL https://ollama.com/install.sh | sh

# Tarik model embedding (768 dim, dipakai library-eka)
ollama pull nomic-embed-text

# Jalankan server (biarkan hidup di terminal lain / service)
ollama serve
```

Tes Ollama hidup:
```bash
curl http://localhost:11434/api/tags
```

---

## 4. Konfigurasi `.env`

Salin template lalu isi:
```bash
cp .env.example .env
```

Edit `.env` — minimal yang **wajib** diisi:
```ini
# LLM (pilih salah satu provider)
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxxxxxxx        # <-- WAJIB diisi
DEEPSEEK_BASE_URL=https://api.deepseek.com

# Embedding (lokal, biarkan default)
EMBED_MODEL=nomic-embed-text
EMBED_DIM=768
OLLAMA_BASE_URL=http://localhost:11434

# Folder yang dipantau watcher (PDF baru auto-ingest). Pisah dengan koma.
WATCH_FOLDERS=/Users/kamu/Papers

# Lokasi DB (default oke)
DB_PATH=data/library.db
```

Opsi lanjutan (boleh dibiarkan default):
```ini
EXTRACTOR=docling     # docling (akurat) | pymupdf (cepat, tanpa model)
OCR=false             # true = OCR untuk PDF hasil scan (lebih lambat)
RERANKER=flashrank    # flashrank | bge | none
RENAME_PATTERN={authors} ({year}) - {title}
CROSSREF_ENABLED=true
```

> Pakai **Jatevo** sebagai LLM? Set `LLM_PROVIDER=jatevo`, isi `JATEVO_API_KEY` dan
> `JATEVO_BASE_URL` (base URL **wajib** — kalau kosong aplikasi sengaja error, bukan diam).

---

## 5. Masukkan PDF (Ingest)

Dua cara:

**A. Sekali jalan (manual)** — scan file/folder:
```bash
python -m app.ingest.pipeline /path/ke/folder-pdf
python -m app.ingest.pipeline paper1.pdf paper2.pdf
```
Output: `[OK]`, `[SKIP]` (sudah pernah, dedup by hash), `[ERR]`.

**B. Otomatis (watcher)** — pantau `WATCH_FOLDERS`, ingest PDF baru begitu masuk:
```bash
python -m app.ingest.watcher
```

Ingest melakukan: extract (Docling) → chunk → embed (Ollama) → simpan ke SQLite + indeks
keyword (FTS5). Halaman tiap chunk dilacak supaya sitasi bisa klik-ke-halaman.

---

## 6. Jalankan Aplikasi

**Paling gampang (macOS):** double-click **`scripts/start.command`** di Finder.
Otomatis: nyalakan Ollama (kalau mati) → watcher + web → buka browser.
Berhenti: Ctrl-C di jendela Terminal yang muncul.
> Pertama kali macOS bisa blokir ("unidentified developer"): klik-kanan file → **Open** → Open.

**Atau** lewat terminal (watcher + web sekaligus):
```bash
scripts/run.sh
```
Buka **http://127.0.0.1:8765**

Atau manual (web saja):
```bash
python -m uvicorn app.web.app:app --host 127.0.0.1 --port 8765
```

Log watcher: `logs/watcher.log`.

---

## 7. Pakai Fitur (Web UI)

Tab di bagian atas:

### Tanya (RAG bersitasi)
Ketik pertanyaan → jawaban ringkas Bahasa Indonesia + daftar sitasi `[n]`.
Klik sitasi → PDF terbuka **persis di halaman sumber** (viewer PDF.js).
Filter opsional: tahun, penulis.

### Draft
Tulis topik → satu paragraf akademik tersintesis + referensi, gaya **Vancouver** atau **APA**.
Tiap klaim diikat ke sumber; kalau bukti kurang, klaim dihilangkan (bukan dikarang).

### Mindmap
Topik → subtopik otomatis (multi-query retrieval) → outline markdown → render MarkMap.

### Pustaka
Daftar semua PDF ter-index. Cari judul/penulis, filter folder/tahun. Tombol buka viewer.
Di sini juga ada **Rename PDF sesuai judul** (lihat §9).

### Proyek (workspace)
Lihat §8.

---

## 8. Proyek + Matriks Sintesis

Korpus tetap **satu global**; proyek hanya merujuk subset paper (tak ada duplikasi).

1. **Buat proyek** (tab Proyek) → kasih nama.
2. **Tambah paper**:
   - *Impor dari pustaka* — centang paper yang sudah ter-index, atau
   - *Unggah PDF* — drop file baru (di-ingest ke korpus global sekali, lalu ditautkan).
3. **Chat ter-scope** — default jawaban **hanya** dari paper proyek. Centang
   *"Perluas ke seluruh library"* untuk lintas korpus. Ada **nudge**: "N paper lain
   mungkin relevan — tambahkan?".
4. **Buat Matriks** — ekstraksi terstruktur per paper, skema auto-deteksi:
   - **empiris**, **review**, atau **meta-analisis**.
   - Grounded ketat: kalau paper tak menyatakan sesuatu → ditulis `tidak disebutkan`
     / `tidak dilaporkan` (tak menebak). Kelemahan dipisah: *limitasi penulis* vs
     *saran — perlu verifikasi*. Paper pendukung hanya dari korpus (sitasi nyata).
     Notes = `(draft)`.
   - Tampilan: **Matriks / Linimasa (per tahun) / Tema (per tag)**.
5. **Ekspor** XLSX/CSV (siap impor Google Sheets). XLSX mewarnai sel tag sesuai
   **codebook**. *Bootstrap codebook* dari sheet/CSV lama → tag konsisten (closed coding).

---

## 9. Rename PDF Sesuai Judul

Ubah nama file berantakan jadi `Penulis (Tahun) - Judul.pdf` (pola configurable).
Judul diekstrak **semantik** (LLM + Crossref), bukan regex. **Aman registry**: file
di-rename di disk **dan** path di DB di-update satu transaksi — tidak memicu re-embed.

Alur (di tab Pustaka, atau via API):
1. **Preview** → tabel *nama lama → nama baru* (belum mengubah apa pun).
2. **Terapkan** → eksekusi setelah konfirmasi (tabrakan nama dapat suffix `(2)`).
3. **Undo** → kembalikan batch terakhir dari log.

API setara: `GET /rename/preview`, `POST /rename/apply`, `POST /rename/undo`.

---

## 10. Endpoint API (ringkas)

| Method | Path | Fungsi |
|--------|------|--------|
| POST | `/ask` | Tanya korpus → jawaban + sitasi |
| POST | `/draft` | Paragraf akademik (Vancouver/APA) |
| POST | `/mindmap` | Outline mindmap |
| GET | `/library` | Daftar dokumen + filter |
| GET | `/pdf/{id}` · `/viewer` | Stream PDF · viewer klik-ke-halaman |
| POST/GET | `/projects` … | CRUD proyek, paper, chat scoped, matriks, ekspor, codebook |
| GET/POST | `/rename/preview·apply·undo` | Rename by title |

---

## 11. Verifikasi & Test

```bash
python -m pytest -q          # seluruh test suite
```

Cek cepat aplikasi hidup:
```bash
curl -s http://127.0.0.1:8765/library | head
```

---

## 12. Troubleshooting

| Gejala | Sebab & solusi |
|--------|----------------|
| `LLM API key missing` | `DEEPSEEK_API_KEY` (atau `JATEVO_API_KEY`) kosong di `.env`. |
| Jawaban "Tidak ada bukti relevan" | Korpus kosong / belum ingest. Jalankan §5. |
| Embedding error / koneksi gagal | Ollama belum jalan atau model belum ditarik. `ollama serve` + `ollama pull nomic-embed-text`. |
| Ingest pertama lambat | Docling mengunduh + menjalankan model deep-learning. Biaya **sekali**, offline. |
| PDF scan tak ada teks | Set `OCR=true` di `.env` (lebih lambat). |
| Mau extractor cepat tanpa model | Set `EXTRACTOR=pymupdf`. |
| Rename `503` | LLM key belum di-set (judul diekstrak via LLM). |

---

## 13. Migrasi (opsional)

Kalau korpus lama perlu diekstrak ulang dengan Docling (embedding tetap nomic):
```bash
python -m app.ingest.reingest --all       # idempotent; --force untuk ulang
```

Upgrade embedding ke `bge-m3` (akurasi lebih tinggi, **paksa re-embed**, dim 1024):
```bash
ollama pull bge-m3
python -m app.ingest.reembed --model bge-m3 --dim 1024
# lalu set EMBED_MODEL=bge-m3 dan EMBED_DIM=1024 di .env
```
Lihat `README.md` untuk konsekuensi VPS.

---

Selesai. Untuk arsitektur & detail teknis, baca `README.md`.
