# Roadmap Pengembangan — Ide Fitur Baru

> Dicatat 2026-06-10, hasil riset lanskap tool serupa di GitHub.
> Konteks: chat-PDF RAG dan rangkum-paper sudah komoditas (PaperQA2, ScholarLens,
> PapersGPT/Zotero, dll). Pembeda library-eka adalah **grounding ketat** — gap
> ditulis eksplisit, sitasi ke halaman nyata, analisis tetap milik pengguna.
> Pengembangan baru harus memperdalam itu, bukan menambah fitur generik.

---

## 1. Audit Klaim Draft — "Mode Sidang" (prioritas tertinggi)

**Arah kebalikan dari semua tool yang ada:** bukan AI menulis draft, tapi pengguna
menempelkan draft BAB 2 yang SUDAH ditulis, lalu sistem memverifikasinya.

- Pecah draft menjadi klaim-klaim.
- Tiap klaim dicek ke korpus: didukung paper mana + halaman berapa?
- Klaim tanpa dukungan → ditandai merah.
- Sitasi "salah arah" (paper dikutip tapi tidak menyatakan hal itu) → ditandai.
- **Ekspor "lampiran bukti" untuk sidang:** tiap kalimat → span sumber yang bisa
  diklik ke halaman PDF.

**Kenapa baru:** riset terbaru (CiteAudit, arXiv 2602.23452) baru berupa benchmark;
belum ada tool lokal personal yang melakukan verifikasi klaim-ke-korpus. Halusinasi
sitasi adalah masalah 110.000+ publikasi — verifikatornya nyaris kosong.

**Kenapa cocok:** pipeline sudah punya semua bahan — retriever hybrid, `citation.py`,
click-to-page. Filosofinya konsisten dengan prinsip inti: mesin memverifikasi,
analisis milik pengguna. Komponen ±80% sudah terbangun.

## 2. Peta Konsensus–Kontradiksi

Matriks sintesis sudah mengekstrak temuan per paper. Langkah berikutnya:
bandingkan antar-baris matriks.

- Contoh keluaran: "Paper A: intervensi X menurunkan stunting (p<0.05, hal 7);
  Paper B: tidak signifikan (hal 12)."
- Peta konsensus vs konflik per variabel/outcome, semua dengan sitasi halaman.

**Kenapa baru:** ContraCrow (dibangun di atas PaperQA2) membuktikan konsep di level
riset, tapi tidak ada implementasi lokal yang grounded ke korpus pribadi.

**Kenapa murah:** datanya sudah ada di tabel matriks proyek.

## 3. Gap Finder Grounded

Dari data matriks: bangun grid **variabel × populasi × desain studi**.

- Sel kosong = gap riset NYATA dengan bukti: "tidak ada paper di korpusmu yang
  menguji X pada populasi Y" — bukan LLM mengarang "future research".
- Output: generator BAB 1 (latar belakang + rumusan masalah) yang bisa
  dipertanggungjawabkan.

## 4. Living Review

Watcher folder lokal sudah ada; tambah watcher eksternal.

- Polling Crossref / Semantic Scholar API untuk topik tiap naskah.
- Paper baru relevan → notifikasi via bot Telegram (Hermes — sudah ada).
- Sekali klik: masuk korpus + baris matriks baru.
- Tampilkan diff: "apa yang berubah sejak draft terakhir".

---

## Urutan saran

| # | Fitur | Nilai pembeda | Biaya bangun |
|---|-------|---------------|--------------|
| 1 | Audit Klaim Draft | Sangat tinggi — belum ada yang punya | Sedang (komponen 80% ada) |
| 2 | Konsensus–Kontradiksi | Tinggi | Rendah (data matriks sudah ada) |
| 3 | Gap Finder | Tinggi | Rendah (turunan matriks) |
| 4 | Living Review | Sedang | Sedang (API eksternal + bot) |

Mulai dari #1.

## Referensi

- PaperQA2 / ContraCrow: https://arxiv.org/pdf/2409.13740
- CiteAudit (benchmark verifikasi sitasi): https://arxiv.org/pdf/2602.23452
- PapersGPT for Zotero: https://github.com/papersgpt/papersgpt-for-zotero
- Zotero-Exitem: https://github.com/alansirius/Zotero-Exitem
- awesome-ai-research-tools: https://github.com/0x11c11e/awesome-ai-research-tools
- Analisis halusinasi sitasi: https://developmentcorporate.com/corporate-development/ai-hallucinated-citations-are-a-110000-publication-problem-and-a-hidden-ma-due-diligence-gap/
- GPTZero hallucination detector: https://gptzero.me/hallucination-detector
