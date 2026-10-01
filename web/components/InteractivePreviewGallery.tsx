"use client";

import { motion } from "framer-motion";

export type GalleryItem = { src: string; kind: "image" | "video"; label: string };

export default function InteractivePreviewGallery({ items }: { items: GalleryItem[] }) {
  if (items.length === 0) {
    return (
      <section className="glass rounded-3xl p-6 col-span-12 lg:col-span-5">
        <h2 className="text-xl font-semibold text-white">Preview Gallery</h2>
        <p className="mt-3 text-sm text-slate-400">
          Run a campaign to see live Jinja2 cards and Remotion reels with subtitle/BGM sync.
        </p>
      </section>
    );
  }
  return (
    <section className="glass rounded-3xl p-6 col-span-12 lg:col-span-5">
      <h2 className="text-xl font-semibold text-white">Preview Gallery</h2>
      <div className="mt-4 grid grid-cols-2 gap-3">
        {items.map((item) => (
          <motion.figure
            key={item.src}
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="overflow-hidden rounded-2xl border border-white/10 bg-white/5"
          >
            {item.kind === "video" ? (
              <video src={item.src} controls preload="metadata" className="h-40 w-full object-cover" />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={item.src} alt={item.label} loading="lazy" className="h-40 w-full object-cover" />
            )}
            <figcaption className="px-3 py-2 text-xs text-slate-400">{item.label}</figcaption>
          </motion.figure>
        ))}
      </div>
    </section>
  );
}
