import type { ReactNode } from "react";

interface Props {
  content: ReactNode;
  children: ReactNode;
  /** "top" opens above (default), "bottom" opens below — use "bottom" on sticky headers */
  side?: "top" | "bottom";
  width?: string;
}

export function Tooltip({ content, children, side = "top", width = "w-64" }: Props) {
  const posClass =
    side === "bottom"
      ? "top-full mt-1.5"
      : "bottom-full mb-1.5";

  return (
    <span className="relative group/tip inline-flex items-center">
      {children}
      <span
        className={`absolute ${posClass} left-0 ${width} hidden group-hover/tip:block p-2.5 text-xs text-gray-700 bg-white border border-gray-200 rounded-md shadow-xl z-50 leading-relaxed pointer-events-none whitespace-normal font-normal normal-case tracking-normal`}
      >
        {content}
      </span>
    </span>
  );
}

/** Small ⓘ icon that carries the tooltip — use inline next to a label */
export function InfoTip({ content, side }: { content: ReactNode; side?: "top" | "bottom" }) {
  return (
    <Tooltip content={content} side={side}>
      <span className="ml-1 text-gray-300 hover:text-gray-500 cursor-default select-none text-[10px]">
        ⓘ
      </span>
    </Tooltip>
  );
}
