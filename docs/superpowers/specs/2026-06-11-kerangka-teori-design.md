# Kerangka Teori — Design Spec

> Tanggal: 2026-06-11. Fitur: generator **kerangka teori** (theoretical framework
> diagram) per naskah di UI naskah-centric. User tempel judul penelitian → sistem
> susun diagram kausal ter-ground (node + panah bertipe), render di browser, editable
> via teks, ekspor PNG.

## 1. Tujuan & Lingkup

**Tujuan:** Dari judul penelitian (mis. "Pengaruh A, B, C Terhadap D pada populasi P"),
hasilkan diagram kerangka teori bergaya skripsi: variabel diteliti (kotak tebal) pada
jalur utama, faktor latar (kotak putus-putus) di pinggir, panah **memicu** (merah) /
**menghambat** (biru), tiap node punya sumber yang bisa dilacak.

**Dalam lingkup:**
- Parse judul → draft variabel bebas/terikat, dikonfirmasi user.
- Generator ter-ground: node korpus disitasi ke `doc_id+halaman`; node eksternal
  diverifikasi Crossref, ditandai "perlu verifikasi".
- Representasi DSL teks (sumber kebenaran, editable) → DOT → SVG (viz.js / Graphviz WASM).
- Tab "Kerangka" ke-5 di Ruang Kerja. Ekspor PNG. Persist satu kerangka per naskah.

**Di luar lingkup (YAGNI):** kanvas drag-drop interaktif; multi-kerangka per naskah;
ekspor SVG/PDF (hanya PNG); kolaborasi; auto-regenerate saat paper berubah.

**Prinsip inti (wajib, warisi dari proyek):** tidak LLM-driven. Tiap node/edge punya
sumber. Node korpus tanpa `doc_id` pendukung **ditolak** saat assembly. Sitasi eksternal
**tidak pernah** dari ingatan LLM — selalu lewat Crossref.

## 2. Arsitektur

| Unit | Jenis | Tanggung jawab | Acuan pola |
|---|---|---|---|
| `app/rag/framework.py` | Python, baru | Generator: parse judul, retrieve korpus, susun graph ter-ground, verifikasi eksternal, rakit DSL+citations, persist. `chat`/`search`/`crossref` di-inject. | `app/rag/matrix.py` |
| `app/ingest/title.py` | Python, modifikasi | `crossref_lookup()` ditambah field `doi` + `url` (additive, tak ubah pemanggil lama). | — |
| `app/core/db.py` | Python, modifikasi | Tambah tabel `project_framework` ke `SCHEMA`. | tabel `project_matrix` |
| `app/web/projects_routes.py` | Python, modifikasi | 3 endpoint baru (parse-title, build, get). | endpoint `/matrix` |
| `app/web/static/new/dsl.js` | JS murni, baru | Compiler `parseDSL()` + `dslToDot()`. Unit-tested. | `citations.js` |
| `app/web/static/new/framework.js` | JS DOM, baru | Tab view: input judul → konfirmasi → render SVG → edit DSL → panel sumber → ekspor PNG. Verifikasi manual. | `papers.js` |
| `app/web/static/new/workspace.js` | JS DOM, modifikasi | Tambah tab ke-5 "Kerangka", mount `framework.js`. | tab Matriks |
| `app/web/templates/new.html` | modifikasi | Tambah `<script>` viz.js (Graphviz WASM) dari CDN. | markmap script |

**Tidak menyentuh:** UI legacy `/tools`, retriever, generator core, ingest pipeline.

## 3. Model Data

### 3.1 Tabel `project_framework` (tambah ke `SCHEMA` di `app/core/db.py`)

```sql
CREATE TABLE IF NOT EXISTS project_framework (
  project_id  INTEGER PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
  title       TEXT NOT NULL DEFAULT '',
  dsl         TEXT NOT NULL DEFAULT '',
  citations   TEXT NOT NULL DEFAULT '{}',   -- JSON, lihat 3.3
  variables   TEXT NOT NULL DEFAULT '{}',   -- JSON {bebas:[],terikat:"",populasi:""}
  updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
```

Satu kerangka per naskah. PK `project_id` → upsert via `INSERT ... ON CONFLICT(project_id)
DO UPDATE`. `ON DELETE CASCADE`: hapus naskah → kerangka ikut terhapus (butuh
`PRAGMA foreign_keys=ON`, sudah aktif di `connect()`).

### 3.2 DSL — sumber kebenaran (grammar EBNF)

DSL adalah teks baris-per-baris. Compiler **toleran**: baris kosong & komentar (`#` di
awal setelah trim) diabaikan; whitespace di-trim; label case-sensitive setelah trim.

```ebnf
program     = { line } ;
line        = node_decl | edge_decl | comment | empty ;
comment     = "#" , { any } ;
node_decl   = "[" , kind , "]" , ws , label , [ annotation ] ;
kind        = "diteliti" | "latar" | "latar*" ;
edge_decl   = label , ws , arrow , ws , label , [ ":" , ws , reltype ] ;
arrow       = "->" | "-|" ;
reltype     = "memicu" | "menghambat" ;
annotation  = ws , "@src:" , ( "korpus" | "eksternal" ) ;   (* opsional, jarang ditulis manual *)
label       = { any char kecuali "[" "]" newline ":" dan token panah } , trimmed ;
ws          = { " " | "\t" } ;
```

**Aturan resolusi tipe edge (deterministik, hilangkan ambiguitas):**
- `-|`  → `menghambat` (apa pun suffix `:`).
- `->`  + `: menghambat` → `menghambat`.
- `->`  tanpa `:` atau `: memicu` → `memicu` (default).
- `-|` + `: memicu` → **error parse** (kontradiksi), pesan baris.

**Aturan node implisit:** label yang muncul di `edge_decl` tapi tak punya `node_decl`
→ dibuat otomatis sebagai `[latar]` (longgar, supaya edit cepat tak putus). Diberi
flag `implicit:true` agar UI bisa ingatkan.

**Contoh DSL kanonik:**
```
# Kerangka: Pengaruh dosis norepinefrin, gula darah, balans cairan terhadap syndecan-1
[diteliti] Dosis norepinefrin
[diteliti] Gula darah sewaktu
[diteliti] Balans cairan rerata
[diteliti] ↑ syndecan-1
[latar*]   Kerusakan glikokaliks
[latar*]   ↑ ROS
[latar]    Sepsis
[latar]    Albumin
[latar]    ↑ permeabilitas kapiler
[latar]    Mortalitas

Dosis norepinefrin -> Kerusakan glikokaliks : memicu
Gula darah sewaktu -> ↑ ROS : memicu
Balans cairan rerata -> Kerusakan glikokaliks : memicu
Sepsis -> ↑ ROS : memicu
Albumin -| Kerusakan glikokaliks : menghambat
↑ ROS -> Kerusakan glikokaliks : memicu
Kerusakan glikokaliks -> ↑ syndecan-1 : memicu
↑ syndecan-1 -> ↑ permeabilitas kapiler : memicu
↑ permeabilitas kapiler -> Mortalitas : memicu
```

### 3.3 Citations map (kolom `citations`, JSON)

Keyed by **label node** (string identik dengan DSL). Edit DSL tak hapus map; saat render
dicocokkan per label, label tanpa entry = tanpa badge.

```json
{
  "Kerusakan glikokaliks": {
    "src": "korpus", "doc_id": 12, "page": 7,
    "title": "Glycocalyx degradation in sepsis", "quote": "…span pendukung…"
  },
  "↑ ROS": {
    "src": "eksternal", "status": "perlu_verifikasi",
    "ref": {"title": "The endothelial glycocalyx", "authors": ["Chappell D"], "year": 2008,
            "doi": "10.xxxx/xxxx", "url": "https://doi.org/10.xxxx/xxxx"}
  },
  "Albumin": {
    "src": "eksternal", "status": "tak_terverifikasi", "ref": null
  }
}
```

`status` ∈ {`perlu_verifikasi` (ada hit Crossref, user belum setuju), `tak_terverifikasi`
(tak ada hit), `terverifikasi` (user setuju — *opsional fase lanjut*, MVP cukup dua status
pertama)}. `src` korpus tidak punya `status` (otomatis terverifikasi).

## 4. Generator `framework.py`

Semua dependency injectable agar testable tanpa model/jaringan: `chat_fn=chat`,
`search_fn=search`, `crossref_fn=crossref_lookup`.

### 4.1 Fungsi publik

```python
def parse_title(title: str, chat_fn=chat) -> dict
# -> {"bebas": [str], "terikat": str, "populasi": str}

def build_framework(conn, project_id: int, variables: dict,
                    chat_fn=chat, search_fn=search, crossref_fn=crossref_lookup) -> dict
# -> {"dsl": str, "citations": dict, "variables": dict}  (juga persist)

def load_framework(conn, project_id: int) -> dict | None
# -> {"dsl","citations","variables","title","updated_at"} atau None
```

### 4.2 Algoritma `build_framework` (deterministik tahap demi tahap)

1. **doc_ids** = `project_doc_ids(conn, project_id)`. Jika kosong → raise `ValueError("naskah tanpa paper")` (endpoint → 400).
2. **Node diteliti**: tiap `variables["bebas"]` + `variables["terikat"]` → node `[diteliti]`.
3. **Jalur mekanistik (backbone)**: untuk tiap bebas→terikat, `search_fn(query, top_k=6,
   filters={"doc_ids": doc_ids}, conn=conn)`. Kirim KONTEKS ke `chat_fn` dengan system-prompt
   ketat: "susun rantai node antara X dan Y HANYA dari KONTEKS; tiap node sertakan kutipan
   + indeks sumber". Output JSON: `[{label, relasi, dari, ke, src_idx}]`. Node backbone yang
   punya dukungan KONTEKS → `[latar*]` (mediator) + entry citations `src:korpus`
   (doc_id+page dari Hit `src_idx`).
4. **Node latar eksternal**: LLM boleh usulkan faktor latar yang TIDAK ada di korpus
   (prompt terpisah, JSON `[{label, relasi, target}]`). Untuk tiap usulan:
   `crossref_fn(label_klaim)`:
   - hit → `status:perlu_verifikasi`, simpan `ref` (title/authors/year/doi/url).
   - tak hit → `status:tak_terverifikasi`, `ref:null`. **Tetap dibuat** (badge merah),
     tidak di-drop diam-diam.
   Semua → node `[latar]`.
5. **Guard anti-halusinasi**: node yang diklaim `src:korpus` tapi `src_idx` di luar rentang
   Hit, atau tanpa doc_id/page → **node ditolak** (di-skip + di-log), tidak masuk DSL.
   (Pola sama dengan GAP di matrix.)
6. **Edge**: kumpulkan dari langkah 3 & 4. Tipe `memicu`/`menghambat` dari field `relasi`
   (LLM, harus dari kalimat konteks untuk edge korpus). Edge ke/dari label yang nodenya
   ditolak (5) → ikut dibuang.
7. **Rakit DSL** (urutan: deklarasi node diteliti → latar* → latar, lalu edge) + **citations**.
8. **Persist** upsert ke `project_framework`. Return `{dsl, citations, variables}`.

### 4.3 Prompt (disimpan sbg konstanta modul, Bahasa Indonesia)

- `PARSE_TITLE_SYS`: "Ekstrak variabel bebas (daftar), terikat (satu), populasi dari judul.
  Kembalikan HANYA JSON `{bebas:[],terikat:'',populasi:''}`. Jangan karang."
- `BACKBONE_SYS`: "Susun rantai mekanistik antar variabel HANYA dari KONTEKS. Tiap node:
  label ringkas, relasi (memicu|menghambat), dari, ke, src_idx (indeks sumber konteks).
  JSON array. Jangan pakai pengetahuan luar. Jika konteks tak cukup, kembalikan []."
- `EXTERNAL_SYS`: "Usulkan faktor latar relevan yang TIDAK ada di konteks (pengetahuan
  domain). Tiap usulan: label, relasi, target (label tujuan). JSON array. Ini akan
  diverifikasi eksternal — jangan mengarang referensi."

Parsing JSON: `json.loads` setelah strip code-fence (pola `matrix.py`), gagal → `[]` (fail-safe).

## 5. Endpoint (`projects_routes.py`)

### 5.1 `POST /projects/{project_id}/framework/parse-title`
Req: `{"title": str}` → Res `200`: `{"variables": {"bebas":[],"terikat":"","populasi":""}}`.
`title` kosong → `422`.

### 5.2 `POST /projects/{project_id}/framework`
Req: `{"variables": {"bebas":[str],"terikat":str,"populasi":str}, "title": str}` →
Res `200`: `{"dsl": str, "citations": {}, "variables": {}}`.
Naskah tanpa paper → `400 {"detail":"naskah tanpa paper"}`. Proyek tak ada → `404`.

### 5.3 `GET /projects/{project_id}/framework`
Res `200`: `{"dsl","citations","variables","title","updated_at"}` atau, bila belum ada,
`{"dsl":"","citations":{},"variables":{},"title":"","updated_at":null}` (bukan 404 —
front-end render kosong).

Semua endpoint buka/tutup `conn` via `connect()` dalam `try/finally` (pola berkas).

## 6. Front-end

### 6.1 `dsl.js` (murni, unit-tested)

```js
export function parseDSL(text)
// -> { nodes: [{label, kind, implicit}], edges: [{from,to,type}], errors: [{line,col,msg}] }
export function dslToDot(parsed, citations)
// -> string DOT. Menyisipkan style node/edge + atribut id utk badge hookup.
```

**Pemetaan `dslToDot` (eksak):**
- Graph: `digraph G { rankdir=TB; node [shape=box, fontname="Inter"]; }`
- `[diteliti]` → `"label" [penwidth=2.5, style=solid];`
- `[latar]`   → `"label" [style=dashed, color="#999", fontcolor="#555"];`
- `[latar*]`  → `"label" [style=dashed, color="#999", fontcolor="#555"];` + ditempatkan
  pada rank backbone (lihat bawah).
- edge `memicu`    → `"a" -> "b" [color="#c0392b"];`
- edge `menghambat`→ `"a" -> "b" [color="#2c5fa8", arrowhead=diamond];`
- **Backbone rank**: node `diteliti` + `latar*` dikelompokkan; compiler emit
  `{rank=same; ...}` per level topologis sederhana (urut kemunculan jalur), `[latar]`
  dibiarkan free (Graphviz dorong ke pinggir secara alami). Label di-escape (`"` → `\"`).
- Badge: tiap node emit `id="node-<slug(label)>"`; `framework.js` overlay ikon 📄/🌐
  setelah SVG jadi, berdasar citations map.

### 6.2 `framework.js` (DOM, manual-verify)

State & alur (lihat mockup §UI di brainstorm). Fungsi `mountFramework(panel, pid, deps)`:
- Saat mount → `GET .../framework`; bila `dsl` non-kosong → render + isi textarea.
- "Parse judul" → `POST .../parse-title` → render draft checklist variabel bebas (checkbox)
  + input terikat + populasi.
- "Bangun kerangka" → `POST .../framework` → set DSL, render, isi panel sumber.
- Textarea DSL → "Render ulang" (debounce 400ms): `parseDSL` → bila `errors` → tampilkan
  daftar error (baris,kolom,pesan), **pertahankan SVG terakhir**; bila bersih →
  `dslToDot` → `viz.render` → swap SVG, overlay badge.
- Badge 📄 klik → buka PDF di halaman (viewer Phase 5, pola `citations.js`/`papers.js`).
  Badge 🌐 hover → tooltip `ref` (title, authors, year, link DOI).
- "⬇ PNG": serialize SVG → `<canvas>` → `toBlob('image/png')` → download
  (`kerangka-<pid>.png`). "Salin DSL": clipboard.
- Error jaringan → `friendlyError` (sudah ada).

### 6.3 viz.js (Graphviz WASM)

Tambah ke `new.html` (pola markmap, CDN, tanpa build). Loader async; bila `window.Viz`
belum siap saat render → tampilkan "menyiapkan mesin diagram…", retry sekali.

## 7. Penanganan Error (perilaku eksplisit)

| Kondisi | Perilaku |
|---|---|
| `title` kosong di parse-title | `422`; UI: tombol disabled sampai ada teks. |
| Naskah tanpa paper saat build | `400 "naskah tanpa paper"`; UI: "Tambah paper dulu di tab Paper." |
| LLM balikan JSON rusak | generator fail-safe `[]`; bila backbone & eksternal sama-sama `[]` → DSL hanya node diteliti tanpa edge + banner "Korpus tak cukup untuk menyusun jalur — tambah paper atau edit manual." |
| Crossref timeout/offline | node eksternal `status:tak_terverifikasi`, badge merah; build tetap sukses. |
| Embedding/LLM down | endpoint 503 → `friendlyError` ("Mesin penjawab sedang tidak aktif…"). |
| DSL parse error saat edit | daftar error di bawah textarea; SVG lama dipertahankan; tak overwrite simpanan. |
| viz.js gagal muat (offline pertama) | "render diagram perlu koneksi pertama kali"; DSL+panel sumber tetap jalan. |
| Label duplikat di DSL | node digabung (label = identitas); peringatan non-blocking. |
| Edge `-\| : memicu` (kontradiksi) | error parse baris. |
| PNG pada SVG kosong | tombol disabled saat belum ada render. |

## 8. Potensi Bug & Risiko (diketahui di muka)

1. **Label sebagai primary key rapuh.** Citations & edge dicocokkan by exact label string.
   Edit label di DSL → badge node itu hilang (jadi node baru). *Mitigasi:* UI ingatkan
   "node tanpa sumber" saat label diedit; ini perilaku diterima untuk MVP (edit-teks-source).
2. **viz.js mismatch label↔id.** `slug(label)` untuk `id` SVG harus konsisten antara
   `dslToDot` dan overlay badge. Label non-ASCII (↑, spasi) → slug harus deterministik &
   reversible-cukup. *Mitigasi:* satu fungsi `slug()` dipakai dua tempat, unit-test
   round-trip; simpan map `id→label` saat emit, jangan re-slug.
3. **Graphviz layout sprawl.** Banyak `[latar]` → diagram melebar, gutter tak rapi seperti
   mockup (Graphviz tak punya konsep "gutter" eksplisit). *Mitigasi:* batasi default
   ≤6 node latar; `rank=same` untuk backbone; bila jelek, user atur via edit DSL. Risiko
   sisa: hasil bisa kurang cantik dari mockup tangan. **Tidak dijamin identik.**
4. **Halusinasi src_idx.** LLM bisa kasih `src_idx` valid tapi kutipan tak benar-benar
   mendukung node. Guard §4.2.5 cek rentang & keberadaan, **tidak** memverifikasi makna
   kutipan. *Risiko sisa:* node korpus bisa "ter-ground ke halaman yang salah". Mitigasi
   parsial: simpan `quote` agar user bisa cek; verifikasi makna = fitur lanjut (lihat
   roadmap "Audit Klaim").
5. **Crossref false-positive.** `query.bibliographic` ambil hasil teratas; bisa cocok ke
   paper keliru → `ref` menyesatkan tapi ber-status `perlu_verifikasi`. *Mitigasi:* badge
   kuning eksplisit + user wajib cek; jangan auto-`terverifikasi`.
6. **Race simpan vs render ulang.** Build async + user cepat edit textarea. *Mitigasi:*
   build set DSL lalu render; edit lokal tak auto-persist (hanya tombol simpan/build
   menulis DB) — hindari overwrite. **Keputusan MVP:** edit DSL lokal TIDAK auto-save;
   hanya "Bangun kerangka" yang persist. (Bila ingin simpan editan manual → fase lanjut
   tambah tombol "Simpan DSL".)
7. **CASCADE delete.** Butuh `foreign_keys=ON`; bila koneksi lain lupa pragma, baris yatim.
   *Mitigasi:* `connect()` sudah set pragma; tes hapus-proyek cek kerangka ikut hilang.
8. **PNG dari SVG dengan font eksternal.** Inter via CDN; saat rasterisasi canvas, font
   mungkin belum ter-load → PNG pakai fallback font. *Mitigasi:* `document.fonts.ready`
   sebelum `toBlob`; terima fallback bila offline.
9. **DSL injection ke DOT.** Label berisi `"` / `}` bisa rusak DOT. *Mitigasi:* `dslToDot`
   escape `"` dan buang newline; unit-test label nakal.

## 9. Testing

**`tests/test_framework.py` (pytest):**
- `parse_title` → JSON benar (chat stub).
- `build_framework`: node korpus dapat doc_id+page (search stub); node tanpa src_idx valid
  ditolak; eksternal lewat crossref stub (hit→perlu_verifikasi, miss→tak_terverifikasi).
- Guard: chat balikan node korpus src_idx out-of-range → node & edge terkaitnya dibuang.
- Naskah tanpa paper → `ValueError`.
- Persist+load round-trip; upsert (build dua kali → satu baris).
- Hapus proyek → `load_framework` None (CASCADE).
- Endpoint: parse-title 422 kosong; build 400 tanpa paper; get kosong (bukan 404).

**`tests/js/dsl.test.mjs` (node:test):**
- `parseDSL`: node 3 kind, edge `->`/`-|`, default memicu, `-| :memicu` error, komentar/
  kosong diabaikan, node implisit dari edge, label duplikat, error baris+kolom.
- `dslToDot`: style diteliti/latar/latar*, warna edge, arrowhead diamond, escaping `"`,
  `slug()` round-trip & dipakai konsisten.

**Manual:** `framework.js` (render SVG, badge klik→PDF, edit→re-render, PNG, error states).

## 10. Komit (saran granular)

1. db: tabel `project_framework`.
2. `title.py`: crossref_lookup + doi/url.
3. `framework.py` generator + `test_framework.py`.
4. endpoint parse-title/build/get (+tes endpoint).
5. `dsl.js` + `dsl.test.mjs`.
6. viz.js di new.html + `framework.js` + tab ke-5 di workspace.js.
7. CSS badge/tab + dokumen CLAUDE.md (bagian Web + Projects).

## 11. Acceptance

- Tempel judul sepsis → konfirmasi 4 variabel → "Bangun kerangka" → diagram berlapis
  muncul: variabel diteliti kotak tebal di backbone, latar putus-putus di pinggir, panah
  merah/biru, badge 📄 (klik→halaman PDF) & 🌐 kuning (hover→referensi Crossref).
- Edit DSL (tambah node/edge) → "Render ulang" → diagram berubah; error DSL tampil tanpa
  merusak tampilan.
- Ekspor PNG menghasilkan gambar siap tempel ke skripsi.
- Node tanpa dukungan korpus & tanpa hit Crossref → badge merah "sumber tak ditemukan",
  bukan diam-diam dibuang.
- `/tools` & fitur lain tak berubah; full suite hijau.
