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

function labelFor(id: string): string {
  const tail = id.split("/").pop() ?? id;
  return tail.split(":")[0].replace(/-/g, " ");
}

export function OrchestratorPanel({
  title,
  tasks,
  testId,
}: {
  title: string;
  tasks: string[];
  testId: string;
}) {
  const [models, setModels] = useState<ModelRegistry | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [checking, setChecking] = useState(true);
  const [newId, setNewId] = useState("");

  async function refresh() {
    setChecking(true);
    try {
      setModels(await getModels(""));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "models failed");
    } finally {
      setChecking(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function reorder(task: string, chain: string[]) {
    setError("");
    setNotice("");
    try {
      await patchModels("", { op: "set_chain", task, chain });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "reorder failed");
    }
  }

  async function removeFromChain(task: string, chain: string[], id: string) {
    setError("");
    setNotice("");
    const next = chain.filter((m) => m !== id);
    if (next.length === 0) {
      setError(`Cannot remove '${id}': chain for '${task}' must keep at least one model.`);
      return;
    }
    await reorder(task, next);
    setNotice(`Removed '${id}' from '${task}'.`);
  }

  async function addModel() {
    const id = newId.trim();
    if (!id) return;
    if (!id.includes("/")) {
      setError("Model id must look like 'vendor/model:tag' (e.g. deepseek/deepseek-r1:free).");
      return;
    }
    setError("");
    setNotice("");
    try {
      // Register globally, then attach to this panel's tasks.
      await patchModels("", { op: "add_model", id, label: labelFor(id), tasks: [] }).catch(
        (err) => {
          // add_model is idempotent via setdefault; a 422 may mean it exists — continue.
          if (!(err instanceof Error && err.message.includes("422"))) throw err;
        },
      );
      const current = models;
      for (const task of tasks) {
        const chain = current?.tasks[task]?.chain ?? [];
        if (!chain.includes(id)) {
          await patchModels("", { op: "set_chain", task, chain: [...chain, id] });
        }
      }
      setNewId("");
      setNotice(`Added '${id}'.`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "add failed");
    }
  }

  function badge(status: string, isChecking: boolean) {
    if (isChecking) return "badge-checking";
    if (status === "connected") return "badge-ok";
    if (status === "failed") return "badge-err";
    return "badge-idle";
  }

  function badgeText(status: string, isChecking: boolean) {
    if (isChecking) return "🟡 Checking";
    if (status === "connected") return "🟢 Active";
    if (status === "failed") return "🔴 Error";
    return "⚪ Unchecked";
  }

  const visibleTasks = tasks.filter((t) => !models || models.tasks[t]);

  return (
    <motion.section
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
      className="glass rounded-3xl p-6 col-span-12 lg:col-span-6"
      data-testid={testId}
    >
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-white">{title}</h2>
        <button
          onClick={refresh}
          data-testid={`${testId}-refresh`}
          className="rounded-full border border-white/10 px-4 py-1 text-xs text-slate-300"
        >
          Refresh
        </button>
      </div>
      {error && (
        <p data-testid={`${testId}-error`} className="mt-2 text-sm text-red-400">
          {error}
        </p>
      )}
      {notice && <p className="mt-2 text-sm text-slate-300">{notice}</p>}
      {!models && checking && <p className="mt-3 text-sm text-slate-500">🟡 Checking models…</p>}
      {models && (
        <div className="mt-4 grid gap-4">
          {visibleTasks.map((task) => {
            const chain = models.tasks[task]?.chain ?? [];
            return (
              <div
                key={task}
                data-testid={`${testId}-task-${task}`}
                className="rounded-2xl border border-white/10 bg-white/5 p-4"
              >
                <h3 className="text-sm font-medium text-slate-200">{task}</h3>
                <ol className="mt-2 space-y-1.5">
                  {chain.map((id, i) => (
                    <li
                      key={id}
                      data-testid={`${testId}-model-${id}`}
                      className="flex items-center gap-2 text-xs"
                    >
                      <span className="text-slate-500">{i + 1}.</span>
                      <span className="flex-1 truncate text-slate-300" title={id}>
                        {id}
                      </span>
                      <span
                        data-testid={`${testId}-status-${id}`}
                        data-status={
                          checking ? "checking" : (models.registry[id]?.status ?? "unknown")
                        }
                        className={`rounded-full border px-2 py-0.5 ${badge(models.registry[id]?.status ?? "unknown", checking)}`}
                      >
                        {badgeText(models.registry[id]?.status ?? "unknown", checking)}
                      </span>
                      <button
                        onClick={() => reorder(task, move(chain, i, i - 1))}
                        disabled={i === 0}
                        aria-label={`promote ${id}`}
                        className="rounded-full border border-white/10 px-2 text-slate-300 disabled:opacity-30"
                      >
                        ↑
                      </button>
                      <button
                        onClick={() => reorder(task, move(chain, i, i + 1))}
                        disabled={i === chain.length - 1}
                        aria-label={`demote ${id}`}
                        className="rounded-full border border-white/10 px-2 text-slate-300 disabled:opacity-30"
                      >
                        ↓
                      </button>
                      <button
                        onClick={() => removeFromChain(task, chain, id)}
                        aria-label={`remove ${id} from ${task}`}
                        data-testid={`${testId}-remove-${id}`}
                        className="rounded-full border border-red-400/40 px-2 text-red-300 hover:bg-red-400/10"
                      >
                        X
                      </button>
                    </li>
                  ))}
                </ol>
              </div>
            );
          })}
        </div>
      )}
      <div className="mt-4 flex flex-wrap gap-2 text-sm">
        <input
          value={newId}
          onChange={(e) => setNewId(e.target.value)}
          placeholder="vendor/model:tag (e.g. deepseek/deepseek-r1:free)"
          data-testid={`${testId}-new-model`}
          className="min-w-[240px] flex-1 rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-slate-100 placeholder:text-slate-500"
        />
        <button
          onClick={addModel}
          disabled={!newId.trim()}
          data-testid={`${testId}-add-btn`}
          className="rounded-full bg-[#A3E635] px-5 py-2 font-semibold text-slate-950 disabled:opacity-40"
        >
          Add model
        </button>
      </div>
    </motion.section>
  );
}

export default function ModelPriorityPanel() {
  return (
    <>
      <OrchestratorPanel
        title="Orchestrator A — Resource Playground"
        tasks={["promptExpansion", "copywriting"]}
        testId="orchestrator-a"
      />
      <OrchestratorPanel
        title="Orchestrator B — JSON Conversion"
        tasks={["jsonBlueprintConversion"]}
        testId="orchestrator-b"
      />
    </>
  );
}
