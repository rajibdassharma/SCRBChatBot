import { useState, type ReactNode } from 'react';
import { Info, X } from 'lucide-react';

const C_NAVY = 'var(--ksp-navy)';
const C_ORANGE = '#c67c1d';

interface Props {
  /** One short line, always visible. Keep it to a few words. */
  summary: string;
  /** The full explanation, shown only after the reader asks for it. */
  children: ReactNode;
}

/**
 * A qualification on the numbers above it, collapsed to one line.
 *
 * WHY IT IS COLLAPSED AND NOT DELETED
 * -----------------------------------
 * These panels were full paragraphs, and on a dashboard with ten tabs
 * they cost real vertical space on every visit — for text an officer
 * reads once and then scrolls past forever.
 *
 * But they cannot simply go. The Money Trail caveat exists because
 * total credit once read Rs 111 trillion — a third of India's GDP,
 * from 154 accounts — when a currency column was parsed as an amount.
 * The Crypto one exists because a substring match reported 168 "OKX"
 * transactions that were men called Ashok. A figure whose
 * qualification is invisible is a figure that gets quoted without it.
 *
 * So the SUMMARY line always shows: it takes one line, and it carries
 * the fact that a qualification exists. The reasoning expands on
 * click. What is hidden is the explanation, never the caveat.
 */
export default function CaveatNote({ summary, children }: Props) {
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)}
        aria-expanded={false}
        title="Why these figures are qualified — click to read"
        className="flex items-center gap-1.5 text-[11px] font-semibold px-2 py-1 rounded-lg transition hover:opacity-80"
        style={{ color: C_ORANGE, background: 'rgba(198,124,29,0.10)',
                 border: '1px solid rgba(198,124,29,0.28)' }}>
        <Info className="w-3.5 h-3.5 shrink-0" />
        {summary}
        <span className="opacity-60 font-normal">— why?</span>
      </button>
    );
  }

  return (
    <div className="rounded-xl px-4 py-3 flex items-start gap-2 relative"
      style={{ background: 'rgba(198,124,29,0.10)', border: '1px solid rgba(198,124,29,0.35)' }}>
      <Info className="w-4 h-4 mt-0.5 shrink-0" style={{ color: C_ORANGE }} />
      <div className="text-xs pr-6" style={{ color: C_NAVY }}>{children}</div>
      <button type="button" onClick={() => setOpen(false)}
        aria-expanded aria-label="Hide explanation"
        className="absolute top-2 right-2 p-1 rounded hover:opacity-70"
        style={{ color: C_ORANGE }}>
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
