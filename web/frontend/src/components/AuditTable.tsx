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

function DomainFavicon({ domain }: { domain: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return (
      <div className="w-4 h-4 rounded-sm bg-gray-200 shrink-0 flex items-center justify-center">
        <span className="text-[8px] text-gray-400 font-bold leading-none">
          {domain[0]?.toUpperCase() ?? "?"}
        </span>
      </div>
    );
  }
  return (
    <img
      src={`https://www.google.com/s2/favicons?domain=${domain}&sz=32`}
      alt=""
      width={16}
      height={16}
      className="w-4 h-4 rounded-sm shrink-0"
      onError={() => setFailed(true)}
    />
  );
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffDays = Math.floor(diffMs / 86400000);
  if (diffDays === 0) return "today";
  if (diffDays === 1) return "yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
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
  onArchiveNow: (domain: string) => void;
  onUnsubscribe: (domain: string) => void;
  onSetAutoArchive: (domain: string) => void;
  onUnsetAutoArchive: (domain: string) => void;
  onClassifyManual: (domain: string, category: CategoryName) => void;
  actionLoading: boolean;
}

export function AuditTable({
  domains,
  selected,
  onToggle,
  onToggleAll,
  allSelected,
  onArchiveNow,
  onUnsubscribe,
  onSetAutoArchive,
  onUnsetAutoArchive,
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

          <th className="px-2 py-2 text-xs text-gray-500 font-normal uppercase tracking-wider w-52">
            Domain
          </th>

          <th className="px-2 py-2 text-xs text-gray-500 font-normal uppercase tracking-wider">
            Latest message
          </th>

          <th className="px-2 py-2 text-xs text-gray-500 font-normal uppercase tracking-wider w-24">
            Category
          </th>

          <th className="px-2 py-2 text-xs text-gray-500 font-normal uppercase tracking-wider w-28">
            <Tooltip side="bottom" content={
              <>
                <strong>Status</strong> — what's already been done for this domain:
                <br /><span className="font-medium">auto-arch MM-DD</span> — set to auto-archive on that date.
                <br /><span className="font-medium">unsub-watch</span> — unsubscribe pending; if mail keeps arriving it becomes recidivist.
              </>
            }>
              <span className="cursor-default">Status</span>
            </Tooltip>
          </th>

          <th className="px-2 py-2 text-xs text-gray-500 font-normal uppercase tracking-wider w-32">
            Settings
          </th>

          <th className="px-2 py-2 w-28" />
        </tr>
      </thead>
      <tbody>
        {domains.map((d) => {
          const isSelected = selected.has(d.domain);
          const isExpanded = expanded.has(d.domain);
          const cls = d.classification;
          const latestEmail = d.emails[0];

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
                <td className="px-2 py-2.5" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => onToggle(d.domain)}
                    className="block"
                  />
                </td>

                {/* Domain — favicon + name + count */}
                <td className="px-2 py-2.5">
                  <div className="flex items-center gap-2">
                    <button
                      onClick={(e) => { e.stopPropagation(); toggleExpand(d.domain); }}
                      className="text-gray-300 hover:text-gray-500 w-3 shrink-0 text-xs"
                    >
                      {isExpanded ? "▾" : "▸"}
                    </button>
                    <DomainFavicon domain={d.domain} />
                    <span className="text-gray-800 font-mono text-xs truncate">{d.domain}</span>
                    <span className="text-xs text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded tabular-nums shrink-0">
                      {d.count}
                    </span>
                  </div>
                </td>

                {/* Latest message — subject + date */}
                <td className="px-2 py-2.5 min-w-0">
                  {latestEmail ? (
                    <div className="flex items-baseline gap-3 min-w-0">
                      <span className="text-gray-600 text-xs truncate flex-1 min-w-0">
                        {latestEmail.subject || <span className="text-gray-300 italic">no subject</span>}
                      </span>
                      {latestEmail.date && (
                        <span className="text-gray-400 text-xs shrink-0 tabular-nums">
                          {formatDate(latestEmail.date)}
                        </span>
                      )}
                    </div>
                  ) : (
                    <span className="text-gray-300 text-xs italic">—</span>
                  )}
                </td>

                {/* Category */}
                <td className="px-2 py-2.5">
                  <div className="flex items-center gap-1.5">
                    <EditableCategoryBadge
                      category={cls?.category}
                      source={cls?.source}
                      onSave={(cat) => onClassifyManual(d.domain, cat)}
                    />
                  </div>
                </td>

                {/* Status */}
                <td className="px-2 py-2.5">
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

                {/* Settings — auto-archive toggle */}
                <td className="px-2 py-2.5" onClick={(e) => e.stopPropagation()}>
                  <ToggleSwitch
                    checked={d.archived}
                    onChange={() => d.archived ? onUnsetAutoArchive(d.domain) : onSetAutoArchive(d.domain)}
                    label="Auto-archive"
                    disabled={actionLoading}
                    tooltip={d.archived
                      ? "Auto-archive is ON — this domain will be caught by future auto-archive runs. Toggle off to remove."
                      : "Auto-archive is OFF — toggle on to include in auto-archive runs."
                    }
                  />
                </td>

                {/* Row actions */}
                <td className="px-2 py-2.5 text-right" onClick={(e) => e.stopPropagation()}>
                  <div className="flex justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <RowActions
                      domain={d.domain}
                      onArchiveNow={onArchiveNow}
                      onUnsubscribe={onUnsubscribe}
                      disabled={actionLoading}
                    />
                  </div>
                </td>
              </tr>

              {/* Expanded — remaining subjects + reasoning */}
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
                          {e.date && (
                            <span className="text-gray-400 shrink-0 ml-auto tabular-nums">{formatDate(e.date)}</span>
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

function RowActions({
  domain,
  onArchiveNow,
  onUnsubscribe,
  disabled,
}: {
  domain: string;
  onArchiveNow: (d: string) => void;
  onUnsubscribe: (d: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="flex gap-1">
      <button
        onClick={() => onArchiveNow(domain)}
        disabled={disabled}
        title="Move all current emails from this domain out of your inbox — one-time cleanup. Does not affect future mail."
        className="text-xs px-2 py-1 rounded bg-gray-50 hover:bg-gray-100 text-gray-600 border border-gray-200 disabled:opacity-40"
      >
        Archive
      </button>
      <button
        onClick={() => onUnsubscribe(domain)}
        disabled={disabled}
        title="Find the List-Unsubscribe header in the most recent email. Attempts a one-click HTTP POST (RFC 8058) if supported, otherwise opens the unsubscribe URL in your browser."
        className="text-xs px-2 py-1 rounded bg-violet-50 hover:bg-violet-100 text-violet-700 border border-violet-200 disabled:opacity-40"
      >
        Unsub
      </button>
    </div>
  );
}
