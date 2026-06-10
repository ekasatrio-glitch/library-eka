// PDF upload + ingest-job polling. Pure logic injectable for node:test;
// postFile is the FormData counterpart of api.js postJSON.
import { getJSON } from "./api.js";

export const STAGE_LABELS = {
  antri: "menunggu giliran…",
  membaca: "membaca halaman…",
  mengindeks: "mengindeks…",
  selesai: "selesai",
};

export async function postFile(url, file) {
  const fd = new FormData();
  fd.append("file", file, file.name);
  const r = await fetch(url, { method: "POST", body: fd });
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

export async function pollJob(jobId, onTick, { delayMs = 1000, fetchJson = getJSON } = {}) {
  for (;;) {
    const job = await fetchJson(`/uploads/${jobId}`);
    onTick(job);
    if (job.finished) return job;
    await new Promise(res => setTimeout(res, delayMs));
  }
}
