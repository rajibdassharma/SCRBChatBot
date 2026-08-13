/** Account Details -> Money Trail tab (2026-08-04).
 *
 *  Surfaces F2: what the uploaded bank statements actually say, once
 *  parsed. Until now those PDFs and spreadsheets could only be read one
 *  at a time, on the account page they were attached to.
 *
 *  VERIFIED vs UNVERIFIED IS SHOWN, NOT HIDDEN.
 *  Every statement carries its own arithmetic check — a running balance
 *  that must satisfy prev - debit + credit = balance on every row.
 *  Files that fail are still parsed and readable, but their debit and
 *  credit columns may be transposed.
 *
 *  So the rupee totals here are summed over RECONCILED statements only,
 *  and the header says so. That is not a stylistic choice: before the
 *  rule was applied, total credit read ₹111 trillion — a third of
 *  India's GDP, from 154 accounts — because 214 rows in one failed file
 *  had a currency column parsed as an amount. The correct figure is
 *  ₹1.10 billion. A number that wrong, under a heading an officer has
 *  no reason to doubt, is worse than showing nothing.
 *
 *  The shared-destination panel (one UPI handle paid by several mules)
 *  was built here and then removed on request. The endpoint still
 *  computes it behind `include_counterparties=true`, so it can come
 *  back as part of F4 without being rewritten.
 */
import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import * as XLSX from 'xlsx';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import {
  Banknote, TrendingUp, TrendingDown, Users, ArrowRightLeft,
  ShieldCheck, FileSpreadsheet, FileText,
} from 'lucide-react';
import { getMoneyTrail } from '../../lib/api/dashboard';
import { formatNumber } from '../../lib/utils/format';
import { Pager, paginate, PAGE_SIZE } from '../common/Pager';
import CaveatNote from '../common/CaveatNote';
import { stateAbbr } from '../../lib/utils/geo-tile-grid';
import type {
  MoneyTrailSummary, StatementAccountRow, MoneyTrailScope,
} from '../../types';

const C_NAVY = '#0b2c4a';
const C_RED = '#8b1919';
const C_GREEN = '#0a6b28';
const C_ORANGE = '#c67c1d';

const cardStyle = {
  background: '#fff',
  border: '1px solid rgba(0,0,0,0.06)',
  boxShadow: '0 6px 16px rgba(0,0,0,0.08)',
};

/** Indian grouping, whole rupees. 12,34,567 parses at a glance for this
 *  audience where 1,234,567 does not.
 *
 *  Paise are dropped on screen deliberately. Every figure here is a SUM
 *  over hundreds or thousands of transactions, where two decimal places
 *  are noise that costs four characters in every money column — and
 *  those four characters were what pushed the table into horizontal
 *  scrolling. The exports keep full precision: Excel receives the raw
 *  numbers, so anything that needs reconciling to the paisa is done
 *  there, not by squinting at a dashboard. */
function rupees(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  const neg = v < 0;
  const whole = Math.round(Math.abs(v)).toString();
  let out = whole;
  if (whole.length > 3) {
    const tail = whole.slice(-3);
    let head = whole.slice(0, -3);
    const parts: string[] = [];
    while (head.length > 2) {
      parts.unshift(head.slice(-2));
      head = head.slice(0, -2);
    }
    if (head) parts.unshift(head);
    out = parts.join(',') + ',' + tail;
  }
  return (neg ? '-₹' : '₹') + out;
}

/** "Jan 25" — a statement period needs the month and year, and nothing
 *  more. The full dates go to the exports. */
function shortMonth(d: string | null): string {
  if (!d) return '—';
  const dt = new Date(d);
  if (Number.isNaN(dt.getTime())) return d;
  return dt.toLocaleDateString('en-GB', { month: 'short', year: '2-digit' });
}

/** Crore/lakh shorthand for KPI cards and inline notes. */
function shortRupees(v: number): string {
  if (Math.abs(v) >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`;
  if (Math.abs(v) >= 1e5) return `₹${(v / 1e5).toFixed(1)} L`;
  return rupees(v);
}

function typePill(t: string | null) {
  if (t === 'Victim') return { background: '#e6f5eb', color: C_GREEN };
  if (t === 'Mule') return { background: '#fbe6e6', color: C_RED };
  if (t === 'Non-Mule') return { background: '#e6ecf5', color: C_NAVY };
  return { background: '#f0f0f0', color: '#444' };
}

/** A sortable column header. Rendered as a real <button> inside the
 *  <th> so it is reachable by keyboard and announced as a control —
 *  a click handler on a bare <th> is invisible to anyone not using a
 *  mouse. `aria-sort` tells a screen reader which column is active and
 *  in which direction. */
function SortTh({ label, k, dir, right, sortBy, sortDir, onSort, arrow }: {
  label: string;
  k: SortKey;
  dir: SortDir;
  right?: boolean;
  sortBy: SortKey;
  sortDir: SortDir;
  onSort: (k: SortKey, d: SortDir) => void;
  arrow: (k: SortKey) => React.ReactNode;
}) {
  const active = sortBy === k;
  return (
    <th className="px-2 py-2 text-[10px] uppercase font-bold"
      aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
      style={{ background: active ? 'rgba(255,255,255,0.10)' : undefined }}>
      <button type="button" onClick={() => onSort(k, dir)}
        title={`Sort by ${label}`}
        className={`w-full flex items-center gap-0.5 uppercase font-bold ${
          right ? 'justify-end' : 'justify-start'}`}
        style={{ color: 'inherit', cursor: 'pointer', userSelect: 'none' }}>
        <span className="truncate">{label}</span>{arrow(k)}
      </button>
    </th>
  );
}

function Kpi({ label, value, accent, sub, Icon }: {
  label: string; value: string; accent: string; sub?: string;
  Icon?: React.ComponentType<{ className?: string; style?: React.CSSProperties }>;
}) {
  return (
    <div className="rounded-2xl p-4" style={{ ...cardStyle, borderTop: `4px solid ${accent}` }}>
      <p className="text-[11px] uppercase tracking-wide font-bold flex items-center gap-1"
        style={{ color: accent }}>
        {Icon && <Icon className="w-3.5 h-3.5" />} {label}
      </p>
      <p className="text-2xl font-bold" style={{ color: C_NAVY }}>{value}</p>
      {sub && <p className="text-[11px] mt-0.5 opacity-60">{sub}</p>}
    </div>
  );
}

/** Export columns, in one place so Excel and PDF cannot disagree about
 *  what the table contained. */
const COLUMNS: { header: string; get: (a: StatementAccountRow) => string | number }[] = [
  { header: 'Account Holder', get: (a) => a.account_holder_name || '' },
  { header: 'Account No', get: (a) => a.account_no || '' },
  { header: 'Bank', get: (a) => a.bank_name || '' },
  { header: 'Type', get: (a) => a.account_type || '' },
  { header: 'FIR No', get: (a) => a.fir_no || '' },
  { header: 'Police Station', get: (a) => a.ps_name || '' },
  { header: 'District', get: (a) => a.district || '' },
  // Full name in the export, not the two-letter code. A spreadsheet
  // gets filtered and pivoted by people who never saw this screen.
  { header: 'Branch State', get: (a) => a.branch_state || '' },
  { header: 'Transactions', get: (a) => a.txns },
  { header: 'Money Out', get: (a) => a.debit },
  { header: 'Money In', get: (a) => a.credit },
  { header: 'First Txn', get: (a) => a.first_txn || '' },
  { header: 'Last Txn', get: (a) => a.last_txn || '' },
  // Carried into the export deliberately. A spreadsheet outlives the
  // screen it came from, and a row whose statement never reconciled
  // must not lose that warning on the way out.
  { header: 'Verified', get: (a) => (a.verified ? 'Yes' : 'NO — rows failed the balance check') },
  // Separate from Unchecked below, because they are separate facts.
  // Rejected means the arithmetic disagreed: the source is wrong.
  // Unchecked means there was no balance column to test against: the
  // source is silent. Collapsing them into one "not verified" column
  // would tell an analyst to distrust both equally, which is exactly
  // the judgement the split exists to let them make.
  { header: 'Rejected Txns', get: (a) => a.rejected_txns },
  // Same reason as the Verified column: the export is where these
  // numbers get pivoted by people who never saw the screen or its
  // tooltips. A zero in Money Out means something different when 1,204
  // of the rows behind it could not be checked, and only this column
  // carries that. It is a count, matching the UI — there is no
  // "Untested Amount" column anywhere, by design.
  { header: 'Unchecked Txns', get: (a) => a.untested_txns },
];

const SCOPES: { value: MoneyTrailScope; label: string }[] = [
  { value: 'all', label: 'All States' },
  { value: 'karnataka', label: 'Karnataka' },
  { value: 'other', label: 'Other States' },
];

/** Victim is offered even though the ask was framed as Mule vs
 *  Non-Mule: victim accounts exist in this data, and a two-option
 *  filter would make them unreachable rather than merely unselected. */
const TYPES = ['All', 'Mule', 'Non-Mule', 'Victim'];

/** Human label for a filter combination, used on screen AND baked into
 *  the exports. A downloaded file must say what it contains — a PDF
 *  titled "money-trail" holding only Karnataka Mule accounts is
 *  actively misleading once it leaves the browser. */
function filterLabel(scope: MoneyTrailScope, type: string): string {
  const s = SCOPES.find((x) => x.value === scope)?.label ?? 'All States';
  return `${s} · ${type === 'All' ? 'All account types' : type}`;
}

function filterSlug(scope: MoneyTrailScope, type: string): string {
  return `${scope}_${type.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
}

type SortKey = 'holder' | 'account_no' | 'type' | 'ps' | 'state' | 'txns'
             | 'debit' | 'credit' | 'period';
type SortDir = 'asc' | 'desc';

/** `onTrace` is optional so this component still renders standalone
 *  (tests, storybook, any future page). When the host provides it, the
 *  account holder becomes a link into the FIR trace. */
export function MoneyTrailTab({ onTrace }: {
  onTrace?: (firNo: string, psId: number) => void;
} = {}) {
  const [data, setData] = useState<MoneyTrailSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  // Opens on Karnataka + Mule rather than everything. This is a
  // Karnataka police dashboard and the mule accounts are the working
  // set; "All States / All Types" made the first thing on screen a
  // mixture nobody had asked to see. Both are one click away.
  //
  // Side effect worth keeping: with a state filter active the header
  // states how many accounts have no branch state recorded and are
  // therefore reachable only under All States — so the narrower default
  // does not quietly hide them.
  const [scope, setScope] = useState<MoneyTrailScope>('karnataka');
  const [acctType, setAcctType] = useState('Mule');
  // Default matches the order the server already returns, so the first
  // paint does not reshuffle under the reader.
  const [sortBy, setSortBy] = useState<SortKey>('debit');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  /** Same key -> reverse. New key -> its natural direction, because
   *  nobody wants the SMALLEST outflow first on a first click, and
   *  nobody wants names Z-to-A. */
  function onSort(key: SortKey, naturalDir: SortDir) {
    if (sortBy === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortBy(key);
      setSortDir(naturalDir);
    }
    // docs/UX.md §3.1 — the underlying order changed, so page 3 of the
    // old ordering is meaningless. Back to the top.
    setPage(0);
  }

  // Refetch on filter change rather than filtering in the browser.
  // The KPI cards above the table are computed by the server; filtering
  // client-side would leave them counting rows the table had dropped
  // (docs/UX.md §10). `alive` also guards the out-of-order response when
  // both dropdowns are changed quickly.
  useEffect(() => {
    let alive = true;
    setLoading(true);
    getMoneyTrail(scope, acctType, 20000)
      .then((d) => { if (alive) { setData(d); setLoading(false); setPage(0); } })
      .catch((e: unknown) => {
        if (!alive) return;
        setData(null);
        setLoading(false);
        toast.error(e instanceof Error ? e.message : 'Failed to load money trail');
      });
    return () => { alive = false; };
  }, [scope, acctType]);

  /** Sorted over the WHOLE dataset, never the visible page — sorting
   *  one page of 25 would just reorder an arbitrary slice and tell the
   *  reader nothing. */
  const rows = useMemo(() => {
    const all = data?.top_accounts ?? [];
    const txt = (v: string | null) => (v || '').toLowerCase();
    const cmp = (a: StatementAccountRow, b: StatementAccountRow): number => {
      let r = 0;
      switch (sortBy) {
        case 'holder': r = txt(a.account_holder_name).localeCompare(txt(b.account_holder_name)); break;
        case 'account_no': r = txt(a.account_no).localeCompare(txt(b.account_no)); break;
        case 'type': r = txt(a.account_type).localeCompare(txt(b.account_type)); break;
        case 'ps': r = txt(a.ps_name).localeCompare(txt(b.ps_name)); break;
        case 'state':
          // Blank state sinks to the bottom in both directions —
          // "not recorded" is a gap, not a state whose name starts
          // with a space, and reversing must not promote 15 empty
          // rows to the top of the screen.
          if (!a.branch_state && !b.branch_state) r = 0;
          else if (!a.branch_state) return 1;
          else if (!b.branch_state) return -1;
          else r = txt(a.branch_state).localeCompare(txt(b.branch_state));
          break;
        case 'txns': r = a.txns - b.txns; break;
        case 'credit': r = a.credit - b.credit; break;
        case 'period':
          // Accounts with no dated transaction sink to the bottom in
          // BOTH directions — "unknown" is not a small date, and
          // flipping the sort should not promote it to the top.
          if (!a.last_txn && !b.last_txn) r = 0;
          else if (!a.last_txn) return 1;
          else if (!b.last_txn) return -1;
          else r = a.last_txn.localeCompare(b.last_txn);
          break;
        default: r = a.debit - b.debit; break;
      }
      if (sortDir === 'desc') r = -r;
      // Stable tiebreak (docs/UX.md §3): without it, the many accounts
      // sharing a value — ₹0 out is common — reshuffle on every render
      // and the table appears to twitch.
      return r || a.account_id.localeCompare(b.account_id);
    };
    return [...all].sort(cmp);
  }, [data, sortBy, sortDir]);

  const maxChannel = useMemo(
    () => Math.max(1, ...(data?.channels ?? []).map((c) => c.txns)),
    [data],
  );
  const pg = paginate(rows.length, page);
  const pageRows = pg.slice(rows);

  const arrow = (key: SortKey) =>
    (sortBy === key
      ? <span className="ml-0.5 opacity-80">{sortDir === 'asc' ? '▲' : '▼'}</span>
      : null);

  /** Whole dataset, never the visible page — docs/UX.md §3.1. */
  function exportMatrix() {
    return {
      header: COLUMNS.map((c) => c.header),
      body: rows.map((a) => COLUMNS.map((c) => c.get(a))),
    };
  }

  function downloadExcel() {
    if (!rows.length) { toast.error('Nothing to export.'); return; }
    const { header, body } = exportMatrix();
    const ws = XLSX.utils.aoa_to_sheet([header, ...body]);
    ws['!cols'] = header.map((_, i) => {
      const longest = Math.max(
        String(header[i] ?? '').length,
        ...body.map((r) => String(r[i] ?? '').length),
      );
      return { wch: Math.min(40, Math.max(10, longest + 2)) };
    });
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Money Trail');
    XLSX.writeFile(wb,
      `money-trail_${filterSlug(scope, acctType)}`
      + `_${new Date().toISOString().slice(0, 10)}.xlsx`);
  }

  function downloadPdf() {
    if (!rows.length) { toast.error('Nothing to export.'); return; }
    const { header, body } = exportMatrix();
    // Landscape A3 — 13 columns will not fit A4 comfortably.
    const doc = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'a3' });
    doc.setFontSize(14);
    doc.text('Money Trail — parsed bank statements', 40, 40);
    doc.setFontSize(10);
    // Printed under the title, not left to the filename, because a
    // printed page gets photocopied away from the file it came from.
    doc.text(`Filter: ${filterLabel(scope, acctType)}`, 40, 58);
    doc.text(
      `${formatNumber(rows.length)} account${rows.length === 1 ? '' : 's'} · `
      + `${formatNumber(data?.transactions ?? 0)} transactions · `
      + `${data?.date_from ?? '—'} to ${data?.date_to ?? '—'}`, 40, 72);
    // The caveat goes on the page, not just the screen. A printed
    // report gets circulated and quoted long after anyone remembers
    // which rows were reliable.
    doc.setFontSize(8);
    doc.text(
      'Rupee totals cover statements whose balance chain reconciles. Rows marked '
      + '"Verified: NO" come from statements whose arithmetic did not agree — their '
      + 'debit and credit columns may be transposed. Treat those figures as indicative.',
      40, 88);
    autoTable(doc, {
      startY: 104,
      head: [header],
      body: body.map((r) => r.map((v, i) =>
        (COLUMNS[i].header === 'Money Out' || COLUMNS[i].header === 'Money In')
          ? rupees(Number(v)) : String(v))),
      styles: { fontSize: 7, cellPadding: 3, overflow: 'linebreak' },
      headStyles: { fillColor: [11, 44, 74] },
      alternateRowStyles: { fillColor: [245, 245, 247] },
      columnStyles: { 12: { cellWidth: 110 } },
    });
    doc.save(`money-trail_${filterSlug(scope, acctType)}`
      + `_${new Date().toISOString().slice(0, 10)}.pdf`);
  }

  if (loading) {
    return (
      <div className="text-center py-16 font-semibold" style={{ color: C_NAVY }}>
        Loading parsed statements…
      </div>
    );
  }

  if (!data || data.transactions === 0) {
    return (
      <div className="rounded-2xl p-8" style={cardStyle}>
        <p className="text-sm font-bold mb-1" style={{ color: C_NAVY }}>
          No bank statements have been parsed yet.
        </p>
        <p className="text-xs opacity-70">
          Statements are parsed by a batch job, not on upload. Ask your
          administrator to run <code>analysis/parse_statements.py</code>.
        </p>
      </div>
    );
  }

  const unverifiedFiles = data.quality.find((q) => q.status === 'unverified')?.files ?? 0;
  const scanned = data.quality.find((q) => q.status === 'scanned')?.files ?? 0;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        <Kpi label="Transactions" value={formatNumber(data.transactions)}
          accent={C_NAVY} sub="parsed from statements" Icon={ArrowRightLeft} />
        <Kpi label="Accounts covered" value={formatNumber(data.accounts_covered)}
          accent={C_NAVY} sub={`${formatNumber(data.statements_parsed)} statements`} Icon={Users} />
        <Kpi label="Money out" value={shortRupees(data.total_debit)}
          accent={C_RED} sub="reconciled files only" Icon={TrendingDown} />
        <Kpi label="Money in" value={shortRupees(data.total_credit)}
          accent={C_GREEN} sub="reconciled files only" Icon={TrendingUp} />
        {/* The sub-line carries the untested COUNT, never a rupee
            figure. Those rows are excluded from Money out / Money in
            above, so without this number the cards would read as
            complete while quietly under-reporting. Stating how many
            rows are unverifiable is honest; stating what they add up
            to would be the same unbacked claim the chain check exists
            to withhold. */}
        <Kpi label="Verified rows" value={`${data.verified_pct}%`}
          accent={data.verified_pct >= 90 ? C_GREEN : C_ORANGE}
          sub={data.untested_txns > 0
            ? `${formatNumber(data.untested_txns)} untestable`
            : 'balance chain agrees'} Icon={ShieldCheck} />
        <Kpi label="Period"
          value={data.date_from ? String(data.date_from).slice(0, 4) : '—'}
          accent={C_NAVY}
          sub={data.date_from ? `${data.date_from} → ${data.date_to}` : undefined}
          Icon={Banknote} />
      </div>

      {/* The caveat still travels with the numbers — collapsed to one
          line, expanding on click. The summary line stays visible
          because a figure whose qualification is invisible is a figure
          that gets quoted without it, and this particular figure once
          read Rs 111 trillion. */}
      <CaveatNote summary="Reconciled statements only">
        <b>Rupee totals count only statements whose own arithmetic agrees.</b>{' '}
        Every statement has a running balance, and it must satisfy
        <i> previous − debit + credit = balance </i> on every row. Files that fail
        that check are still parsed and their rows are readable, but their debit and
        credit columns may be swapped — so they are excluded from the totals above
        and flagged in the table below.
        {unverifiedFiles > 0 && (
          <> <b>{formatNumber(unverifiedFiles)}</b> statement
            {unverifiedFiles === 1 ? '' : 's'} did not reconcile.</>
        )}
        {scanned > 0 && (
          <> <b>{formatNumber(scanned)}</b> more are scanned images and need OCR
            before they can be read at all.</>
        )}
        {/* This screen shows only accounts whose statement has been
            PARSED. Without saying so, a short list here reads as
            "few accounts moved money" rather than "few statements
            have been processed" — which is how 4 Karnataka mule
            accounts got compared against 744 on the map. */}
        {' '}This tab covers only accounts whose statement has been parsed —
        see <b>Statement Coverage</b> for accounts still waiting on one.
      </CaveatNote>

      {/* ---- accounts by money out ---- */}
      <div className="rounded-2xl overflow-hidden" style={cardStyle}>
        <div className="px-5 py-4 flex items-start justify-between gap-4 flex-wrap"
          style={{ borderBottom: '3px solid var(--ksp-yellow)' }}>
          <div>
            <h3 className="text-sm font-bold" style={{ color: C_NAVY }}>
              Accounts by money out
            </h3>
            <div className="mt-1">
              <CaveatNote summary="Largest outflow first, from each account’s own statements">
                Every figure comes from the account’s own parsed statements rather
                than from any central ledger, so an account with no statement on
                file does not appear at all.
                {onTrace && ' Click an account holder to trace that FIR.'}
              </CaveatNote>
            </div>
            {/* Karnataka + Other does NOT equal All, and saying so
                is cheaper than letting an officer discover it while
                checking totals. */}
            {scope !== 'all' && (data?.accounts_without_state ?? 0) > 0 && (
              <p className="text-[11px] mt-1 opacity-70">
                {formatNumber(data?.accounts_without_state ?? 0)} account
                {(data?.accounts_without_state ?? 0) === 1 ? ' has' : 's have'} no
                branch state recorded and appear only under “All States”.
              </p>
            )}
            <p className="text-sm font-medium mt-1" style={{ color: C_RED }}>
              {rows.length === 0
                ? 'no accounts'
                : `showing ${formatNumber(pg.firstIdx + 1)}–${formatNumber(pg.lastIdx)}`
                  + ` of ${formatNumber(rows.length)} account${rows.length === 1 ? '' : 's'}`}
            </p>
            {/* accounts_covered is counted WITHOUT the row limit, so
                this compares what arrived against what exists. Silent
                truncation is the failure being guarded against: a table
                that shows 1,000 of 3,073 accounts and says nothing
                reads as the complete picture, and the export inherits
                the same lie. */}
            {data.accounts_covered > rows.length && (
              <p className="text-xs mt-1 font-semibold"
                style={{ color: C_ORANGE }}>
                ⚠ Showing the top {formatNumber(rows.length)} of{' '}
                {formatNumber(data.accounts_covered)} accounts by money out.
                The remaining {formatNumber(data.accounts_covered - rows.length)}{' '}
                are not on this page or in the export.
              </p>
            )}
          </div>
          {/* Downloads sit on top of the table header, per the pattern
              established on the PS drill-down. Both export EVERY row,
              not the page on screen. */}
          {/* justify-end keeps the downloads pinned to the right edge
              even when the filters wrap onto their own line on a narrow
              screen; without it the buttons drift left under the
              dropdowns. */}
          <div className="flex gap-2 items-center flex-wrap justify-end ml-auto">
            {/* Filters sit with the downloads, so the thing that
                changes the data and the thing that exports it are
                read together. */}
            <select value={scope}
              onChange={(e) => setScope(e.target.value as MoneyTrailScope)}
              aria-label="Filter by state"
              className="px-2 py-1.5 rounded-lg text-sm font-semibold bg-white"
              style={{ border: `2px solid ${C_NAVY}`, color: C_NAVY }}>
              {SCOPES.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <select value={acctType} onChange={(e) => setAcctType(e.target.value)}
              aria-label="Filter by account type"
              className="px-2 py-1.5 rounded-lg text-sm font-semibold bg-white"
              style={{ border: `2px solid ${C_NAVY}`, color: C_NAVY }}>
              {TYPES.map((t) => (
                <option key={t} value={t}>{t === 'All' ? 'All Types' : t}</option>
              ))}
            </select>
            <button onClick={downloadExcel} disabled={rows.length === 0}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-semibold disabled:opacity-40"
              style={{ background: C_GREEN, color: '#fff' }}>
              <FileSpreadsheet className="w-4 h-4" /> Excel
            </button>
            <button onClick={downloadPdf} disabled={rows.length === 0}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-semibold disabled:opacity-40"
              style={{ background: C_RED, color: '#fff' }}>
              <FileText className="w-4 h-4" /> PDF
            </button>
          </div>
        </div>

        {rows.length === 0 ? (
          <p className="px-5 py-10 text-center text-sm opacity-60">
            No parsed statements yet.
          </p>
        ) : (
          <>
            {/* overflow-x-auto stays as a floor, not a plan: the table
                is sized to fit, but a very long holder name on a narrow
                laptop must scroll inside this box rather than push the
                whole page sideways (docs/UX.md). */}
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left" style={{ tableLayout: 'fixed' }}>
                {/* Fixed widths, because `auto` lets one 40-character
                    business name stretch a column and squeeze the money
                    figures into wrapping. */}
                {/* ~45rem of fixed columns, leaving the holder name the
                    rest. Sized against the widest real values in the
                    corpus: an 18-digit account number and ₹9,34,10,760,
                    the largest outflow. */}
                <colgroup>
                  <col style={{ width: '2.25rem' }} />
                  <col />
                  <col style={{ width: '7.5rem' }} />
                  <col style={{ width: '4.5rem' }} />
                  <col style={{ width: '8.5rem' }} />
                  <col style={{ width: '3.25rem' }} />
                  <col style={{ width: '3.5rem' }} />
                  <col style={{ width: '6.5rem' }} />
                  <col style={{ width: '6.5rem' }} />
                  <col style={{ width: '4rem' }} />
                </colgroup>
                {/* Every column sorts except the rank, which IS the
                    current sort expressed as a number. Text columns
                    open ascending, numbers and dates descending —
                    "biggest first" is what the reader wants from a
                    money column, and A-to-Z from a name. */}
                <thead style={{ background: C_NAVY, color: 'var(--ksp-yellow)' }}>
                  <tr>
                    <th className="px-2 py-2 text-[10px] uppercase font-bold">#</th>
                    <SortTh label="Account holder" k="holder" dir="asc"
                      sortBy={sortBy} sortDir={sortDir} onSort={onSort} arrow={arrow} />
                    <SortTh label="Account no" k="account_no" dir="asc"
                      sortBy={sortBy} sortDir={sortDir} onSort={onSort} arrow={arrow} />
                    <SortTh label="Type" k="type" dir="asc"
                      sortBy={sortBy} sortDir={sortDir} onSort={onSort} arrow={arrow} />
                    <SortTh label="Police Station" k="ps" dir="asc"
                      sortBy={sortBy} sortDir={sortDir} onSort={onSort} arrow={arrow} />
                    <SortTh label="State" k="state" dir="asc"
                      sortBy={sortBy} sortDir={sortDir} onSort={onSort} arrow={arrow} />
                    <SortTh label="Txns" k="txns" dir="desc" right
                      sortBy={sortBy} sortDir={sortDir} onSort={onSort} arrow={arrow} />
                    <SortTh label="Out" k="debit" dir="desc" right
                      sortBy={sortBy} sortDir={sortDir} onSort={onSort} arrow={arrow} />
                    <SortTh label="In" k="credit" dir="desc" right
                      sortBy={sortBy} sortDir={sortDir} onSort={onSort} arrow={arrow} />
                    <SortTh label="Period" k="period" dir="desc"
                      sortBy={sortBy} sortDir={sortDir} onSort={onSort} arrow={arrow} />
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((a, i) => (
                    <tr key={a.account_id} className="border-t"
                      style={{ borderColor: 'rgba(11,44,74,0.08)' }}>
                      {/* Rank is absolute, not per-page — page 3 starts
                          at 51, so the ordering survives paging. */}
                      <td className="px-2 py-1.5 font-bold opacity-50">
                        {formatNumber(pg.firstIdx + i + 1)}
                      </td>
                      <td className="px-2 py-1.5">
                        {/* A link only when a trace is actually possible.
                            The trace keys on (FIR No, PS id) — FIR
                            numbers repeat across stations — so a row
                            missing either one would open a dead end.
                            Those rows stay plain text rather than
                            offering a link that fails on click. */}
                        {onTrace && a.fir_no && a.ps_id ? (
                          <button type="button"
                            onClick={() => onTrace(a.fir_no!, a.ps_id!)}
                            title={`Trace FIR ${a.fir_no} at ${a.ps_name ?? 'this station'}`}
                            className="font-semibold block truncate text-left w-full hover:underline"
                            style={{ color: C_NAVY, cursor: 'pointer' }}>
                            {a.account_holder_name || '—'}
                            {!a.verified && (
                              <span className="ml-1 px-1 py-px rounded text-[9px] font-bold align-middle"
                                style={{ background: 'rgba(198,124,29,0.16)', color: C_ORANGE }}
                                title={`${formatNumber(a.rejected_txns)} transaction(s) here failed the balance check and are excluded from the figures shown`}>
                                UNVER
                              </span>
                            )}
                          </button>
                        ) : (
                          <span className="font-semibold block truncate"
                            style={{ color: C_NAVY }}
                            title={a.account_holder_name || undefined}>
                            {a.account_holder_name || '—'}
                            {!a.verified && (
                              <span className="ml-1 px-1 py-px rounded text-[9px] font-bold align-middle"
                                style={{ background: 'rgba(198,124,29,0.16)', color: C_ORANGE }}
                                title={`${formatNumber(a.rejected_txns)} transaction(s) here failed the balance check and are excluded from the figures shown`}>
                                UNVER
                              </span>
                            )}
                          </span>
                        )}
                        <span className="block text-[10px] opacity-55 truncate"
                          title={`${a.bank_name || ''} · ${a.fir_no || ''}`}>
                          {a.bank_name || '—'} · {a.fir_no || 'no FIR'}
                        </span>
                      </td>
                      <td className="px-2 py-1.5 font-mono text-[11px] truncate"
                        title={a.account_no || undefined}>{a.account_no || '—'}</td>
                      <td className="px-2 py-1.5">
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-bold"
                          style={typePill(a.account_type)}>{a.account_type || '—'}</span>
                      </td>
                      <td className="px-2 py-1.5">
                        <span className="block truncate" title={a.ps_name || undefined}>
                          {a.ps_name || '—'}
                        </span>
                        <span className="block text-[10px] opacity-55 truncate">
                          {a.district || ''}
                        </span>
                      </td>
                      {/* Two-letter code, sharing the India map's
                          abbreviations rather than a second list. An
                          unrecognised value falls back to the raw
                          string — branch_state is free text, and hiding
                          a bad value would hide the data-quality
                          problem worth seeing. */}
                      <td className="px-2 py-1.5" title={a.branch_state || 'not recorded'}>
                        {a.branch_state
                          ? (stateAbbr(a.branch_state)
                              ?? <span className="truncate block">{a.branch_state}</span>)
                          : <span className="opacity-40">—</span>}
                      </td>
                      <td className="px-2 py-1.5 text-right">
                        {formatNumber(a.txns)}
                        {/* Why the money columns may read zero. An
                            account whose statement had no balance
                            column looks identical to one that never
                            moved a rupee, and an investigator should
                            react to those in opposite ways — one is a
                            dead end, the other is a parsing gap worth
                            chasing. The count sits under the txn total
                            because that is the honest unit here: we
                            know how many rows we cannot vouch for, and
                            deliberately do not total them. */}
                        {a.untested_txns > 0 && (
                          <span className="block text-[9px] font-semibold"
                            style={{ color: C_ORANGE }}
                            title={`${a.untested_txns} of these rows had no balance column to check against — their amounts are excluded from the money columns`}>
                            {formatNumber(a.untested_txns)} unchecked
                          </span>
                        )}
                      </td>
                      <td className="px-2 py-1.5 text-right font-semibold whitespace-nowrap"
                        style={{ color: C_RED }}>{rupees(a.debit)}</td>
                      <td className="px-2 py-1.5 text-right font-semibold whitespace-nowrap"
                        style={{ color: C_GREEN }}>{rupees(a.credit)}</td>
                      <td className="px-2 py-1.5 text-[10px] opacity-70 whitespace-nowrap"
                        title={`${a.first_txn || ''} to ${a.last_txn || ''}`}>
                        {shortMonth(a.first_txn)}<br />{shortMonth(a.last_txn)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager total={rows.length} page={pg.safePage} pageCount={pg.pageCount}
              onPage={setPage} noun="accounts" size={PAGE_SIZE} />
          </>
        )}
      </div>

      {/* ---- channel mix ---- */}
      <div className="rounded-2xl overflow-hidden" style={cardStyle}>
        <div className="px-5 py-4" style={{ borderBottom: '3px solid var(--ksp-yellow)' }}>
          <h3 className="text-sm font-bold" style={{ color: C_NAVY }}>How money moved</h3>
          <div className="mt-1">
            <CaveatNote summary="Channel is read from narration text, not a column">
              Banks do not label the channel, so it is inferred from the narration.
              “Not identified” means the narration carried no recognisable marker;
              the transaction is still counted.
            </CaveatNote>
          </div>
        </div>
        <div className="p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-2">
          {data.channels.map((c) => (
            <div key={c.channel}>
              <div className="flex justify-between text-xs mb-0.5">
                <span className="font-semibold" style={{ color: C_NAVY }}>{c.channel}</span>
                <span className="opacity-70">
                  {formatNumber(c.txns)} · {shortRupees(c.debit)} out
                </span>
              </div>
              <div className="h-2 rounded-full overflow-hidden"
                style={{ background: 'rgba(11,44,74,0.08)' }}>
                <div className="h-full rounded-full"
                  style={{
                    width: `${Math.max(2, (c.txns / maxChannel) * 100)}%`,
                    background: c.channel === 'Not identified'
                      ? 'rgba(11,44,74,0.25)' : C_NAVY,
                  }} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
