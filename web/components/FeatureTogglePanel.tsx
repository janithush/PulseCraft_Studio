"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { getFeatures, patchFeature } from "../lib/api";

const GROUPS: { title: string; paths: string[] }[] = [
  { title: "Processing Engines", paths: ["tts.kokoro", "stt.whisper"] },
  { title: "Graphics APIs", paths: ["media.pexels", "media.pixabay", "media.openverse"] },
  { title: "Audio Engines", paths: ["audio.sfx", "audio.bgm"] },
];

function readEnabled(features: Record<string, unknown>, dotted: string): boolean {
  const parts = dotted.split(".");
  let node: unknown = features;
  for (const part of parts) {
    if (typeof node !== "object" || node === null) return false;
    node = (node as Record<string, unknown>)[part];
  }
  if (typeof node === "object" && node !== null && "enabled" in node) {
    return Boolean((node as Record<string, unknown>).enabled);
  }
  return false;
}

export default function FeatureTogglePanel() {
  const [features, setFeatures] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    getFeatures("").then(setFeatures).catch(() => setFeatures({}));
  }, []);

  async function flip(path: string, enabled: boolean) {
    await patchFeature("", path, !enabled).catch(() => undefined);
    const next = await getFeatures("").catch(() => null);
    if (next) setFeatures(next);
  }

  return (
    <motion.section
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
      className="glass rounded-3xl p-6 col-span-12"
    >
      <h2 className="text-xl font-semibold text-white">Feature Toggles</h2>
      <div className="mt-4 grid gap-4 md:grid-cols-3">
        {GROUPS.map((group) => (
          <div key={group.title} className="rounded-2xl border border-white/10 bg-white/5 p-4">
            <h3 className="text-sm font-medium text-slate-200">{group.title}</h3>
            <ul className="mt-3 space-y-2">
              {group.paths.map((path) => {
                const enabled = features ? readEnabled(features, path) : false;
                return (
                  <li key={path} className="flex items-center justify-between text-sm">
                    <span className="text-slate-300">{path}</span>
                    <button
                      role="switch"
                      aria-checked={enabled}
                      onClick={() => flip(path, enabled)}
                      className={`relative h-6 w-11 rounded-full transition ${
                        enabled ? "bg-[#A3E635]" : "bg-white/10"
                      }`}
                    >
                      <span
                        className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all ${
                          enabled ? "left-[22px]" : "left-0.5"
                        }`}
                      />
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
    </motion.section>
  );
}
