# library-eka — Update: Ganti Extractor ke Docling

> Mengganti extractor PyMuPDF (Phase 2) dengan **Docling** untuk kualitas ekstraksi paper akademik: urutan baca multi-kolom benar, tabel terstruktur, OCR untuk PDF scan. **Embedding tetap nomic** (tidak ganti bge-m3). **Surface perubahan dijaga minimal:** hanya modul extractor + satu kali re-ingest. Sisanya (sqlite-vec, registry, chunker, retrieval, proyek, matriks) TIDAK diubah.

---

## Cara Menjalankan

```bash
cd library-eka
claude --dangerously-skip-permissions
```
Lalu paste KICKOFF PROMPT.

### KICKOFF PROMPT (paste apa adanya)

```
Baca file library-eka-UPDATE-docling.md. Ini UPGRADE atas pipeline yang SUDAH ada — mengganti extractor PyMuPDF dengan Docling. JANGAN bangun ulang. Pelajari dulu extractor & pipeline ingestion yang ada, lalu ganti HANYA bagian ekstraksi; pertahankan interface output extractor supaya chunker/embedder/registry tidak perlu diubah.

Kerjakan sub-phase D1 lalu D2 berurutan.

ATURAN:
- Gunakan skill Superpowers.
- Autonomous penuh, JANGAN minta konfirmasi apa pun.
- Embedding TETAP nomic (jangan ganti bge-m3).
- Pertahankan pelacakan nomor halaman per chunk (untuk sitasi klik-ke-halaman).
- Commit tiap sub-phase (perintah tertera).
- Jika perintah gagal, perbaiki sendiri dan lanjut.
- Di akhir tampilkan ringkasan + `git log --oneline`.

Mulai dari sub-phase D1.
```

---

## Sub-phase D1 — Extractor Docling

**Tujuan:** ganti ekstraksi PyMuPDF dengan Docling, output mengikuti interface extractor lama.

**Tugas:**
- [ ] Tambah dependency: `pip install docling`. Catatan: run pertama mengunduh model layout/tabel (ratusan MB); jalankan sekali untuk warm-up.
- [ ] Pelajari signature extractor lama (mis. `app/ingest/extractor.py`) — apa bentuk output yang dipakai chunker (kemungkinan list `(page_no, text)`). **Pertahankan bentuk itu.**
- [ ] Implementasi extractor baru pakai `DocumentConverter` Docling:
  - Konversi PDF → `DoclingDocument`.
  - **Urutan baca:** ambil elemen dalam reading order yang sudah benar (atasi masalah dua-kolom).
  - **Halaman:** tiap elemen punya provenance halaman (`prov[].page_no`, 1-indexed) — gunakan untuk mengelompokkan teks **per halaman** agar chunker tetap bisa mengisi `page_start/page_end`.
  - **Tabel:** ekspor tiap tabel sebagai **markdown**, sisipkan pada posisinya di teks halaman, supaya isi tabel ikut ter-index & bisa mengisi field kuantitatif matriks. Tandai halamannya.
  - **OCR:** aktifkan opsi OCR Docling (`do_ocr=True`) sebagai fallback untuk PDF hasil scan. Boleh dibuat toggle di `.env` (`OCR=true|false`) karena memperlambat.
- [ ] Pastikan output extractor identik bentuknya dengan yang lama, sehingga chunker/embedder/registry/FTS5 tidak berubah.

**Acceptance:** paper dua-kolom diekstrak dengan urutan baca benar (tidak tercampur antar kolom); tabel muncul sebagai markdown dengan nomor halaman tepat; PDF scan (bila OCR on) menghasilkan teks; nomor halaman per chunk tetap akurat.

**Git:**
```bash
git add -A && git commit -m "Phase D1: replace PyMuPDF extractor with Docling (reading order, tables as markdown, OCR, page tracking preserved)"
```

---

## Sub-phase D2 — Re-ingest Migration (sekali jalan)

**Tujuan:** ekstrak ulang korpus lama dengan Docling (karena teks/chunk berubah), embedding model tetap nomic.

**Tugas:**
- [ ] Perintah migrasi `reingest --all` (CLI atau endpoint):
  - Untuk tiap dokumen di registry: **paksa re-extract** dengan Docling (lewati skip-by-hash khusus untuk migrasi ini), hapus chunk + vektor + entri FTS5 lama dokumen itu, lalu re-chunk → re-embed (model **nomic**, dim 768 tetap) → repopulate vec + FTS5.
  - Pertahankan baris `documents` (path, hash, metadata) — hanya chunk/vektor yang dibangun ulang.
  - Tampilkan progres.
  - Tandai flag migrasi agar idempotent (tidak mengulang tanpa sengaja).
- [ ] Jika korpus **belum** pernah di-ingest, langkah ini no-op — ingestion berikutnya otomatis pakai Docling.
- [ ] Catatan: ingestion Docling lebih lambat per halaman (model deep-learning). Ini biaya **sekali**, offline; tidak memengaruhi kecepatan query.

**Acceptance:** seluruh dokumen lama ter-ekstrak ulang via Docling; jumlah chunk & FTS5 konsisten; retrieval + sitasi klik-ke-halaman tetap berfungsi; flag migrasi mencegah pengulangan.

**Git:**
```bash
git add -A && git commit -m "Phase D2: one-time re-ingest migration to Docling extraction (nomic embeddings retained)"
```

---

## Verifikasi Akhir

- [ ] Uji 1 paper dua-kolom: urutan baca benar.
- [ ] Uji 1 paper dengan tabel: tabel muncul sebagai markdown + halaman tepat.
- [ ] (Jika ada) uji 1 PDF scan dengan OCR on: teks terekstrak.
- [ ] Klik sitasi → PDF terbuka di halaman benar.
- [ ] Tampilkan ringkasan + `git log --oneline`.
