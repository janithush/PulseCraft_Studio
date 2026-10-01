"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { galleryKind, getJob, renderResource } from "../lib/api";
import type { GalleryItem } from "./InteractivePreviewGallery";

const POST_BLUEPRINT = {
  version: "blueprint/v1",
  type: "static-post",
  brand: "acme",
  seed: 42,
  layout: "bold-hook-split",
  canvas: ["1080x1080", "1080x1350"],
  copy: { hook: "3 Morning Habits That Burn Fat", sub: "No gym. No crash diet.", cta: "Save + Follow" },
  assets: { query: "healthy breakfast bright", provider: "pexels", count: 3 },
};

const REEL_BLUEPRINT = {
  version: "blueprint/v1",
  type: "reel",
  brand: "acme",
  seed: 42,
  layout: "kinetic-bold",
  durationTargetSec: 30,
  hook: "Stop skipping breakfast",
  script: [{ id: "s1", voText: "Stop skipping breakfast.", captionBudget: 4 }],
  scenes: [{ id: "scene-1", scriptRef: "s1", assetQuery: "oatmeal bowl bright", kind: "image", durationSec: 4 }],
};

export default function ResourcePlayground({
  brand,
  onResult,
}: {
  brand: string;
  onResult: (items: GalleryItem[]) => void;
}) {
  const [kind, setKind] = useState<"render-post" | "render-reel">("render-post");
  const [text, setText] = useState(JSON.stringify(POST_BLUEPRINT, null, 2));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function switchKind(next: "render-post" | "render-reel") {
    setKind(next);
    setText(JSON.stringify(next === "render-post" ? POST_BLUEPRINT : REEL_BLUEPRINT, null, 2));
  }

  async function submit() {
    setBusy(true);
    setError("");
    try {
      const blueprint = JSON.parse(text) as Record<string, unknown>;
      const { job_id } = await renderResource("", {
        kind,
        blueprint,
        brand,
        preset: "alex-hormozi",
        platform: "all",
      });
      let status = "queued";
      let result: { artifact_urls?: Record<string, string>; warnings?: string[] } = {};
      for (let i = 0; i < 120 && (status === "queued" || status === "running"); i++) {
        await new Promise((r) => setTimeout(r, 1000));
        const job = await getJob("", job_id);
        status = job.status;
        if (status === "failed") throw new Error(job.error ?? "render failed");
        if (status === "done") result = (job.result ?? {}) as typeof result;
      }
      const items: GalleryItem[] = Object.entries(result.artifact_urls ?? {})
        .map(([key, url]) => {
          const media = galleryKind(url);
          return media ? { src: url, kind: media, label: `${job_id} · ${key}` } : null;
        })
        .filter((item): item is GalleryItem => item !== null);
      onResult(items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "render failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <motion.section
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
      className="glass rounded-3xl p-6 col-span-12 lg:col-span-6"
    >
      <h2 className="text-xl font-semibold text-white">Resource Playground</h2>
      <div className="mt-3 flex gap-2">
        {(["render-post", "render-reel"] as const).map((k) => (
          <button
            key={k}
            onClick={() => switchKind(k)}
            className={`rounded-full px-4 py-1.5 text-sm border ${
              kind === k
                ? "bg-[#A3E635] text-slate-950 border-transparent glow-neon"
                : "bg-white/5 border-white/10 text-slate-300"
            }`}
          >
            {k}
          </button>
        ))}
      </div>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={10}
        spellCheck={false}
        className="mt-3 w-full rounded-2xl bg-black/40 border border-white/10 p-4 font-mono text-xs text-slate-200"
      />
      <button
        onClick={submit}
        disabled={busy}
        className="mt-3 rounded-full bg-[#A3E635] px-5 py-2 text-sm font-semibold text-slate-950 disabled:opacity-40"
      >
        {busy ? "Rendering…" : "Render single resource"}
      </button>
      {error && <p className="mt-2 text-sm text-red-400">{error}</p>}
    </motion.section>
  );
}
