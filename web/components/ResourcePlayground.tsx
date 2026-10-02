"use client";

import { useMemo, useRef, useState, type ClipboardEvent, type FocusEvent } from "react";
import { motion } from "framer-motion";
import { galleryKind, getJob, renderResource } from "../lib/api";
import type { GalleryItem } from "./InteractivePreviewGallery";

/** Normalize common paste artifacts so JSON.parse has a fair chance. */
export function sanitizeJsonText(raw: string): string {
  let out = raw.replace(/^\ufeff/, "").replace(/[\u200b-\u200d\ufeff]/g, "");
  out = out.replace(/[\u201c\u201d\u201e\u00ab\u00bb]/g, '"').replace(/[\u2018\u2019\u201a\u2032]/g, "'");
  const fenced = out.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fenced) out = fenced[1];
  out = out.replace(/,(\s*[}\]])/g, "$1");
  return out.trim();
}

function lineColOf(text: string, pos: number): string {
  const upto = text.slice(0, Math.max(0, pos));
  const line = upto.split("\n").length;
  const col = pos - (upto.lastIndexOf("\n") + 1) + 1;
  return `line ${line}, column ${col}`;
}

export function friendlyJsonError(err: unknown, text?: string): string {
  const msg = err instanceof Error ? err.message : String(err);
  const at = msg.match(/at position (\d+)/);
  const where = at && text !== undefined ? ` (${lineColOf(text, Number(at[1]))})` : "";
  if (/control character/i.test(msg)) {
    return `Bad control character (raw newline/tab inside a string)${where}. Put text on one line with \\n escapes.`;
  }
  if (/escaped character/i.test(msg)) {
    return `Bad escaped character${where}. Single backslashes (e.g. D:\\path) must be written as \\\\ .`;
  }
  if (/property name|Unexpected token/i.test(msg)) {
    return `Invalid JSON syntax${where}. Check quotes, commas, and brackets.`;
  }
  return `JSON parse error${where}: ${msg}`;
}

/** Strict parse first, sanitized parse as fallback (paste artifacts). */
export function parseBlueprintText(text: string): Record<string, unknown> {
  try {
    return JSON.parse(text) as Record<string, unknown>;
  } catch {
    return JSON.parse(sanitizeJsonText(text)) as Record<string, unknown>;
  }
}

export function tryPrettyJson(raw: string): { ok: true; text: string } | { ok: false; message: string } {
  try {
    return { ok: true, text: JSON.stringify(parseBlueprintText(raw), null, 2) };
  } catch (err) {
    return { ok: false, message: friendlyJsonError(err, raw) };
  }
}

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
  const [copied, setCopied] = useState(false);
  const areaRef = useRef<HTMLTextAreaElement>(null);

  const validation = useMemo(() => {
    if (!text.trim()) return { valid: false, message: "Empty input: paste a blueprint JSON object." };
    try {
      parseBlueprintText(text);
      return { valid: true, message: "Valid JSON" };
    } catch (err) {
      return { valid: false, message: friendlyJsonError(err, text) };
    }
  }, [text]);

  function insertAtCursor(insert: string) {
    const el = areaRef.current;
    if (!el) {
      setText((prev) => prev + insert);
      return;
    }
    const start = el.selectionStart ?? el.value.length;
    const end = el.selectionEnd ?? el.value.length;
    const next = el.value.slice(0, start) + insert + el.value.slice(end);
    setText(next);
    const caret = start + insert.length;
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(caret, caret);
    });
  }

  function handlePaste(e: ClipboardEvent<HTMLTextAreaElement>) {
    const raw = e.clipboardData.getData("text");
    if (!raw) return;
    e.preventDefault();
    setError("");
    const pretty = tryPrettyJson(raw);
    // Standalone JSON pastes go in pretty-printed; anything else is
    // inserted verbatim at the caret (validation hint explains the issue).
    insertAtCursor(pretty.ok ? pretty.text : raw);
  }

  function handleBlur(e: FocusEvent<HTMLTextAreaElement>) {
    const pretty = tryPrettyJson(e.target.value);
    if (pretty.ok && pretty.text !== e.target.value) setText(pretty.text);
  }

  function formatNow() {
    const pretty = tryPrettyJson(text);
    if (pretty.ok) {
      setText(pretty.text);
      setError("");
    } else {
      setError(pretty.message);
    }
  }

  async function copyNow() {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  function resetNow() {
    setError("");
    setText(JSON.stringify(kind === "render-post" ? POST_BLUEPRINT : REEL_BLUEPRINT, null, 2));
  }

  function switchKind(next: "render-post" | "render-reel") {
    setKind(next);
    setFallback("");
    setError("");
    setText(JSON.stringify(next === "render-post" ? POST_BLUEPRINT : REEL_BLUEPRINT, null, 2));
  }

  function inject() {
    setError("");
    // Strict append mode: parent appends on a new line, never overwrites.
    const snippet = (() => {
      try {
        const data = parseBlueprintText(text);
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
      let blueprint: Record<string, unknown>;
      try {
        blueprint = parseBlueprintText(text);
      } catch (err) {
        throw new Error(friendlyJsonError(err, text));
      }
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
        ref={areaRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onPaste={handlePaste}
        onBlur={handleBlur}
        rows={10}
        spellCheck={false}
        data-testid="playground-prompt"
        className="mt-3 w-full rounded-2xl bg-black/40 border border-white/10 p-4 font-mono text-xs text-slate-200"
      />
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <p
          data-testid="playground-json-status"
          className={`text-xs ${validation.valid ? "text-[#A3E635]" : "text-red-400"}`}
        >
          {validation.valid ? "✓ Valid JSON" : `✗ ${validation.message}`}
        </p>
        <span className="flex-1" />
        <button
          onClick={formatNow}
          data-testid="playground-format"
          className="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-300"
        >
          Format
        </button>
        <button
          onClick={copyNow}
          data-testid="playground-copy"
          className="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-300"
        >
          {copied ? "Copied ✓" : "Copy"}
        </button>
        <button
          onClick={resetNow}
          data-testid="playground-reset"
          className="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-300"
        >
          Reset
        </button>
      </div>
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
