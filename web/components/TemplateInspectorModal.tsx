"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

export default function TemplateInspectorModal({ template }: { template: string }) {
  const [open, setOpen] = useState(false);
  const [html, setHtml] = useState("");
  const [schema, setSchema] = useState<{ required: string[]; optional: string[] } | null>(null);

  async function inspect() {
    const res = await fetch(`/api/templates/${template}/preview`, { cache: "no-store" });
    const data = await res.json();
    setHtml(data.html ?? "");
    setSchema(data.schema ?? null);
    setOpen(true);
  }

  return (
    <>
      <button
        onClick={inspect}
        className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200"
      >
        Inspect {template}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
            onClick={() => setOpen(false)}
          >
            <motion.div
              initial={{ scale: 0.94, y: 12 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.96, opacity: 0 }}
              transition={{ type: "spring", stiffness: 300, damping: 30 }}
              className="glass max-h-[80vh] w-full max-w-2xl overflow-auto rounded-3xl p-6"
              onClick={(e) => e.stopPropagation()}
            >
              <h3 className="text-lg font-semibold text-white">{template}</h3>
              {schema && (
                <p className="mt-2 text-xs text-slate-400">
                  required: {schema.required.join(", ") || "none"} · optional:{" "}
                  {schema.optional.join(", ") || "none"}
                </p>
              )}
              <div
                className="mt-4 rounded-2xl border border-white/10 bg-white p-4 text-slate-900"
                dangerouslySetInnerHTML={{ __html: html }}
              />
              <button
                onClick={() => setOpen(false)}
                className="mt-4 rounded-full bg-[#A3E635] px-5 py-2 text-sm font-semibold text-slate-950"
              >
                Close
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
