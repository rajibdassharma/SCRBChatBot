import type { LucideIcon } from 'lucide-react';

/** One selectable tab. `group` is the heading it sits under. */
export interface TabDef<T extends string> {
  id: T;
  label: string;
  icon?: LucideIcon;
  group: string;
  /** Small count/badge — e.g. a finding count worth surfacing before the click. */
  badge?: number;
}

interface Props<T extends string> {
  tabs: TabDef<T>[];
  active: T;
  onChange: (id: T) => void;
}

/**
 * Grouped tab bar for dashboards that have outgrown a single row.
 *
 * WHY GROUPED RATHER THAN A LONGER ROW
 * ------------------------------------
 * The Accounts dashboard reached ten tabs. As one flat row they are a
 * wall of equally-weighted words: "Overview, Map View, Deep Analysis,
 * Graphical Analysis, Repeat Accounts, Duplicate IDs, Money Trail,
 * Statement Coverage, Mule Network, Crypto Analysis". Nothing tells an
 * officer that four of those read uploaded bank statements and two are
 * about where accounts physically are.
 *
 * The groups carry that. "Statements" says plainly that everything
 * under it depends on parsed uploads — which matters, because those
 * tabs go blank or partial when parsing is behind, and the others do
 * not.
 *
 * WHY THIS IS DATA-DRIVEN
 * -----------------------
 * The previous version repeated a ten-line button per tab with the
 * active-state colours inlined three times each — about ninety lines
 * that had to be copied correctly to add one tab. Adding the tenth was
 * what made the pattern untenable rather than merely repetitive.
 */
export default function TabBar<T extends string>({ tabs, active, onChange }: Props<T>) {
  // Preserve declaration order rather than sorting: the order tabs are
  // written in is the order an investigation actually moves through.
  const groups: { name: string; items: TabDef<T>[] }[] = [];
  for (const t of tabs) {
    const last = groups[groups.length - 1];
    if (last && last.name === t.group) last.items.push(t);
    else groups.push({ name: t.group, items: [t] });
  }

  return (
    <div className="flex flex-wrap items-end gap-x-5 gap-y-2 mb-3 pb-2"
      style={{ borderBottom: '2px solid rgba(11,44,74,0.12)' }}>
      {groups.map((g) => (
        <div key={g.name} className="flex flex-col gap-1">
          {/* Maroon, not muted grey. These labels are the only thing
              telling an officer that the "Bank Statements Analysis"
              tabs depend on parsed uploads — so they are partial while
              parsing is behind and blank on a fresh corpus, unlike the
              others. A label carrying that had no business being the
              faintest text on the screen. */}
          <span className="text-[11px] font-bold uppercase tracking-wider px-1 leading-none"
            style={{ color: 'var(--ksp-red)' }}>
            {g.name}
          </span>
          <div className="flex gap-1.5">
            {g.items.map((t) => {
              const on = t.id === active;
              const Icon = t.icon;
              return (
                <button key={t.id} type="button"
                  onClick={() => onChange(t.id)}
                  aria-current={on ? 'page' : undefined}
                  title={t.label}
                  className="px-3 py-1.5 text-xs font-bold rounded-lg transition flex items-center gap-1.5 whitespace-nowrap"
                  style={{
                    background: on ? 'var(--ksp-navy)' : '#fff',
                    color: on ? 'var(--ksp-yellow)' : 'var(--ksp-navy)',
                    border: on
                      ? '1px solid var(--ksp-navy)'
                      : '1px solid rgba(11,44,74,0.18)',
                    boxShadow: on ? '0 2px 6px rgba(11,44,74,0.28)' : 'none',
                  }}>
                  {Icon && <Icon className="w-3.5 h-3.5" />}
                  {t.label}
                  {/* Rendered only when > 0. A "0" badge is noise: it
                      draws the eye to a tab with nothing in it. */}
                  {t.badge != null && t.badge > 0 && (
                    <span className="px-1.5 rounded-full text-[10px] font-bold"
                      style={{
                        background: on ? 'var(--ksp-yellow)' : 'rgba(11,44,74,0.10)',
                        color: on ? 'var(--ksp-navy)' : 'var(--ksp-navy)',
                      }}>
                      {t.badge > 999 ? '999+' : t.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
