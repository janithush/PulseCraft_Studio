"use client";

import { useState } from "react";
import { motion } from "framer-motion";

export default function BrandSelector({
  brands,
  selected,
  onSelect,
  onReset,
}: {
  brands: string[];
  selected: string;
  onSelect: (slug: string) => void;
  onReset: () => void;
}) {
  const [draft, setDraft] = useState("");

  function commit(value: string) {
    const slug = value.trim().toLowerCase();
    if (!slug) return;
    // Local-only: do NOT POST to /api/brands here. The slug lives in UI
    // state until the first campaign submit (prevents junk files on typos).
    onSelect(slug);
    setDraft("");
  }

  return (
    <motion.section
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
      className="glass rounded-3xl p-6 col-span-12 lg:col-span-6"
      data-testid="brand-selector"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-white">Brand Selector</h2>
        <button
          onClick={onReset}
          data-testid="new-campaign-btn"
          className="rounded-full border border-white/10 px-4 py-1.5 text-xs text-slate-300 hover:border-[#A3E635] hover:text-[#A3E635]"
        >
          New Campaign
        </button>
      </div>
      <p className="mt-1 text-xs text-slate-500">
        Select existing or type a new slug (e.g. CEL). New slugs stay local until first campaign
        submit.
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit(draft);
          }}
          placeholder="Type brand slug or pick below (e.g. CEL)"
          list="brand-datalist"
          data-testid="brand-input"
          className="min-w-[220px] flex-1 rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-[#A3E635]"
        />
        <datalist id="brand-datalist">
          {brands.map((slug) => (
            <option key={slug} value={slug} />
          ))}
        </datalist>
        <select
          value={brands.includes(selected) ? selected : ""}
          onChange={(e) => {
            if (e.target.value) commit(e.target.value);
          }}
          data-testid="brand-dropdown"
          aria-label="Select existing brand"
          className="rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-sm text-slate-100"
        >
          <option value="">Select existing…</option>
          {brands.map((slug) => (
            <option key={slug} value={slug}>
              {slug}
            </option>
          ))}
        </select>
        <button
          onClick={() => commit(draft)}
          disabled={!draft.trim()}
          data-testid="brand-apply-btn"
          className="rounded-full bg-[#A3E635] px-5 py-2 text-sm font-semibold text-slate-950 disabled:opacity-40"
        >
          Use brand
        </button>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="text-xs text-slate-500">Active:</span>
        <span
          data-testid="brand-active"
          className="rounded-full bg-[#A3E635] px-4 py-1.5 text-sm font-medium text-slate-950 glow-neon"
        >
          {selected || "(none)"}
        </span>
      </div>
    </motion.section>
  );
}
