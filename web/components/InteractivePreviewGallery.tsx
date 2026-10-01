"use client";

import { motion } from "framer-motion";

export type GalleryItem = { src: string; kind: "image" | "video"; label: string };

function cleanMeta(item: GalleryItem): { typeBadge: string; dimBadge: string; aspect: string } {
  const path = item.src.split("?")[0].toLowerCase();
  const isVideo = item.kind === "video" || /\.(mp4|webm|mov)$/.test(path);
  if (isVideo) return { typeBadge: "Reel [MP4]", dimBadge: "1080x1920", aspect: "9:16" };
  if (/1350/.test(item.src) || /vertical/.test(item.label.toLowerCase())) {
    return { typeBadge: "Post [PNG]", dimBadge: "1080x1350", aspect: "4:5" };
  }
  if (/1080x1080|square/.test(item.src + item.label)) {
    return { typeBadge: "Post [PNG]", dimBadge: "1080x1080", aspect: "1:1" };
  }
  // Default per protocol: PNG posts render 1080x1350.
  return { typeBadge: "Post [PNG]", dimBadge: "1080x1350", aspect: "4:5" };
}

export default function InteractivePreviewGallery({
  items,
  onRemove,
}: {
  items: GalleryItem[];
  onRemove?: (index: number) => void;
}) {
  if (items.length === 0) {
    return (
      <section
        data-testid="gallery"
        className="glass rounded-3xl p-6 col-span-12 lg:col-span-5"
      >
        <h2 className="text-xl font-semibold text-white">Preview Gallery</h2>
        <p className="mt-3 text-sm text-slate-400">
          Run a campaign to see live Jinja2 cards and Remotion reels with subtitle/BGM sync.
        </p>
      </section>
    );
  }
  return (
    <section
      data-testid="gallery"
      className="glass rounded-3xl p-6 col-span-12 lg:col-span-5"
    >
      <h2 className="text-xl font-semibold text-white">Preview Gallery</h2>
      <div className="mt-4 grid grid-cols-2 gap-3">
        {items.map((item, idx) => {
          const meta = cleanMeta(item);
          return (
            <motion.figure
              key={`${item.src}-${idx}`}
              data-testid={`gallery-card-${idx}`}
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ type: "spring", stiffness: 300, damping: 30 }}
              className="relative overflow-hidden rounded-2xl border border-white/10 bg-white/5"
            >
              <button
                onClick={() => onRemove?.(idx)}
                aria-label={`dismiss card ${idx}`}
                data-testid={`gallery-close-${idx}`}
                className="absolute right-2 top-2 z-10 rounded-full bg-black/60 border border-white/20 px-2 py-0.5 text-xs text-white hover:bg-black/90"
              >
                X
              </button>
              {item.kind === "video" ? (
                <video src={item.src} controls preload="metadata" className="h-40 w-full object-cover" />
              ) : (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={item.src} alt={meta.typeBadge} loading="lazy" className="h-40 w-full object-cover" />
              )}
              <figcaption className="flex flex-wrap gap-1 px-3 py-2">
                <span
                  data-testid={`gallery-type-${idx}`}
                  className="rounded-full border border-[#A3E635]/40 px-2 py-0.5 text-[11px] text-[#A3E635]"
                >
                  {meta.typeBadge}
                </span>
                <span
                  data-testid={`gallery-dims-${idx}`}
                  className="rounded-full border border-white/10 px-2 py-0.5 text-[11px] text-slate-300"
                >
                  {meta.dimBadge} / {meta.aspect}
                </span>
              </figcaption>
            </motion.figure>
          );
        })}
      </div>
    </section>
  );
}
