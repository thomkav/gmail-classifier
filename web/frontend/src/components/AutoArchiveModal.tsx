import { useState, useEffect } from "react";
import type { AutoArchivePlan, ApplyResult } from "../types";
import { api } from "../api";

interface Props {
  accountId: number | null;
  onClose: () => void;
  onApplied: (result: ApplyResult) => void;
}

type Phase = "loading-plan" | "review" | "applying" | "error";

function Spinner() {
  return (
    <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin opacity-60" />
  );
}

export function AutoArchiveModal({ accountId, onClose, onApplied }: Props) {
  const [phase, setPhase] = useState<Phase>("loading-plan");
  const [plan, setPlan] = useState<AutoArchivePlan | null>(null);
  const [threshold, setThreshold] = useState(70);
  const [error, setError] = useState<string | null>(null);

  async function loadPlan(t: number) {
    setPhase("loading-plan");
    setError(null);
    try {
      const p = await api.getAutoArchivePlan(t, accountId ?? undefined);
      setPlan(p);
      setPhase("review");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load plan");
      setPhase("error");
    }
  }

  useEffect(() => {
    loadPlan(threshold);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function applyPlan() {
    setPhase("applying");
    try {
      const result = await api.applyAutoArchive(threshold, accountId ?? undefined);
      onApplied(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Apply failed");
      setPhase("error");
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div className="relative z-10 bg-white border border-gray-200 rounded-lg shadow-2xl w-full max-w-3xl mx-4 flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 shrink-0">
          <h2 className="text-sm font-semibold text-gray-800">Auto-archive</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-lg leading-none">
            ×
          </button>
        </div>

        {/* Threshold control */}
        <div className="px-6 py-3 border-b border-gray-200 flex items-center gap-4 shrink-0">
          <label className="text-xs text-gray-600">Confidence threshold</label>
          <input
            type="number"
            min={10}
            max={100}
            step={5}
            value={threshold}
            onChange={(e) => setThreshold(Number(e.target.value))}
            className="w-16 bg-gray-50 border border-gray-300 rounded px-2 py-1 text-xs text-gray-800 text-center"
          />
          <span className="text-xs text-gray-400">%</span>
          <button
            onClick={() => loadPlan(threshold)}
            disabled={phase === "loading-plan" || phase === "applying"}
            className="text-xs px-3 py-1 rounded bg-gray-100 hover:bg-gray-200 text-gray-700 border border-gray-200 disabled:opacity-40"
          >
            Recompute
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-auto px-6 py-4">
          {phase === "loading-plan" && (
            <div className="flex flex-col items-center justify-center h-40 gap-3">
              <Spinner />
              <p className="text-xs text-gray-500">Fetching and classifying inbox…</p>
            </div>
          )}

          {phase === "error" && (
            <div className="flex flex-col items-center justify-center h-40 gap-3">
              <p className="text-red-600 text-sm">{error}</p>
              <button
                onClick={() => loadPlan(threshold)}
                className="text-xs px-3 py-1.5 rounded bg-gray-100 hover:bg-gray-200 text-gray-700 border border-gray-200"
              >
                Retry
              </button>
            </div>
          )}

          {phase === "applying" && (
            <div className="flex flex-col items-center justify-center h-40 gap-3">
              <Spinner />
              <p className="text-xs text-gray-500">Archiving domains…</p>
            </div>
          )}

          {phase === "review" && plan && (
            <div className="space-y-6">
              {/* Summary */}
              <div className="flex gap-6 text-xs text-gray-600">
                <span>
                  <span className="text-gray-900 font-medium">{plan.total_unread.toLocaleString()}</span>{" "}
                  unread
                </span>
                <span>
                  <span className="text-red-600 font-medium">{plan.to_archive.length}</span>{" "}
                  domains to archive ({plan.to_archive.reduce((s, e) => s + e.count, 0)} inbox emails)
                </span>
                <span>
                  <span className="text-gray-600">{plan.to_skip.length}</span>{" "}
                  skipped
                </span>
              </div>

              {/* To-archive list */}
              {plan.to_archive.length === 0 ? (
                <p className="text-gray-500 text-xs">Nothing meets the auto-archive threshold.</p>
              ) : (
                <section>
                  <h3 className="text-xs font-medium text-gray-600 uppercase tracking-wider mb-2">
                    Will archive
                  </h3>
                  <PlanTable entries={plan.to_archive} variant="archive" />
                </section>
              )}

              {/* To-skip list */}
              {plan.to_skip.length > 0 && (
                <section>
                  <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-2">
                    Skipped
                  </h3>
                  <PlanTable entries={plan.to_skip.slice(0, 30)} variant="skip" />
                  {plan.to_skip.length > 30 && (
                    <p className="text-xs text-gray-400 mt-2">… and {plan.to_skip.length - 30} more</p>
                  )}
                </section>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        {phase === "review" && plan && (
          <div className="px-6 py-4 border-t border-gray-200 flex items-center justify-between shrink-0">
            <p className="text-xs text-gray-500">
              This will archive{" "}
              <span className="text-gray-700 font-medium">
                {plan.to_archive.reduce((s, e) => s + e.count, 0)} inbox emails
              </span>{" "}
              across {plan.to_archive.length} domain{plan.to_archive.length !== 1 ? "s" : ""} and update <code className="text-gray-600">.local.md</code>.
            </p>
            <div className="flex gap-3">
              <button onClick={onClose} className="btn-ghost text-xs">
                Cancel
              </button>
              <button
                onClick={applyPlan}
                disabled={plan.to_archive.length === 0}
                className="btn-primary text-xs"
              >
                Confirm &amp; Archive
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function PlanTable({
  entries,
  variant,
}: {
  entries: AutoArchivePlan["to_archive"];
  variant: "archive" | "skip";
}) {
  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-left text-gray-500 border-b border-gray-200">
          <th className="pb-1 font-normal">Domain</th>
          <th className="pb-1 font-normal w-16 text-right">Emails</th>
          <th className="pb-1 font-normal w-24 text-right">Confidence</th>
          <th className="pb-1 font-normal pl-4">Reason</th>
        </tr>
      </thead>
      <tbody>
        {entries.map((e) => (
          <tr
            key={e.domain}
            className={`border-b border-gray-100 ${
              variant === "archive" ? "text-gray-700" : "text-gray-400"
            }`}
          >
            <td className="py-1.5 font-mono">{e.domain}</td>
            <td className="py-1.5 text-right tabular-nums">{e.count}</td>
            <td className="py-1.5 text-right tabular-nums">{Math.round(e.confidence)}%</td>
            <td className="py-1.5 pl-4 text-gray-500">{e.reason}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
