/** The one pagination control (docs/UX.md §3.1).
 *
 *  Extracted from AccountsPsDetailPanel so a second paginated table
 *  cannot quietly invent a second set of rules. The standard is 25 rows
 *  a page, a "showing 1–25 of 312" line above the table, and First /
 *  Prev / 5 numbered pages / Next / Last below it.
 *
 *  Two behaviours here are corrections of bugs, not preferences:
 *
 *    - The page index is CLAMPED, never trusted. Changing a filter can
 *      shrink the result set while the index still points past the end,
 *      which renders an empty table on a page that has data.
 *    - The pager is hidden entirely on a single page. Controls that can
 *      only do nothing are noise.
 *
 *  Exports are deliberately NOT wired in here. A download is always the
 *  whole dataset, never the page on screen, so it has nothing to do
 *  with pagination state.
 */

export const PAGE_SIZE = 25;

/** Clamped paging maths for `total` rows. Call with the raw page index
 *  from state; use the returned `safePage` for everything. */
export function paginate(total: number, page: number, size: number = PAGE_SIZE) {
  const pageCount = Math.max(1, Math.ceil(total / size));
  const safePage = Math.min(Math.max(0, page), pageCount - 1);
  const firstIdx = safePage * size;
  return {
    pageCount,
    safePage,
    firstIdx,
    lastIdx: Math.min(firstIdx + size, total),
    slice<T>(rows: T[]): T[] { return rows.slice(firstIdx, firstIdx + size); },
  };
}

/** Up to 5 page numbers centred on the current page. 400 rows is 16
 *  pages — rendering every number turns the pager into its own
 *  scrolling problem. */
export function pageWindow(current: number, total: number): number[] {
  const span = Math.min(5, total);
  let start = Math.max(0, current - Math.floor(span / 2));
  if (start + span > total) start = total - span;
  return Array.from({ length: span }, (_, i) => start + i);
}

function PagerBtn({ label, disabled, onClick }: {
  label: string; disabled: boolean; onClick: () => void;
}) {
  return (
    <button type="button" onClick={onClick} disabled={disabled}
      className="px-2.5 py-1 rounded-lg text-xs font-bold disabled:opacity-35"
      style={{ background: '#fff', color: 'var(--ksp-navy)',
               border: '1px solid rgba(11,44,74,0.20)' }}>
      {label}
    </button>
  );
}

export function Pager({ total, page, pageCount, onPage, noun = 'rows', size = PAGE_SIZE }: {
  total: number;
  page: number;
  pageCount: number;
  onPage: (p: number) => void;
  noun?: string;
  size?: number;
}) {
  if (pageCount <= 1) return null;
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3 flex-wrap"
      style={{ borderTop: '1px solid rgba(11,44,74,0.10)', background: '#fafbfd' }}>
      <span className="text-xs font-semibold" style={{ color: 'var(--ksp-navy)' }}>
        Page {page + 1} of {pageCount}
        <span className="opacity-60 font-normal">
          {'  ·  '}{total.toLocaleString('en-IN')} {noun}, {size} per page
        </span>
      </span>
      <div className="flex items-center gap-1">
        <PagerBtn label="First" disabled={page === 0} onClick={() => onPage(0)} />
        <PagerBtn label="Prev" disabled={page === 0} onClick={() => onPage(page - 1)} />
        {pageWindow(page, pageCount).map((n) => (
          <button key={n} type="button" onClick={() => onPage(n)}
            className="px-2.5 py-1 rounded-lg text-xs font-bold min-w-[30px]"
            style={n === page
              ? { background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }
              : { background: '#fff', color: 'var(--ksp-navy)',
                  border: '1px solid rgba(11,44,74,0.20)' }}>
            {n + 1}
          </button>
        ))}
        <PagerBtn label="Next" disabled={page >= pageCount - 1}
          onClick={() => onPage(page + 1)} />
        <PagerBtn label="Last" disabled={page >= pageCount - 1}
          onClick={() => onPage(pageCount - 1)} />
      </div>
    </div>
  );
}
