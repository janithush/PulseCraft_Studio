"use client";

import { useCallback, useEffect, useState } from "react";
import CampaignStudio from "../components/CampaignStudio";
import InteractivePreviewGallery, { type GalleryItem } from "../components/InteractivePreviewGallery";
import FeatureTogglePanel from "../components/FeatureTogglePanel";
import TemplateInspectorModal from "../components/TemplateInspectorModal";
import BrandManager from "../components/BrandManager";
import ModelPriorityPanel from "../components/ModelPriorityPanel";
import ResourcePlayground from "../components/ResourcePlayground";
import { galleryKind, getJob, listBrands } from "../lib/api";

export default function Home() {
  const [items, setItems] = useState<GalleryItem[]>([]);
  const [brands, setBrands] = useState<string[]>(["acme"]);
  const [brand, setBrand] = useState("acme");

  const refreshBrands = useCallback(async () => {
    try {
      const { brands: slugs } = await listBrands("");
      if (slugs.length > 0) {
        setBrands(slugs);
        setBrand((prev) => (slugs.includes(prev) ? prev : slugs[0]));
      }
    } catch {
      // keep defaults when the backend is unreachable
    }
  }, []);

  useEffect(() => {
    refreshBrands();
  }, [refreshBrands]);

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
    return Object.entries(urls)
      .map(([key, url]) => {
        const media = galleryKind(url);
        return media ? { src: url, kind: media, label: `${jobId} · ${key}` } : null;
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
        <CampaignStudio onDone={handleDone} brand={brand} onBrandChange={setBrand} brands={brands} />
        <InteractivePreviewGallery items={items} />
        <BrandManager brands={brands} selected={brand} onSelect={setBrand} onRefresh={refreshBrands} />
        <ResourcePlayground brand={brand} onResult={(next) => setItems((prev) => [...prev, ...next])} />
        <ModelPriorityPanel />
        <FeatureTogglePanel />
      </div>
    </main>
  );
}
