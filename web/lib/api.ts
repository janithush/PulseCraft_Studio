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
