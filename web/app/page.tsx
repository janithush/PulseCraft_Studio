"use client";

import { useCallback, useEffect, useState } from "react";
import CampaignStudio from "../components/CampaignStudio";
import InteractivePreviewGallery, { type GalleryItem } from "../components/InteractivePreviewGallery";
import FeatureTogglePanel from "../components/FeatureTogglePanel";
import TemplateInspectorModal from "../components/TemplateInspectorModal";
import BrandSelector from "../components/BrandSelector";
import ModelPriorityPanel from "../components/ModelPriorityPanel";
import ResourcePlayground from "../components/ResourcePlayground";
import { galleryKind, getJob, listBrands } from "../lib/api";

export default function Home() {
  const [items, setItems] = useState<GalleryItem[]>([]);
  const [brands, setBrands] = useState<string[]>([]);
  const [brand, setBrand] = useState("");
  const [prompt, setPrompt] = useState("");

  const refreshBrands = useCallback(async () => {
    try {
      const { brands: slugs } = await listBrands("");
      // Merge server slugs with any local-only slug; never auto-select —
      // the studio starts at "(No Brand Selected)" per visual review.
      setBrands((prev) => Array.from(new Set([...slugs, ...prev])));
      setBrand((prev) => (prev && slugs.includes(prev) ? prev : prev));
    } catch {
      // keep local state when the backend is unreachable
    }
  }, []);

  useEffect(() => {
    refreshBrands();
  }, [refreshBrands]);

  function handleSelectBrand(slug: string) {
    setBrand(slug);
    setBrands((prev) => (prev.includes(slug) ? prev : [...prev, slug]));
  }

  function handleNewCampaign() {
    // Reset clears ONLY the prompt textarea, preserving active Brand.
    setPrompt("");
  }

  function handleInject(text: string) {
    // Strict append mode: new line, never overwrite.
    setPrompt((prev) => (prev.trim() ? `${prev}\n${text}` : text));
  }

  async function collectJobItems(jobId: string): Promise<GalleryItem[]> {
    let status = "queued";
    let urls: Record<string, string> = {};
    for (let i = 0; i < 120 && (status === "queued" || status === "running"); i++) {
      await new Promise((r) => setTimeout(r, 1000));
      const job = await getJob("", jobId);
      status = job.status;
      if (status === "failed") throw new Error(job.error ?? "job failed");
      if (status === "done") {
        const result = (job.result ?? {}) as { artifact_urls?: Record<string, string> };
        urls = result.artifact_urls ?? {};
      }
    }
    // Clean metadata: never surface raw job hashes / temp filenames in labels.
    return Object.entries(urls)
      .map(([key, url]) => {
        const media = galleryKind(url);
        return media ? { src: url, kind: media, label: key } : null;
      })
      .filter((item): item is GalleryItem => item !== null);
  }

  async function handleDone(jobId: string) {
    try {
      const next = await collectJobItems(jobId);
      setItems((prev) => [...prev, ...next]);
    } catch {
      // job polling errors surface inside the originating component
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-10">
      <header className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">
            PulseCraft <span className="text-[#A3E635]">Studio</span>
          </h1>
          <p className="mt-1 text-sm text-slate-400">Liquid Glass campaign dashboard</p>
        </div>
        <div className="flex gap-2">
          <TemplateInspectorModal template="bold-hook-split" />
          <TemplateInspectorModal template="minimal-type" />
        </div>
      </header>
      <div className="grid grid-cols-12 gap-4">
        <CampaignStudio
          onDone={handleDone}
          brand={brand}
          prompt={prompt}
          onPromptChange={setPrompt}
        />
        <InteractivePreviewGallery
          items={items}
          onRemove={(idx) => setItems((prev) => prev.filter((_, i) => i !== idx))}
        />
        <BrandSelector
          brands={brands}
          selected={brand}
          onSelect={handleSelectBrand}
          onReset={handleNewCampaign}
        />
        <ResourcePlayground
          brand={brand}
          onResult={(next) => setItems((prev) => [...prev, ...next])}
          onInject={handleInject}
        />
        <ModelPriorityPanel />
        <FeatureTogglePanel />
      </div>
    </main>
  );
}
