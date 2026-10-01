"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { createBrand, type BrandDoc } from "../lib/api";

const EMPTY: BrandDoc = {
  slug: "",
  name: "",
  colors: { primary: "#A3E635", bg: "#111111", text: "#FFFFFF" },
  fonts: { display: "Inter", body: "Inter" },
  voice: { id: "kokoro-default", speed: 1.0 },
};

export default function BrandManager({
  brands,
  selected,
  onSelect,
  onRefresh,
}: {
  brands: string[];
  selected: string;
  onSelect: (slug: string) => void;
  onRefresh: () => void;
}) {
  const [form, setForm] = useState<BrandDoc>(EMPTY);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  function set(path: string, value: string | number) {
    setForm((prev) => {
      const next = structuredClone(prev);
      const [group, key] = path.split(".");
      if (key) {
        (next[group as keyof BrandDoc] as Record<string, string | number>)[key] = value;
      } else {
        (next as unknown as Record<string, string | number>)[group] = value;
      }
      return next;
    });
  }

  async function submit() {
    setBusy(true);
    setMessage("");
    try {
      const payload: BrandDoc = {
        ...form,
        slug: form.slug.trim().toLowerCase(),
        voice: { ...form.voice, speed: Number(form.voice.speed) },
      };
      const { slug, created } = await createBrand("", payload);
      onRefresh();
      onSelect(slug);
      setMessage(created ? `Brand '${slug}' created.` : `Brand '${slug}' updated.`);
      setForm(EMPTY);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "create failed");
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
      <h2 className="text-xl font-semibold text-white">Brand Manager</h2>
      <div className="mt-4 flex flex-wrap gap-2">
        {brands.map((slug) => (
          <button
            key={slug}
            onClick={() => onSelect(slug)}
            className={`rounded-full px-4 py-1.5 text-sm border ${
              selected === slug
                ? "bg-[#A3E635] text-slate-950 border-transparent glow-neon"
                : "bg-white/5 border-white/10 text-slate-300"
            }`}
          >
            {slug}
          </button>
        ))}
        {brands.length === 0 && <p className="text-sm text-slate-500">No brands yet — create one below.</p>}
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <input
          value={form.slug}
          onChange={(e) => set("slug", e.target.value)}
          placeholder="slug (e.g. acme)"
          className="rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-slate-100 placeholder:text-slate-500"
        />
        <input
          value={form.name}
          onChange={(e) => set("name", e.target.value)}
          placeholder="Display name"
          className="rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-slate-100 placeholder:text-slate-500"
        />
        {(["primary", "bg", "text"] as const).map((key) => (
          <label key={key} className="flex items-center gap-2 text-slate-400">
            <input
              type="color"
              value={form.colors[key] ?? "#ffffff"}
              onChange={(e) => set(`colors.${key}`, e.target.value)}
              className="h-8 w-10 cursor-pointer rounded bg-transparent"
            />
            {key}
          </label>
        ))}
        <input
          value={form.fonts.display}
          onChange={(e) => set("fonts.display", e.target.value)}
          placeholder="Display font"
          className="rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-slate-100 placeholder:text-slate-500"
        />
        <input
          value={form.voice.id}
          onChange={(e) => set("voice.id", e.target.value)}
          placeholder="Voice id"
          className="rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-slate-100 placeholder:text-slate-500"
        />
      </div>
      <button
        onClick={submit}
        disabled={busy || !form.slug.trim() || !form.name.trim()}
        className="mt-4 rounded-full bg-[#A3E635] px-5 py-2 text-sm font-semibold text-slate-950 disabled:opacity-40"
      >
        {busy ? "Saving…" : "Create / update brand"}
      </button>
      {message && <p className="mt-2 text-sm text-slate-300">{message}</p>}
    </motion.section>
  );
}
