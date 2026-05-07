import { useState } from "react";
import type { DomainDecision, DecisionState, Domain } from "../types";

const STATE_STYLES: Record<DecisionState, { bg: string; text: string; label: string }> = {
  recidivist:    { bg: "bg-red-50",     text: "text-red-700",     label: "recidivist" },
  unsub_pending: { bg: "bg-violet-50",  text: "text-violet-700",  label: "unsub-watch" },
  seen:          { bg: "bg-gray-100",   text: "text-gray-500",    label: "seen" },
  archived:      { bg: "bg-amber-50",   text: "text-amber-700",   label: "auto-arch" },
  keep:          { bg: "bg-emerald-50", text: "text-emerald-700", label: "keep" },
};

const STATE_ORDER: DecisionState[] = ["recidivist", "unsub_pending", "seen", "archived", "keep"];

function StateBadge({ state }: { state: DecisionState }) {
  const s = STATE_STYLES[state];
  return (
    <span className={`inline-block px-1.5 py-0.5 rounded text-xs ${s.bg} ${s.text}`}>
      {s.label}
    </span>
  );
}

function daysSince(dateStr: string): number {
  const d = new Date(dateStr);
  const now = new Date();
  return Math.floor((now.getTime() - d.getTime()) / (1000 * 60 * 60 * 24));
}

interface Props {
  decisions: Record<string, DomainDecision>;
  currentDomains: Domain[];
}

export function DecisionsPanel({ decisions, currentDomains }: Props) {
  const [filter, setFilter] = useState<DecisionState | "all">("all");

  const currentByDomain = new Map(currentDomains.map((d) => [d.domain, d.count]));

  const summary = STATE_ORDER.reduce<Record<string, number>>((acc, s) => {
    acc[s] = 0;
    return acc;
  }, {});
  for (const d of Object.values(decisions)) {
    if (d.state in summary) summary[d.state]++;
  }

  const entries = Object.entries(decisions)
    .filter(([, d]) => filter === "all" || d.state === filter)
    .sort(([, a], [, b]) => {
      const ai = STATE_ORDER.indexOf(a.state);
      const bi = STATE_ORDER.indexOf(b.state);
      if (ai !== bi) return ai - bi;
      return b.decided_at.localeCompare(a.decided_at);
    });

  if (Object.keys(decisions).length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-gray-400 text-sm">
        No decisions recorded yet — actions you take will appear here.
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Summary + filter row */}
      <div className="px-4 py-3 border-b border-gray-200 flex flex-wrap gap-2 items-center shrink-0">
        <button
          onClick={() => setFilter("all")}
          className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
            filter === "all"
              ? "bg-gray-800 text-white border-gray-800"
              : "border-gray-200 text-gray-600 hover:bg-gray-50"
          }`}
        >
          All {Object.keys(decisions).length}
        </button>
        {STATE_ORDER.map((s) => {
          if (!summary[s]) return null;
          const style = STATE_STYLES[s];
          return (
            <button
              key={s}
              onClick={() => setFilter(filter === s ? "all" : s)}
              className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                filter === s
                  ? `${style.bg} ${style.text} border-current`
                  : "border-gray-200 text-gray-600 hover:bg-gray-50"
              }`}
            >
              {style.label} {summary[s]}
            </button>
          );
        })}
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-sm border-collapse">
          <thead className="sticky top-0 bg-white z-10">
            <tr className="border-b border-gray-200 text-left">
              <th className="px-3 py-2 text-xs text-gray-500 font-normal uppercase tracking-wider">Domain</th>
              <th className="px-3 py-2 text-xs text-gray-500 font-normal uppercase tracking-wider w-28">State</th>
              <th className="px-3 py-2 text-xs text-gray-500 font-normal uppercase tracking-wider w-28">Decided</th>
              <th className="px-3 py-2 text-xs text-gray-500 font-normal uppercase tracking-wider w-24 text-right">Emails then</th>
              <th className="px-3 py-2 text-xs text-gray-500 font-normal uppercase tracking-wider w-24 text-right">In inbox now</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([domain, d]) => {
              const currentCount = currentByDomain.get(domain);
              const days = daysSince(d.decided_at);
              const isBack = currentCount !== undefined && d.state !== "keep" && d.state !== "seen";
              return (
                <tr
                  key={domain}
                  className={`border-b border-gray-100 ${
                    d.state === "recidivist" ? "bg-red-50/40" : "hover:bg-gray-50"
                  }`}
                >
                  <td className="px-3 py-2 font-mono text-xs text-gray-800">{domain}</td>
                  <td className="px-3 py-2"><StateBadge state={d.state} /></td>
                  <td className="px-3 py-2 text-xs text-gray-500 tabular-nums">
                    {d.decided_at.slice(5)}
                    <span className="ml-1.5 text-gray-300">
                      {days === 0 ? "today" : `${days}d ago`}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-xs text-gray-400 tabular-nums text-right">
                    {d.email_count || "—"}
                  </td>
                  <td className="px-3 py-2 text-xs tabular-nums text-right">
                    {currentCount !== undefined ? (
                      <span className={isBack ? "text-red-600 font-medium" : "text-gray-500"}>
                        {currentCount}
                      </span>
                    ) : (
                      <span className="text-gray-300">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
