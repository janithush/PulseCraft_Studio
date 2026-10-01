export async function getHealth(base = "http://localhost:8000"): Promise<{ status: string }> {
  const res = await fetch(`${base}/api/health`, { cache: "no-store" });
  if (!res.ok) throw new Error(`health failed: ${res.status}`);
  return res.json();
}

export async function listTemplates(base = ""): Promise<{ templates: { name: string; kind: string }[] }> {
  const res = await fetch(`${base}/api/templates`, { cache: "no-store" });
  if (!res.ok) throw new Error(`templates failed: ${res.status}`);
  return res.json();
}

export async function getFeatures(base = ""): Promise<Record<string, unknown>> {
  const res = await fetch(`${base}/api/features`, { cache: "no-store" });
  if (!res.ok) throw new Error(`features failed: ${res.status}`);
  return res.json();
}

export async function patchFeature(base: string, path: string, enabled: boolean): Promise<unknown> {
  const res = await fetch(`${base}/api/features`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, enabled }),
  });
  if (!res.ok) throw new Error(`patch failed: ${res.status}`);
  return res.json();
}

export async function createCampaign(
  base: string,
  body: { prompt: string; brand: string; formats: string; preset: string; platform: string; seed: number },
): Promise<{ job_id: string }> {
  const res = await fetch(`${base}/api/campaigns`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`campaign failed: ${res.status}`);
  return res.json();
}

export async function getJob(base: string, jobId: string): Promise<{ status: string; result?: unknown; error?: string }> {
  const res = await fetch(`${base}/api/jobs/${jobId}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`job failed: ${res.status}`);
  return res.json();
}

export type BrandDoc = {
  slug: string;
  name: string;
  colors: Record<string, string>;
  fonts: Record<string, string>;
  voice: { id: string; speed: number };
};

export async function listBrands(base = ""): Promise<{ brands: string[] }> {
  const res = await fetch(`${base}/api/brands`, { cache: "no-store" });
  if (!res.ok) throw new Error(`brands failed: ${res.status}`);
  return res.json();
}

export async function getBrand(
  base: string,
  slug: string,
): Promise<{ slug: string; brand: Record<string, unknown>; warnings: string[] }> {
  const res = await fetch(`${base}/api/brands/${slug}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`brand failed: ${res.status}`);
  return res.json();
}

export async function createBrand(base: string, body: BrandDoc): Promise<{ slug: string; created: boolean }> {
  const res = await fetch(`${base}/api/brands`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`create brand failed: ${res.status}`);
  return res.json();
}

export type ModelRegistry = {
  version: string;
  tasks: Record<string, { chain: string[] }>;
  registry: Record<string, { label: string; status: string; lastChecked: string | null }>;
};

export async function getModels(base = ""): Promise<ModelRegistry> {
  const res = await fetch(`${base}/api/models`, { cache: "no-store" });
  if (!res.ok) throw new Error(`models failed: ${res.status}`);
  return res.json();
}

export async function patchModels(base: string, body: Record<string, unknown>): Promise<unknown> {
  const res = await fetch(`${base}/api/models`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`patch models failed: ${res.status}`);
  return res.json();
}

export async function renderResource(
  base: string,
  body: { kind: string; blueprint: Record<string, unknown>; brand: string; preset: string; platform: string },
): Promise<{ job_id: string }> {
  const res = await fetch(`${base}/api/render`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`render failed: ${res.status}`);
  return res.json();
}

export function galleryKind(url: string): "image" | "video" | null {
  const path = url.split("?")[0].toLowerCase();
  if (/\.(mp4|webm|mov)$/.test(path)) return "video";
  if (/\.(png|jpe?g|webp|gif)$/.test(path)) return "image";
  return null;
}
