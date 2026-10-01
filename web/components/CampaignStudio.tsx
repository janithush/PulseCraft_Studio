"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { createCampaign, getJob } from "../lib/api";

const PRESETS = ["alex-hormozi", "faceless-docu", "b-roll-centric", "kinetic-bold"];
const PLATFORMS = ["fb", "ig", "all"];

export default function CampaignStudio({ onDone }: { onDone: (jobId: string) => void }) {
  const [prompt, setPrompt] = useState("");
  const [brand, setBrand] = useState("acme");
  const [platform, setPlatform] = useState("all");
  const [preset, setPreset] = useState(PRESETS[0]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit() {
    setBusy(true);
    setError("");
    try {
      const { job_id } = await createCampaign("", {
        prompt,
        brand,
        formats: "png,reel",
        preset,
        platform,
        seed: 42,
      });
      let status = "queued";
      for (let i = 0; i < 120 && (status === "queued" || status === "running"); i++) {
        await new Promise((r) => setTimeout(r, 1000));
        const job = await getJob("", job_id);
        status = job.status;
        if (status === "failed") throw new Error(job.error ?? "job failed");
      }
      onDone(job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "campaign failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <motion.section
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
      className="glass rounded-3xl p-6 col-span-12 lg:col-span-7"
    >
      <h2 className="text-xl font-semibold text-white">Campaign Studio</h2>
      <textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="3 morning habits that burn fat…"
        rows={4}
        className="mt-4 w-full rounded-2xl bg-white/5 border border-white/10 p-4 text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-[#A3E635]"
      />
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <select
          value={brand}
          onChange={(e) => setBrand(e.target.value)}
          className="rounded-full bg-white/5 border border-white/10 px-4 py-2 text-sm"
        >
          <option value="acme">acme</option>
        </select>
        {PLATFORMS.map((p) => (
          <button
            key={p}
            onClick={() => setPlatform(p)}
            className={`rounded-full px-4 py-2 text-sm border transition ${
              platform === p
                ? "bg-[#A3E635] text-slate-950 border-transparent glow-neon"
                : "bg-white/5 border-white/10 text-slate-300"
            }`}
          >
            {p.toUpperCase()}
          </button>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {PRESETS.map((p) => (
          <button
            key={p}
            onClick={() => setPreset(p)}
            className={`rounded-full px-3 py-1 text-xs border ${
              preset === p ? "border-[#A3E635] text-[#A3E635]" : "border-white/10 text-slate-400"
            }`}
          >
            {p}
          </button>
        ))}
      </div>
      <button
        onClick={submit}
        disabled={busy || !prompt.trim()}
        className="mt-5 rounded-full bg-[#A3E635] px-6 py-2.5 text-sm font-semibold text-slate-950 disabled:opacity-40 glow-neon"
      >
        {busy ? "Rendering…" : "Generate campaign"}
      </button>
      {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
    </motion.section>
  );
}
