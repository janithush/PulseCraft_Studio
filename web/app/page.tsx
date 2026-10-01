"use client";

import { useState } from "react";
import CampaignStudio from "../components/CampaignStudio";
import InteractivePreviewGallery, { type GalleryItem } from "../components/InteractivePreviewGallery";
import FeatureTogglePanel from "../components/FeatureTogglePanel";
import TemplateInspectorModal from "../components/TemplateInspectorModal";

export default function Home() {
  const [items, setItems] = useState<GalleryItem[]>([]);

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
        <CampaignStudio onDone={() => setItems([])} />
        <InteractivePreviewGallery items={items} />
        <FeatureTogglePanel />
      </div>
    </main>
  );
}
