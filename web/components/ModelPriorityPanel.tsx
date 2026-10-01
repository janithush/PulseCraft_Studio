"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { getModels, patchModels, type ModelRegistry } from "../lib/api";

function move(chain: string[], from: number, to: number): string[] {
  if (to < 0 || to >= chain.length) return chain;
  const next = [...chain];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

export default function ModelPriorityPanel() {
  const [models, setModels] = useState<ModelRegistry | null>(null);
  const [error, setError] = useState("");
  const [newId, setNewId] = useState("");
  const [newLabel, setNewLabel] = useState("");

  async function refresh() {
    try {
      setModels(await getModels(""));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "models failed");
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function reorder(task: string, chain: string[]) {
    try {
      await patchModels("", { op: "set_chain", task, chain });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "reorder failed");
    }
  }

  async function addModel() {
    if (!newId.trim() || !newLabel.trim()) return;
    try {
      await patchModels("", { op: "add_model", id: newId.trim(), label: newLabel.trim() });
      setNewId("");
      setNewLabel("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "add failed");
    }
  }

  const badge = (status: string) =>
    status === "connected"
      ? "text-[#A3E635] border-[#A3E635]"
      : status === "failed"
        ? "text-red-400 border-red-400/40"
        : "text-slate-400 border-white/10";

  return (
    <motion.section
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
      className="glass rounded-3xl p-6 col-span-12"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-white">Model Orchestrator</h2>
        <button onClick={refresh} className="rounded-full border border-white/10 px-4 py-1 text-xs text-slate-300">
          Refresh
        </button>
      </div>
      {error && <p className="mt-2 text-sm text-red-400">{error}</p>}
      {!models && !error && <p className="mt-3 text-sm text-slate-500">Loading registry…</p>}
      {models && (
        <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Object.entries(models.tasks).map(([task, spec]) => (
            <div key={task} className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <h3 className="text-sm font-medium text-slate-200">{task}</h3>
              <ol className="mt-2 space-y-1.5">
                {spec.chain.map((id, i) => (
                  <li key={id} className="flex items-center gap-2 text-xs">
                    <span className="text-slate-500">{i + 1}.</span>
                    <span className="flex-1 truncate text-slate-300" title={id}>
                      {id}
                    </span>
                    <span className={`rounded-full border px-2 py-0.5 ${badge(models.registry[id]?.status ?? "unknown")}`}>
                      {models.registry[id]?.status ?? "unknown"}
                    </span>
                    <button
                      onClick={() => reorder(task, move(spec.chain, i, i - 1))}
                      disabled={i === 0}
                      aria-label={`promote ${id}`}
                      className="rounded-full border border-white/10 px-2 text-slate-300 disabled:opacity-30"
                    >
                      ↑
                    </button>
                    <button
                      onClick={() => reorder(task, move(spec.chain, i, i + 1))}
                      disabled={i === spec.chain.length - 1}
                      aria-label={`demote ${id}`}
                      className="rounded-full border border-white/10 px-2 text-slate-300 disabled:opacity-30"
                    >
                      ↓
                    </button>
                  </li>
                ))}
              </ol>
            </div>
          ))}
        </div>
      )}
      <div className="mt-4 flex flex-wrap gap-2 text-sm">
        <input
          value={newId}
          onChange={(e) => setNewId(e.target.value)}
          placeholder="vendor/model:tag"
          className="rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-slate-100 placeholder:text-slate-500"
        />
        <input
          value={newLabel}
          onChange={(e) => setNewLabel(e.target.value)}
          placeholder="Label"
          className="rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-slate-100 placeholder:text-slate-500"
        />
        <button
          onClick={addModel}
          disabled={!newId.trim() || !newLabel.trim()}
          className="rounded-full bg-[#A3E635] px-5 py-2 font-semibold text-slate-950 disabled:opacity-40"
        >
          Add model
        </button>
      </div>
    </motion.section>
  );
}
