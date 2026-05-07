import { useState, Fragment, useRef, useEffect } from "react";
import type { Domain, CategoryName, DecisionState } from "../types";
import { Tooltip } from "./Tooltip";

const CATEGORY_STYLES: Record<CategoryName, { bg: string; text: string; label: string }> = {
  receipt:      { bg: "bg-blue-50",    text: "text-blue-700",    label: "receipt" },
  newsletter:   { bg: "bg-violet-50",  text: "text-violet-700",  label: "newsletter" },
  promotion:    { bg: "bg-amber-50",   text: "text-amber-700",   label: "promo" },
  notification: { bg: "bg-emerald-50", text: "text-emerald-700", label: "notif" },
  unknown:      { bg: "bg-gray-100",   text: "text-gray-500",    label: "unknown" },
};

const ALL_CATEGORIES: CategoryName[] = ["receipt", "newsletter", "promotion", "notification", "unknown"];

function EditableCategoryBadge({
  category,
  source,
  onSave,
}: {
  category?: CategoryName;
  source?: string;
  onSave: (cat: CategoryName) => void;
}) {
  const [editing, setEditing] = useState(false);
  const selectRef = useRef<HTMLSelectElement>(null);

  useEffect(() => {
    if (editing) selectRef.current?.focus();
  }, [editing]);

  const cat = category ?? "unknown";
  const s = CATEGORY_STYLES[cat];

  if (editing) {
    return (
      <select
        ref={selectRef}
        defaultValue={cat}
        onChange={(e) => {
          onSave(e.target.value as CategoryName);
          setEditing(false);
        }}
        onBlur={() => setEditing(false)}
        onClick={(e) => e.stopPropagation()}
        className="text-xs border border-gray-300 rounded px-1 py-0.5 bg-white text-gray-700 outline-none"
      >
        {ALL_CATEGORIES.map((c) => (
          <option key={c} value={c}>{c}</option>
        ))}
      </select>
    );
  }

  return (
    <button
      onClick={(e) => { e.stopPropagation(); setEditing(true); }}
      title="Click to override category"
      className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-xs ${s.bg} ${s.text} hover:ring-1 hover:ring-inset hover:ring-current`}
    >
      {s.label}
      {source === "manual" && <span className="opacity-50 text-[9px]">✎</span>}
      {source === "llm" && <span className="opacity-50 text-[9px]">⚡</span>}
    </button>
  );
}

function ConfidenceBar({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence);
  const color =
    pct >= 80 ? "bg-emerald-500" :
    pct >= 60 ? "bg-blue-500" :
    pct >= 40 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-16 h-1 bg-gray-200 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-gray-500 text-xs w-7 tabular-nums">{pct}%</span>
    </div>
  );
}

const DECISION_STYLES: Record<DecisionState, { bg: string; text: string; label: string }> = {
  recidivist:    { bg: "bg-red-50",     text: "text-red-700",     label: "recidivist" },
  unsub_pending: { bg: "bg-violet-50",  text: "text-violet-700",  label: "unsub-watch" },
  seen:          { bg: "bg-gray-100",   text: "text-gray-500",    label: "seen" },
  archived:      { bg: "bg-amber-50",   text: "text-amber-700",   label: "auto-arch" },
  keep:          { bg: "bg-emerald-50", text: "text-emerald-700", label: "keep" },
};

function DecisionBadge({ state, date }: { state: DecisionState; date: string }) {
  const s = DECISION_STYLES[state];
  const mmdd = date.slice(5);
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs ${s.bg} ${s.text}`}>
      {s.label}
      <span className="opacity-60">{mmdd}</span>
    </span>
  );
}

function TierBadge({ tier }: { tier?: string | null }) {
  if (!tier) return null;
  const styles =
    tier === "high"   ? "text-emerald-700" :
    tier === "medium" ? "text-amber-700"   : "text-gray-400";
  return <span className={`text-xs ${styles}`}>{tier}</span>;
}

function ToggleSwitch({
  checked,
  onChange,
  label,
  disabled,
  tooltip,
}: {
  checked: boolean;
  onChange: () => void;
  label: string;
  disabled?: boolean;
  tooltip?: string;
}) {
  const el = (
    <button
      role="switch"
      aria-checked={checked}
      onClick={(e) => { e.stopPropagation(); onChange(); }}
      disabled={disabled}
      className="flex items-center gap-1.5 disabled:opacity-40 cursor-pointer"
    >
      <div className={`relative w-6 h-3.5 rounded-full transition-colors shrink-0 ${
        checked ? "bg-emerald-500" : "bg-gray-200"
      }`}>
        <div className={`absolute top-0.5 w-2.5 h-2.5 rounded-full bg-white shadow-sm transition-transform ${
          checked ? "translate-x-2.5" : "translate-x-0.5"
        }`} />
      </div>
      <span className={`text-xs whitespace-nowrap ${checked ? "text-emerald-700" : "text-gray-400"}`}>
        {label}
      </span>
    </button>
  );

  if (tooltip) {
    return <Tooltip content={tooltip}>{el}</Tooltip>;
  }
  return el;
}

interface Props {
  domains: Domain[];
  selected: Set<string>;
  onToggle: (domain: string) => void;
  onToggleAll: () => void;
  allSelected: boolean;
  onClear: (domain: string) => void;
  onArchive: (domain: string) => void;
  onUnsubscribe: (domain: string) => void;
  onBoth: (domain: string) => void;
  onKeep: (domain: string) => void;
  onUnkeep: (domain: string) => void;
  onNoUnsub: (domain: string) => void;
  onUnNoUnsub: (domain: string) => void;
  onClassifyManual: (domain: string, category: CategoryName) => void;
  actionLoading: boolean;
}

export function AuditTable({
  domains,
  selected,
  onToggle,
  onToggleAll,
  allSelected,
  onClear,
  onArchive,
  onUnsubscribe,
  onBoth,
  onKeep,
  onUnkeep,
  onNoUnsub,
  onUnNoUnsub,
  onClassifyManual,
  actionLoading,
}: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  function toggleExpand(domain: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(domain) ? next.delete(domain) : next.add(domain);
      return next;
    });
  }

  if (domains.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-gray-400 text-sm">
        No domains in this category.
      </div>
    );
  }

  return (
    <table className="w-full text-sm border-collapse">
      <thead className="sticky top-0 z-10 bg-white">
        <tr className="border-b border-gray-200 text-left">
          <th className="px-2 py-2 w-8">
            <input type="checkbox" checked={allSelected} onChange={onToggleAll} className="block" />
          </th>

          <th className="px-2 py-2 text-xs text-gray-500 font-normal uppercase tracking-wider">
            Domain
          </th>

          <th className="px-2 py-2 text-xs text-gray-500 font-normal uppercase tracking-wider w-28">
            Category
          </th>

          <th className="px-2 py-2 text-xs text-gray-500 font-normal uppercase tracking-wider w-36">
            <Tooltip side="bottom" content={
              <>
                <strong>Status</strong> — what's already been done for this domain:
                <br /><span className="font-medium">auto-arch MM-DD</span> — archived on that date.
                <br /><span className="font-medium">unsub-watch</span> — unsubscribe pending; if mail keeps arriving it becomes recidivist.
              </>
            }>
              <span className="cursor-default">Status</span>
            </Tooltip>
          </th>

          <th className="px-2 py-2 text-xs text-gray-500 font-normal uppercase tracking-wider w-28">
            <Tooltip side="bottom" content="Classifier confidence score (0–100%). Red bar = low confidence.">
              <span className="cursor-default">Confidence</span>
            </Tooltip>
          </th>

          <th className="px-2 py-2 text-xs text-gray-500 font-normal uppercase tracking-wider w-48">
            Settings
          </th>

          <th className="px-2 py-2 w-36" />
        </tr>
      </thead>
      <tbody>
        {domains.map((d) => {
          const isSelected = selected.has(d.domain);
          const isExpanded = expanded.has(d.domain);
          const cls = d.classification;

          return (
            <Fragment key={d.domain}>
              <tr
                className={`border-b cursor-pointer transition-colors group ${
                  isSelected
                    ? "bg-indigo-50 border-indigo-100"
                    : "border-gray-100 hover:bg-gray-50"
                }`}
                onClick={() => onToggle(d.domain)}
              >
                {/* Checkbox */}
                <td className="px-2 py-2" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => onToggle(d.domain)}
                    className="block"
                  />
                </td>

                {/* Domain */}
                <td className="px-2 py-2">
                  <div className="flex items-center gap-2">
                    <button
                      onClick={(e) => { e.stopPropagation(); toggleExpand(d.domain); }}
                      className="text-gray-300 hover:text-gray-500 w-3 shrink-0 text-xs"
                    >
                      {isExpanded ? "▾" : "▸"}
                    </button>
                    <span className="text-gray-800 font-mono text-xs">{d.domain}</span>
                    <span className="text-xs text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded tabular-nums">
                      {d.count}
                    </span>
                  </div>
                </td>

                {/* Category */}
                <td className="px-2 py-2">
                  <div className="flex items-center gap-2">
                    <EditableCategoryBadge
                      category={cls?.category}
                      source={cls?.source}
                      onSave={(cat) => onClassifyManual(d.domain, cat)}
                    />
                    {cls?.tier && <TierBadge tier={cls.tier} />}
                  </div>
                </td>

                {/* Status */}
                <td className="px-2 py-2">
                  <div className="flex flex-wrap gap-1">
                    {d.decision ? (
                      <DecisionBadge state={d.decision.state} date={d.decision.decided_at} />
                    ) : d.archived ? (
                      <span className="text-xs px-1.5 py-0.5 rounded bg-amber-50 text-amber-700">
                        auto-arch
                      </span>
                    ) : null}
                  </div>
                </td>

                {/* Confidence */}
                <td className="px-2 py-2">
                  <ConfidenceBar confidence={cls?.confidence ?? 0} />
                </td>

                {/* Settings — toggle switches */}
                <td className="px-2 py-2" onClick={(e) => e.stopPropagation()}>
                  <div className="flex flex-col gap-1.5">
                    <ToggleSwitch
                      checked={d.keep}
                      onChange={() => d.keep ? onUnkeep(d.domain) : onKeep(d.domain)}
                      label="Never auto-archive"
                      disabled={actionLoading}
                      tooltip={d.keep
                        ? "ON — this domain bypasses auto-archive. Toggle off to remove from keep list."
                        : "OFF — toggle on to add to keep list. Mail from this domain will never be auto-archived."
                      }
                    />
                    <ToggleSwitch
                      checked={d.no_unsub}
                      onChange={() => d.no_unsub ? onUnNoUnsub(d.domain) : onNoUnsub(d.domain)}
                      label="Skip unsub"
                      disabled={actionLoading}
                      tooltip={d.no_unsub
                        ? "ON — unsubscribe actions are skipped for this domain. Toggle off to allow."
                        : "OFF — toggle on to skip unsubscribe for this domain (e.g. accounts you want to keep receiving but can't unsubscribe from)."
                      }
                    />
                  </div>
                </td>

                {/* Row actions — one-time operations only */}
                <td className="px-2 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                  <div className="flex justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <RowActions
                      domain={d.domain}
                      isKeep={d.keep}
                      isNoUnsub={d.no_unsub}
                      onClear={onClear}
                      onArchive={onArchive}
                      onUnsubscribe={onUnsubscribe}
                      onBoth={onBoth}
                      disabled={actionLoading}
                    />
                  </div>
                </td>
              </tr>

              {/* Expanded — sample subjects + reasoning */}
              {isExpanded && (
                <tr className={`border-b ${isSelected ? "bg-indigo-50/60 border-indigo-100" : "bg-gray-50 border-gray-100"}`}>
                  <td colSpan={7} className="px-10 py-2.5">
                    <div className="space-y-1">
                      {d.emails.map((e, i) => (
                        <div key={i} className="flex gap-2 text-xs">
                          <span className="text-gray-400 shrink-0 truncate max-w-[200px]">{e.sender}</span>
                          {e.subject && (
                            <>
                              <span className="text-gray-300">—</span>
                              <span className="text-gray-600 truncate">{e.subject}</span>
                            </>
                          )}
                        </div>
                      ))}
                    </div>
                    {cls?.reasoning && (
                      <p className="mt-2 text-xs text-gray-400 italic">{cls.reasoning}</p>
                    )}
                  </td>
                </tr>
              )}
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
}

const ROW_ACTION_TIPS = {
  clear: "Clear: removes all current emails from this domain from your INBOX — one-time cleanup. Does not add to any list; future mail is unaffected.",
  arc: "Archive: removes all emails from INBOX AND adds this domain to your auto-archive list. Future mail from this domain will be caught by Auto-archive.",
  unsub: "Unsubscribe: finds the List-Unsubscribe header in the most recent email. Attempts a one-click HTTP POST (RFC 8058) if supported, otherwise opens the unsubscribe URL in your browser.",
  both: "Both: archives (permanent) AND unsubscribes simultaneously.",
};

function RowActions({
  domain,
  isKeep,
  isNoUnsub,
  onClear,
  onArchive,
  onUnsubscribe,
  onBoth,
  disabled,
}: {
  domain: string;
  isKeep: boolean;
  isNoUnsub: boolean;
  onClear: (d: string) => void;
  onArchive: (d: string) => void;
  onUnsubscribe: (d: string) => void;
  onBoth: (d: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="flex gap-1">
      <button
        onClick={() => onClear(domain)}
        disabled={disabled || isKeep}
        title={ROW_ACTION_TIPS.clear}
        className="text-xs px-2 py-1 rounded bg-gray-50 hover:bg-gray-100 text-gray-600 border border-gray-200 disabled:opacity-40"
      >
        clear
      </button>
      <button
        onClick={() => onArchive(domain)}
        disabled={disabled || isKeep}
        title={ROW_ACTION_TIPS.arc}
        className="text-xs px-2 py-1 rounded bg-amber-50 hover:bg-amber-100 text-amber-700 border border-amber-200 disabled:opacity-40"
      >
        arc
      </button>
      <button
        onClick={() => onUnsubscribe(domain)}
        disabled={disabled || isNoUnsub}
        title={ROW_ACTION_TIPS.unsub}
        className="text-xs px-2 py-1 rounded bg-violet-50 hover:bg-violet-100 text-violet-700 border border-violet-200 disabled:opacity-40"
      >
        unsub
      </button>
      <button
        onClick={() => onBoth(domain)}
        disabled={disabled || isKeep || isNoUnsub}
        title={ROW_ACTION_TIPS.both}
        className="text-xs px-2 py-1 rounded bg-red-50 hover:bg-red-100 text-red-700 border border-red-200 disabled:opacity-40"
      >
        both
      </button>
    </div>
  );
}
