# library-eka — Rencana Pembangunan Project

> RAG lokal personal untuk korpus karya ilmiah: korpus permanen, privat, sitasi presisi (klik-ke-halaman PDF), synthesis lintas dokumen, paragraf akademik, mindmap/graph. Berjalan di MacBook M4 16 GB, dengan sinkronisasi ke VPS agar bisa diakses lewat agent Hermes (Telegram) saat di perjalanan.

---

## Cara Menjalankan (BACA INI DULU)

1. `cd` ke folder kosong untuk project ini.
2. Jalankan Claude Code dalam mode tanpa konfirmasi:
   ```bash
   claude --dangerously-skip-permissions
   ```
   Flag ini membuat semua tool (edit file, bash, git) berjalan otomatis **tanpa meminta tekan Enter**. Sebagai cadangan di dalam sesi, tekan `Shift+Tab` untuk mengaktifkan auto-accept edits.
3. Paste **KICKOFF PROMPT** di bawah.

### KICKOFF PROMPT (paste apa adanya)

```
Baca file library-eka-PLAN.md di folder ini, lalu kerjakan SELURUH phase dari Phase 0 sampai Phase 9 secara berurutan.

ATURAN:
- Gunakan skill Superpowers sepanjang pengerjaan (brainstorm singkat → rencana → implementasi → verifikasi → commit).
- Bekerja sepenuhnya autonomous. JANGAN berhenti untuk bertanya atau meminta konfirmasi apa pun. Jika ada keputusan ambigu, ambil pilihan paling masuk akal sesuai PLAN dan lanjут.
- Setelah setiap phase selesai dan acceptance terpenuhi, langsung jalankan git commit phase tersebut (perintah ada di tiap phase), baru lanjut phase berikutnya.
- Jangan tunggu instruksi tambahan dari saya antar-phase. Lanjutkan otomatis sampai Phase 9 selesai.
- Jika sebuah perintah gagal, perbaiki sendiri lalu lanjutkan; jangan berhenti menunggu saya.
- Di akhir, tampilkan ringkasan singkat dan output `git log --oneline`.

Mulai sekarang dari Phase 0.
```

---

## Aturan Global untuk Claude Code

- **Skill:** gunakan skill **Superpowers** untuk disiplin alur kerja dan kualitas kode.
- **Autonomous:** tidak ada jeda konfirmasi. Lanjut antar-phase otomatis.
- **Git per phase:** tiap phase diakhiri dengan commit (perintah tertera). Phase 0 melakukan `git init`.
- **Bahasa:** komentar kode & README boleh Inggris; UI default Bahasa Indonesia.
- **Lingkungan:** Python `venv`. Install lib dengan `pip install <pkg>` di dalam venv.
- **Rahasia:** API key di `.env` (jangan commit). Sediakan `.env.example`.
- **Estetika UI:** minimalis, gelap, bersih. Tanpa hiasan berlebihan.

## Stack (acuan tetap)

- Backend: **Python + FastAPI**
- Ekstraksi PDF: **PyMuPDF (fitz)** — teks per halaman
- Penyimpanan (registry + metadata + vektor, satu file): **SQLite + sqlite-vec**
- Embedding (lokal): **Ollama `nomic-embed-text`** (dipilih agar ringan & konsisten di VPS)
- Generation: **DeepSeek API** (OpenAI-compatible); **Jatevo** sebagai fallback (tinggal ganti `base_url`+key)
- Ingestion otomatis: **watchdog** (folder watcher) + debounce + antrian + startup scan
- Web lokal: **FastAPI + PDF.js** (viewer + klik-ke-halaman) + UI chat
- Mindmap: **MarkMap** (render dari markdown)
- Persistence (macOS): **LaunchAgent**
- Remote: **rsync** file sqlite-vec ke VPS → dibaca **Hermes**

---

## Phase 0 — Scaffold & Git

**Tujuan:** kerangka project + git aktif.

**Tugas:**
- [ ] `git init`.
- [ ] Buat struktur:
  ```
  library-eka/
  ├── app/            # backend FastAPI
  │   ├── core/       # db, config
  │   ├── ingest/     # extractor, chunker, embedder, watcher
  │   ├── rag/        # retrieval, generation, citation
  │   └── web/        # routes, static, templates
  ├── data/           # db file + (pdf disimpan di folder eksternal yg di-watch)
  ├── scripts/        # sync_to_vps.sh, dll
  ├── tests/
  ├── .env.example
  ├── .gitignore
  ├── requirements.txt
  └── README.md
  ```
- [ ] `venv` + `requirements.txt` awal: `fastapi uvicorn pymupdf watchdog sqlite-vec openai python-dotenv jinja2`.
- [ ] `.gitignore`: `.env`, `venv/`, `__pycache__/`, `*.db`, `data/`, `*.pdf`.
- [ ] `.env.example`: `DEEPSEEK_API_KEY=`, `DEEPSEEK_BASE_URL=https://api.deepseek.com`, `JATEVO_API_KEY=`, `JATEVO_BASE_URL=`, `LLM_PROVIDER=deepseek`, `EMBED_MODEL=nomic-embed-text`, `WATCH_FOLDERS=`.
- [ ] README ringkas.

**Acceptance:** struktur ada, venv jalan, `import fastapi` sukses.

**Git:**
```bash
git add -A && git commit -m "Phase 0: scaffold project, venv, gitignore, env template"
```

---

## Phase 1 — Data Layer (sqlite-vec, satu file)

**Tujuan:** satu DB SQLite menampung registry + metadata + vektor.

**Tugas:**
- [ ] Modul `app/core/db.py`: init koneksi, load ekstensi sqlite-vec.
- [ ] Skema:
  - `documents` (registry): `id, path UNIQUE, content_hash, title, authors, year, folder, added_at, status`.
  - `chunks`: `id, doc_id FK, page_start, page_end, text, char_len`.
  - `vec_chunks`: virtual table sqlite-vec menyimpan embedding (dimensi sesuai `nomic-embed-text` = 768), terhubung ke `chunks.id`.
- [ ] Fungsi: `init_db()`, `upsert_document()`, `insert_chunk()`, `document_exists(hash)`.

**Acceptance:** `init_db()` membuat file DB + semua tabel; insert & query vektor dummy berhasil.

**Git:**
```bash
git add -A && git commit -m "Phase 1: sqlite-vec schema (registry + metadata + vectors) in one DB"
```

---

## Phase 2 — Ingestion Pipeline

**Tujuan:** PDF → chunk (lacak halaman) → embed → simpan, idempotent.

**Tugas:**
- [ ] `extractor.py`: PyMuPDF ekstrak teks **per halaman** (simpan nomor halaman).
- [ ] `metadata.py`: tebak `title/authors/year` dari halaman pertama (best-effort; boleh sederhana).
- [ ] `chunker.py`: chunk dengan overlap (default 1000 token, overlap 200); tiap chunk membawa `page_start/page_end`.
- [ ] `embedder.py`: panggil Ollama `nomic-embed-text` (lokal) untuk embedding batch.
- [ ] `pipeline.py`: untuk satu PDF → cek `content_hash` di registry (skip jika sudah ada) → extract → chunk → embed → upsert document + chunks + vektor → set `status=done`.
- [ ] CLI `python -m app.ingest.pipeline <folder>`: scan rekursif sebuah folder, proses semua PDF.

**Acceptance:** ingest 1 folder berisi beberapa PDF → DB terisi; jalankan ulang → semua di-skip (idempotent).

**Git:**
```bash
git add -A && git commit -m "Phase 2: ingestion pipeline (extract per-page, chunk, embed, idempotent upsert)"
```

---

## Phase 3 — Auto-Ingest Watcher

**Tujuan:** drop PDF → otomatis ter-chunk, tahan terhadap restart.

**Tugas:**
- [ ] `watcher.py` (watchdog): pantau banyak root folder (dari `WATCH_FOLDERS`) secara rekursif.
- [ ] **Debounce**: setelah event, tunggu ukuran file stabil (~2 dtk) sebelum proses (hindari file belum selesai ditulis).
- [ ] **Antrian + worker**: file baru masuk queue; worker proses satu per satu (jangan proses di thread watcher).
- [ ] **Startup reconciliation scan**: saat start, scan semua folder, proses yang belum ada di registry.

**Acceptance:** dengan watcher jalan, menyalin PDF baru ke folder → otomatis terproses. Matikan watcher, tambah file, nyalakan lagi → startup scan menangkapnya.

**Git:**
```bash
git add -A && git commit -m "Phase 3: folder watcher (debounce + queue) + startup reconciliation scan"
```

---

## Phase 4 — RAG Core (Retrieval + Generation + Sitasi)

**Tujuan:** tanya → jawab ter-grounding dengan sitasi presisi (dokumen + halaman).

**Tugas:**
- [ ] `retriever.py`: embed pertanyaan (model SAMA, `nomic-embed-text`) → vector search top-k di sqlite-vec → kembalikan chunk + metadata (path, halaman, judul). Dukung filter metadata (mis. `year >= 2024`).
- [ ] `generator.py`: klien OpenAI-compatible; `base_url`/key dari `.env` sesuai `LLM_PROVIDER` (deepseek/jatevo). Susun jawaban dari konteks.
- [ ] **Disiplin sitasi:** setiap klaim wajib menunjuk chunk sumbernya; kembalikan struktur sitasi `{doc_id, title, page}`. Dilarang mengarang referensi.
- [ ] Fungsi `ask(question, filters)` → `{answer, citations[]}`.

**Acceptance:** pertanyaan uji menghasilkan jawaban + daftar sitasi berisi judul & nomor halaman yang valid.

**Git:**
```bash
git add -A && git commit -m "Phase 4: RAG core — retrieval, DeepSeek generation, grounded citations (doc+page)"
```

---

## Phase 5 — Web Lokal (Chat + PDF.js + Library)

**Tujuan:** UI lokal minimalis: chat, viewer PDF klik-ke-halaman, jelajah pustaka.

**Tugas:**
- [ ] Routes FastAPI: `POST /ask`, `GET /library` (daftar + filter metadata), `GET /pdf/{doc_id}` (sajikan file), `GET /viewer` (PDF.js).
- [ ] Integrasi **PDF.js**: sitasi di jawaban = tautan ke `viewer?doc={id}#page={n}` → buka PDF persis di halaman sumber (panel samping).
- [ ] UI chat: kirim pertanyaan, tampilkan jawaban + sitasi yang bisa diklik.
- [ ] Tampilan **Library**: tabel/grid semua PDF ter-index, filter per folder/tahun/penulis, klik buka.
- [ ] Desain: gelap, minimalis, bersih.

**Acceptance:** `uvicorn` jalan; bisa tanya, klik sitasi → PDF terbuka di halaman benar; library bisa difilter.

**Git:**
```bash
git add -A && git commit -m "Phase 5: local web app — chat UI, PDF.js click-to-page citations, library view"
```

---

## Phase 6 — Generator Paragraf Akademik

**Tujuan:** draf paragraf karya ilmiah yang ter-grounding + format sitasi.

**Tugas:**
- [ ] `POST /draft`: input topik → multi-retrieval lintas dokumen → LLM susun paragraf yang menyintesis sumber.
- [ ] Tiap kalimat/klaim tertaut sumber (doc + halaman); sediakan opsi gaya sitasi **Vancouver** (default, medis) / **APA**.
- [ ] **Integritas:** hanya pakai sumber yang ter-retrieve; tidak mengarang sitasi. Tampilkan daftar referensi di akhir.

**Acceptance:** input topik → paragraf akademik + referensi bernomor yang cocok dengan sumber nyata di korpus.

**Git:**
```bash
git add -A && git commit -m "Phase 6: academic paragraph generator (grounded synthesis + Vancouver/APA citations)"
```

---

## Phase 7 — Mindmap / Graph

**Tujuan:** mindmap sebuah topik dari korpus.

**Tugas:**
- [ ] `POST /mindmap`: topik → multi-query retrieval → LLM strukturkan jadi hierarki → keluarkan **markdown MarkMap**.
- [ ] Render MarkMap di UI; node idealnya tertaut ke sumber (doc+halaman) bila memungkinkan.

**Acceptance:** input topik → mindmap interaktif tampil dari isi korpus.

**Git:**
```bash
git add -A && git commit -m "Phase 7: mindmap generator (multi-query retrieval -> MarkMap render)"
```

---

## Phase 8 — Sinkronisasi VPS + Hermes (akses Telegram)

**Tujuan:** korpus bisa diakses lewat Hermes saat tanpa laptop.

**Tugas:**
- [ ] `scripts/sync_to_vps.sh`: buat **snapshot bersih** DB sqlite-vec (saat ingestion idle), lalu `rsync` over SSH ke VPS. Dipicu otomatis setelah worker selesai batch.
- [ ] Catatan setup VPS (tulis di README, section "VPS"):
  - Install ekstensi **sqlite-vec** di VPS.
  - Jalankan **`nomic-embed-text` via Ollama di VPS** (untuk embed pertanyaan — WAJIB model sama agar dimensi cocok).
  - Handler Hermes: terima pertanyaan Telegram → embed (nomic) → retrieval dari DB tersinkron → generation via **Jatevo** → balas (inline pendek / `.md` bila panjang).
- [ ] Pastikan jangan rsync saat DB sedang ditulis (gunakan snapshot).

**Acceptance:** script sync menghasilkan DB di VPS; (jika VPS tersedia) Hermes bisa menjawab pertanyaan korpus via Telegram.

**Git:**
```bash
git add -A && git commit -m "Phase 8: VPS sync (snapshot + rsync) + Hermes RAG handler notes"
```

---

## Phase 9 — Persistence (macOS) & Polish

**Tujuan:** watcher jalan otomatis + finalisasi.

**Tugas:**
- [ ] `scripts/com.eka.library.watcher.plist` (LaunchAgent): auto-start watcher saat login, restart bila crash. Sertakan instruksi `launchctl load`.
- [ ] `scripts/run.sh`: nyalakan web + watcher.
- [ ] Finalisasi README: setup, cara pakai, struktur, catatan VPS.
- [ ] Cek akhir: lint ringan, pastikan semua endpoint hidup.

**Acceptance:** satu perintah menjalankan sistem; watcher persisten via LaunchAgent; README lengkap.

**Git:**
```bash
git add -A && git commit -m "Phase 9: macOS LaunchAgent persistence, run scripts, finalize README"
```

---

## Selesai

Setelah Phase 9, tampilkan ringkasan + `git log --oneline`.
