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

const RESOURCE_BADGES = ["Hooks/Headlines", "Viral Captions", "SEO Hashtags", "Visual/Reel Prompts"];

export default function ResourcePlayground({
  brand,
  onResult,
  onInject,
}: {
  brand: string;
  onResult: (items: GalleryItem[]) => void;
  onInject: (text: string) => void;
}) {
  const [kind, setKind] = useState<"render-post" | "render-reel">("render-post");
  const [text, setText] = useState(JSON.stringify(POST_BLUEPRINT, null, 2));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fallback, setFallback] = useState("");

  function switchKind(next: "render-post" | "render-reel") {
    setKind(next);
    setFallback("");
    setText(JSON.stringify(next === "render-post" ? POST_BLUEPRINT : REEL_BLUEPRINT, null, 2));
  }

  function inject() {
    setError("");
    // Strict append mode: parent appends on a new line, never overwrites.
    const snippet = (() => {
      try {
        const data = JSON.parse(text) as Record<string, unknown>;
        const copy = data.copy as Record<string, string> | undefined;
        if (copy?.hook) return String(copy.hook);
        if (typeof data.hook === "string") return data.hook as string;
      } catch {
        // fall through to raw text
      }
      return text.slice(0, 500);
    })();
    onInject(snippet);
  }

  async function submit() {
    setBusy(true);
    setError("");
    setFallback("");
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
      let lastError = "";
      for (let i = 0; i < 120 && (status === "queued" || status === "running"); i++) {
        await new Promise((r) => setTimeout(r, 1000));
        try {
          const job = await getJob("", job_id);
          status = job.status;
          if (status === "failed") throw new Error(job.error ?? "render failed");
          if (status === "done") result = (job.result ?? {}) as typeof result;
        } catch (err) {
          lastError = err instanceof Error ? err.message : "render failed";
          // Transparent fallback: surface primary failure, keep polling once more.
          setFallback(`⚠️ Primary model failed -> retrying fallback (${lastError})`);
        }
      }
      const warnings = result.warnings ?? [];
      const failWarning = warnings.find((w) => /fail|fallback|switch/i.test(w));
      if (failWarning) setFallback(`⚠️ Model failed -> Switched (${failWarning})`);
      const items: GalleryItem[] = Object.entries(result.artifact_urls ?? {})
        .map(([key, url]) => {
          const media = galleryKind(url);
          return media ? { src: url, kind: media, label: key } : null;
        })
        .filter((item): item is GalleryItem => item !== null);
      onResult(items);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "render failed";
      setError(msg);
      setFallback(`⚠️ Primary model failed -> no fallback available (${msg})`);
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
      data-testid="playground"
    >
      <h2 className="text-xl font-semibold text-white">Resource Playground</h2>
      <div className="mt-3 flex flex-wrap gap-2" data-testid="playground-badges">
        {RESOURCE_BADGES.map((b) => (
          <span
            key={b}
            data-testid={`playground-badge-${b}`}
            className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-300"
          >
            [{b}]
          </span>
        ))}
      </div>
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
        data-testid="playground-prompt"
        className="mt-3 w-full rounded-2xl bg-black/40 border border-white/10 p-4 font-mono text-xs text-slate-200"
      />
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          onClick={submit}
          disabled={busy}
          data-testid="playground-render"
          className="rounded-full bg-[#A3E635] px-5 py-2 text-sm font-semibold text-slate-950 disabled:opacity-40"
        >
          {busy ? "Rendering…" : "Render single resource"}
        </button>
        <button
          onClick={inject}
          data-testid="playground-inject"
          className="rounded-full border border-[#A3E635] px-5 py-2 text-sm text-[#A3E635]"
        >
          Inject to Studio (append)
        </button>
      </div>
      {fallback && (
        <p
          data-testid="playground-fallback"
          className="mt-3 rounded-xl border border-yellow-300/30 bg-yellow-300/10 px-3 py-2 text-sm text-yellow-200"
        >
          {fallback}
        </p>
      )}
      {error && <p className="mt-2 text-sm text-red-400">{error}</p>}
    </motion.section>
  );
}
