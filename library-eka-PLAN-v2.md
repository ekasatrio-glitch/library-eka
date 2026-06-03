# library-eka — Update Plan v2 (Proyek + Matriks Sintesis)

> Lanjutan dari `library-eka-PLAN.md` (Phase 0–9 sudah selesai). File ini menambahkan **Phase 10–13**: konsep Proyek/Workspace, chat ter-scope, dan mesin **Matriks Sintesis Literatur** (3 skema: empiris, review, meta-analisis) dengan aturan grounding ketat (tidak LLM-driven).

---

## Cara Menjalankan

1. `cd library-eka` (folder project yang sudah ada).
2. Jalankan tanpa konfirmasi:
   ```bash
   claude --dangerously-skip-permissions
   ```
3. Paste **KICKOFF PROMPT** di bawah.

### KICKOFF PROMPT (paste apa adanya)

```
Baca file library-eka-PLAN-v2.md di folder ini. Ini LANJUTAN dari project yang sudah ada (Phase 0–9 sudah dibangun). JANGAN membangun ulang dari awal — integrasikan fitur baru ke kode yang sudah ada (db.py, retriever, generator, web, dll).

Kerjakan SELURUH phase dari Phase 10 sampai Phase 14 secara berurutan.

ATURAN:
- Gunakan skill Superpowers sepanjang pengerjaan.
- Bekerja sepenuhnya autonomous. JANGAN berhenti untuk bertanya atau meminta konfirmasi apa pun. Jika ada keputusan ambigu, ambil pilihan paling masuk akal sesuai file ini dan lanjut.
- Pelajari dulu struktur kode yang sudah ada sebelum mengubah; pertahankan satu DB sqlite-vec yang sama.
- Setelah setiap phase selesai dan acceptance terpenuhi, langsung jalankan git commit phase tersebut (perintah ada di tiap phase), baru lanjut.
- Jika sebuah perintah gagal, perbaiki sendiri lalu lanjutkan; jangan berhenti menunggu saya.
- Di akhir, tampilkan ringkasan singkat dan output `git log --oneline`.

Mulai sekarang dari Phase 10.
```

---

## Prinsip Inti (WAJIB dipatuhi di Phase 12–13)

**Tidak LLM-driven — semua field di-ground ke paper-atau-korpus:**

1. Setiap nilai field harus dapat dilacak ke (a) span di dalam paper itu sendiri, atau (b) paper lain di korpus (dengan sitasi nyata: judul + halaman).
2. Jika paper tidak menyatakan sesuatu → tulis **"tidak disebutkan dalam paper"** (atau **"tidak dilaporkan"** untuk metode meta-analisis). DILARANG menebak/mengarang/menginferensi.
3. **Kelemahan** dipisah dua kolom: (a) *limitasi yang dinyatakan penulis* (ekstrak dari paper), (b) *saran kritis* yang ditandai tegas **"saran — perlu verifikasi"**. Jangan dicampur.
4. **Paper pendukung** HANYA dari korpus (kecocokan semantik temuan antar-PDF), disitasi ke paper + halaman nyata. DILARANG dari ingatan LLM (sumber halusinasi sitasi).
5. **Notes** (interpretasi) dihasilkan hanya sebagai **draft saran** bertanda jelas; pengguna yang menulis ulang. Analisis tetap milik pengguna.

---

## Phase 10 — Proyek/Workspace (Data + API)

**Tujuan:** korpus global tetap satu; proyek hanya merujuk subset paper (tanpa duplikasi/embed ulang).

**Tugas:**
- [ ] Tambah tabel ke DB sqlite-vec yang sudah ada:
  - `projects` (`id, name, description, created_at`).
  - `project_documents` (`project_id, doc_id`) — relasi many-to-many ke `documents` yang sudah ada. Satu paper boleh ada di banyak proyek.
  - `project_codebook` (`project_id, tag, category, color`) — kosakata tag per-proyek (diisi di Phase 13).
- [ ] API:
  - `POST /projects` (buat), `GET /projects` (daftar), `GET /projects/{id}`, `DELETE /projects/{id}`.
  - `POST /projects/{id}/papers` — tambah paper ke proyek dengan dua jalur:
    1. dari library global (kirim daftar `doc_id` yang dipilih);
    2. drop PDF baru → ingest ke korpus global (pipeline Phase 2, sekali) + tautkan ke proyek.
  - `DELETE /projects/{id}/papers/{doc_id}` — lepas dari proyek (paper tetap di korpus global).
  - `GET /projects/{id}/papers` — daftar paper dalam proyek.

**Acceptance:** bisa buat proyek, impor beberapa paper dari library global, drop PDF baru ke proyek; paper tidak tergandakan di korpus.

**Git:**
```bash
git add -A && git commit -m "Phase 10: projects/workspaces (data model + import API, no duplication)"
```

---

## Phase 11 — UI Proyek + Chat Ter-scope

**Tujuan:** kerja di dalam proyek; chat default fokus ke paper proyek.

**Tugas:**
- [ ] **Daftar proyek** + tombol buat proyek baru.
- [ ] **Halaman detail proyek**: daftar paper di proyek, tombol "Impor paper".
- [ ] **Picker library global ("all paper")**: tampilkan semua paper ter-index (pakai Library view Phase 5), centang untuk diimpor ke proyek; plus drop-zone PDF baru.
- [ ] **Chat ter-scope (KEPUTUSAN FINAL):**
  - Default: retrieval **hanya** dari paper proyek (`WHERE doc_id IN (paper proyek)`).
  - Toggle **"Perluas ke seluruh library"** untuk penemuan lintas korpus.
  - **Nudge halus**: di samping jawaban, tampilkan "N paper lain di library Anda mungkin relevan — tambahkan ke proyek?" (hasil pencarian seluruh library di latar, tanpa mencemari jawaban utama).
- [ ] Sitasi tetap klik-ke-halaman (PDF.js Phase 5).

**Acceptance:** di proyek HES, tanya → jawaban + sitasi hanya dari paper proyek; toggle perluas berfungsi; nudge muncul bila ada kandidat.

**Git:**
```bash
git add -A && git commit -m "Phase 11: project UI + scoped chat (default project, expand toggle, discovery nudge)"
```

---

## Phase 12 — Mesin Matriks Sintesis (3 Skema + Grounding)

**Tujuan:** ekstraksi terstruktur per paper, scoped ke proyek, patuh Prinsip Inti.

**Tugas:**
- [ ] **Deteksi otomatis jenis paper** dari judul/abstrak/struktur → `empiris` | `review` | `meta-analisis`. Sediakan override manual.
- [ ] Endpoint `POST /projects/{id}/matrix` — untuk tiap paper proyek, ekstrak field sesuai skema-nya. Patuhi Prinsip Inti (gap → "tidak disebutkan"; pendukung dari korpus; notes = draft).
- [ ] **Skema A — Empiris:** Source, Page(s), Main finding, Definisi operasional tiap variabel, Penyebab/mekanisme (stated; else "tidak dijelaskan"), Kontroversi (diakui paper + ketegangan korpus), Kelemahan [limitasi penulis | saran-perlu-verifikasi], Paper pendukung (korpus), Tag, Notes (draft).
- [ ] **Skema B — Review (naratif/sistematis):** Jenis & cakupan (naratif/scoping/systematic; jika systematic: PRISMA, jumlah studi, strategi pencarian), Pertanyaan/tujuan, Sintesis utama, Tema/argumen utama, Definisi konsep kunci, Area konsensus vs perdebatan, Gap penelitian, Studi kunci dirujuk (tautkan korpus bila ada), Kelemahan review (+ risk of bias jika systematic), Tag, Notes.
- [ ] **Skema C — Meta-analisis** (warisi field review +): PICO, Jenis & protokol (PRISMA/PROSPERO, database, tanggal), Jumlah studi & total peserta, Effect measure & outcome, **Pooled estimate + 95% CI + p (= main finding)**, Model (fixed/random + metode: DL/REML/MH/IV), Heterogenitas (I², τ², Q + p), Subgrup/meta-regresi, Analisis sensitivitas, Bias publikasi (funnel/Egger/trim-fill), Penilaian kualitas (RoB/GRADE), Studi dimasukkan (korpus), Kontroversi vs MA terdahulu, Kelemahan. Untuk meta-analisis, field **"tidak dilaporkan" otomatis mengalir ke kolom Kelemahan**.
- [ ] Tiap sel menyimpan referensi sumber (doc_id + halaman) agar bisa diklik balik ke PDF.

**Acceptance:** jalankan matrix pada proyek campuran (paper empiris + review + meta-analisis) → tiap paper diekstrak dengan skema benar; gap tertulis eksplisit; pendukung menunjuk paper korpus nyata; notes bertanda draft.

**Git:**
```bash
git add -A && git commit -m "Phase 12: synthesis matrix engine (empirical/review/meta-analysis schemas, grounded, scoped to project)"
```

---

## Phase 13 — Ekspor Matriks + Tampilan Alternatif

**Tujuan:** keluaran format spreadsheet + codebook tag + tampilan lain.

**Tugas:**
- [ ] **Ekspor XLSX/CSV** dari matriks proyek, siap impor ke Google Sheets.
- [ ] **Tag berwarna**: terapkan conditional formatting di XLSX berdasarkan `project_codebook` (tag → warna). Untuk CSV, ekspor tag polos.
- [ ] **Bootstrap codebook (opsional):** endpoint untuk unggah sheet/CSV matriks lama (mis. BAB 1) → pelajari kosakata tag + warna → simpan ke `project_codebook`. Tag baru di-assign **closed coding** dari codebook ini (konsisten, bukan tag bebas).
- [ ] **Tampilan alternatif dari data matriks yang sama:**
  - `matrix` (default).
  - `linimasa` — urut berdasarkan tahun (timeline).
  - `tema` — dikelompokkan per Tag.
- [ ] Tombol ekspor per tampilan.

**Acceptance:** matriks proyek bisa diekspor ke XLSX (tag berwarna sesuai codebook) + diimpor ke Google Sheets; bootstrap dari sheet lama menghasilkan tag konsisten; tampilan linimasa & tema tampil dari data yang sama.

**Git:**
```bash
git add -A && git commit -m "Phase 13: matrix export (XLSX/CSV + codebook colors, bootstrap) + timeline/theme views"
```

---

## Phase 14 — Rename PDF Sesuai Judul (tanpa regex)

**Tujuan:** rename semua PDF jadi `Penulis (Tahun) - Judul.pdf` (pola default, configurable), dengan judul bersih, aman terhadap registry, dan bisa di-undo.

**Prinsip: judul diekstrak secara semantik, BUKAN regex.** Layout PDF terlalu beragam untuk pola.

**Tugas:**
- [ ] **Pipeline judul bersih** (`app/ingest/title.py`), urutan keandalan:
  1. **LLM ekstraksi** dari teks halaman pertama (PyMuPDF) → DeepSeek, prompt ketat, minta output JSON `{"title": "...", "authors": [...], "year": ...}`, parse dengan `json.loads` (bukan regex). Beri petunjuk: blok **font terbesar** di atas halaman (`page.get_text("dict")`, pilih `size` terbesar) + metadata `/Title` bawaan (`doc.metadata['title']`) sebagai kandidat.
  2. **Kanonikalisasi Crossref** (opsional, bila online): kirim judul/teks ke Crossref bibliographic query → ambil judul + penulis + tahun resmi. Gratis, tanpa key.
  3. Fallback bila offline: pakai hasil LLM saja.
- [ ] **Pembersihan string tanpa regex:** `unicodedata.normalize("NFKC", t)` → `" ".join(t.split())` (rapikan spasi/newline) → `str.translate` dengan peta karakter ilegal (`/ \ : * ? " < > |` → `-`) → potong panjang bila perlu. Tidak ada regex.
- [ ] **Susun nama file** dari pola default `Penulis (Tahun) - Judul.pdf` (configurable lewat `.env`/setting).
- [ ] **JEBAKAN registry — wajib benar:** rename file di disk HARUS dibarengi update kolom `path` di tabel `documents` dalam satu transaksi. Karena dedup pakai `content_hash` (hash tak berubah saat rename), file TIDAK di-embed ulang — pastikan watcher/startup-scan mencocokkan by-hash lalu update path, bukan menganggap file baru.
- [ ] **Keamanan:** rename **di tempat** (jangan pindah folder); tangani tabrakan nama (tambah suffix); tulis **log undo** (pemetaan nama lama → baru) ke file/registry.
- [ ] **Preview wajib:** endpoint `GET /rename/preview` menampilkan tabel **nama lama → nama baru** untuk semua/terpilih; `POST /rename/apply` baru mengeksekusi setelah dikonfirmasi; `POST /rename/undo` mengembalikan dari log.
- [ ] **Bonus integrasi:** pakai pipeline judul/penulis/tahun yang sama untuk memperbaiki kolom **Source** di matriks (Phase 12) — Crossref + LLM, konsisten dengan nama file.

**Acceptance:** preview menampilkan nama lama→baru yang rapi (tanpa regex); apply me-rename + update path registry tanpa memicu re-embed; undo berfungsi; karakter ilegal & tabrakan tertangani.

**Git:**
```bash
git add -A && git commit -m "Phase 14: rename PDFs by title (LLM+Crossref, no regex, registry-safe, preview+undo)"
```

---

## Selesai

Setelah Phase 14, tampilkan ringkasan + `git log --oneline`.
