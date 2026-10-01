"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { createCampaign, getJob, listTemplates } from "../lib/api";

const PRESETS = ["alex-hormozi", "faceless-docu", "b-roll-centric", "kinetic-bold"];
const PLATFORMS = ["fb", "ig", "all"];

type TemplateEntry = { name: string; kind: string; manifest?: Record<string, unknown> };

function templateTitle(entry: TemplateEntry): string {
  const display = entry.manifest?.displayName;
  return typeof display === "string" && display ? display : entry.name;
}

export default function CampaignStudio({
  onDone,
  brand,
  prompt,
  onPromptChange,
}: {
  onDone: (jobId: string) => void;
  brand: string;
  prompt: string;
  onPromptChange: (next: string) => void;
}) {
  const [platform, setPlatform] = useState("all");
  const [preset, setPreset] = useState(PRESETS[0]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [templates, setTemplates] = useState<TemplateEntry[]>([]);
  const [templatesError, setTemplatesError] = useState("");

  useEffect(() => {
    if (!drawerOpen) return;
    listTemplates()
      .then((data) => {
        setTemplates((data.templates ?? []) as TemplateEntry[]);
        setTemplatesError("");
      })
      .catch((err) => setTemplatesError(err instanceof Error ? err.message : "templates failed"));
  }, [drawerOpen]);

  function useTemplate(entry: TemplateEntry) {
    // Strict append mode: new line, never overwrite (same contract as Inject).
    const line = `[Template: ${templateTitle(entry)} (${entry.name})]`;
    onPromptChange(prompt.trim() ? `${prompt}\n${line}` : line);
    setDrawerOpen(false);
  }

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

  const noBrand = !brand.trim();

  return (
    <motion.section
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
      className="glass rounded-3xl p-6 col-span-12 lg:col-span-7"
      data-testid="campaign-studio"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-white">Campaign Studio</h2>
        <button
          onClick={() => setDrawerOpen(true)}
          data-testid="template-library-btn"
          className="rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-xs text-slate-200 hover:border-[#A3E635] hover:text-[#A3E635]"
        >
          📂 Template Library
        </button>
      </div>
      <textarea
        value={prompt}
        onChange={(e) => onPromptChange(e.target.value)}
        placeholder="3 morning habits that burn fat…"
        rows={4}
        data-testid="campaign-prompt"
        className="mt-4 w-full rounded-2xl bg-white/5 border border-white/10 p-4 text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-[#A3E635]"
      />
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <span
          data-testid="campaign-brand"
          className="rounded-full bg-white/5 border border-white/10 px-4 py-2 text-sm text-slate-200"
        >
          {brand || "(No Brand Selected)"}
        </span>
        {PLATFORMS.map((p) => (
          <button
            key={p}
            onClick={() => setPlatform(p)}
            data-testid={`platform-${p}`}
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
      <div className="mt-3">
        <p className="text-xs text-slate-500">Style Preset (toggle — click again to deselect)</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {PRESETS.map((p) => (
            <button
              key={p}
              onClick={() => setPreset((prev) => (prev === p ? "" : p))}
              data-testid={`preset-${p}`}
              data-selected={preset === p}
              className={`rounded-full px-3 py-1 text-xs border ${
                preset === p ? "border-[#A3E635] text-[#A3E635]" : "border-white/10 text-slate-400"
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </div>
      <button
        onClick={submit}
        disabled={busy || !prompt.trim() || noBrand}
        title={noBrand ? "Please select or type a Brand" : undefined}
        data-testid="generate-btn"
        className="mt-5 rounded-full bg-[#A3E635] px-6 py-2.5 text-sm font-semibold text-slate-950 disabled:opacity-40 glow-neon"
      >
        {busy ? "Rendering…" : "Generate campaign"}
      </button>
      {error && <p className="mt-3 text-sm text-red-400">{error}</p>}

      {drawerOpen && (
        <div
          data-testid="template-drawer"
          className="fixed inset-y-0 right-0 z-50 w-full max-w-md overflow-auto bg-slate-950/95 p-6 shadow-2xl border-l border-white/10"
        >
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-white">📂 Template Library</h3>
            <button
              onClick={() => setDrawerOpen(false)}
              data-testid="template-drawer-close"
              aria-label="Close template library"
              className="rounded-full border border-white/20 px-3 py-1 text-sm text-white hover:bg-white/10"
            >
              X
            </button>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Loaded from <code>/api/templates</code> —{" "}
            <code>{"{id, title, category, description}"}</code> mapped from backend{" "}
            <code>{"{name, kind, manifest}"}</code>. Use appends on a new line.
          </p>
          {templatesError && <p className="mt-3 text-sm text-red-400">{templatesError}</p>}
          <div className="mt-4 space-y-3">
            {templates.map((entry) => {
              const title = templateTitle(entry);
              return (
                <div
                  key={entry.name}
                  data-testid={`template-card-${entry.name}`}
                  className="rounded-2xl border border-white/10 bg-white/5 p-4"
                >
                  <h4 className="text-sm font-medium text-slate-100">{title}</h4>
                  <p className="mt-1 text-xs text-slate-500">
                    category: {entry.kind} · id: {entry.name}
                  </p>
                  <button
                    onClick={() => useTemplate(entry)}
                    data-testid={`use-template-${entry.name}`}
                    className="mt-3 rounded-full bg-[#A3E635] px-4 py-1.5 text-xs font-semibold text-slate-950"
                  >
                    Use Template
                  </button>
                </div>
              );
            })}
            {templates.length === 0 && !templatesError && (
              <p className="text-sm text-slate-500">Loading templates…</p>
            )}
          </div>
        </div>
      )}
    </motion.section>
  );
}
