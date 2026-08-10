/** Account Details -> Statement Coverage tab (2026-08-04).
 *
 *  Which accounts still have no usable bank statement — a chasing list,
 *  not an analysis. The Excel/PDF export is the point: it is what gets
 *  handed to a bank nodal officer.
 *
 *  WHY THIS SCREEN EXISTS
 *  ----------------------
 *  Money Trail showed 4 Karnataka mule accounts while the map showed
 *  744, and nothing on either screen explained the difference. It was
 *  not that 740 accounts had no money movement — their statements
 *  simply had not been parsed yet. A dashboard that cannot state what
 *  it is missing invites exactly that misreading, and the misreading
 *  here would be "these accounts are clean".
 *
 *  FOUR STATES, NOT ONE "MISSING"
 *  ------------------------------
 *    missing     no file attached           -> chase the bank
 *    unparsed    batch job hasn't run yet   -> clears itself
 *    unreadable  scanned image / bad layout -> OCR or parser work
 *    parsed      transactions extracted
 *
 *  Only `missing` and `unreadable` are anyone's work. Lumping all four
 *  together would put the batch job's own backlog in front of an
 *  officer as though it were their problem — and on the current corpus
 *  that backlog is 89% of everything.
 *
 *  The KPI counts deliberately IGNORE the status filter, so the four
 *  numbers always add to the total no matter which status is being
 *  viewed. A denominator that moves when you click a filter is not a
 *  denominator.
 */
import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import * as XLSX from 'xlsx';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import {
  FileWarning, FileSpreadsheet, FileText, Info, Clock, ScanLine,
  CheckCircle2, Hourglass,
} from 'lucide-react';
import { getStatementCoverage } from '../../lib/api/dashboard';
import { formatNumber } from '../../lib/utils/format';
import { Pager, paginate, PAGE_SIZE } from '../common/Pager';
import { stateAbbr } from '../../lib/utils/geo-tile-grid';
import type {
  StatementCoverageSummary, StatementCoverageRow, MoneyTrailScope, CoverageStatus,
} from '../../types';

const C_NAVY = '#0b2c4a';
const C_RED = '#8b1919';
const C_GREEN = '#0a6b28';
const C_ORANGE = '#c67c1d';
const C_GREY = '#6b7280';

const cardStyle = {
  background: '#fff',
  border: '1px solid rgba(0,0,0,0.06)',
  boxShadow: '0 6px 16px rgba(0,0,0,0.08)',
};

const SCOPES: { value: MoneyTrailScope; label: string }[] = [
  { value: 'all', label: 'All India' },
  { value: 'karnataka', label: 'Karnataka' },
  { value: 'other', label: 'Other States' },
];
const TYPES = ['All', 'Mule', 'Non-Mule', 'Victim'];
const STATUSES: { value: CoverageStatus; label: string }[] = [
  { value: 'missing', label: 'No statement uploaded' },
  { value: 'unreadable', label: 'Uploaded but unreadable' },
  { value: 'unparsed', label: 'Not yet parsed' },
  { value: 'parsed', label: 'Parsed' },
  { value: 'all', label: 'All statuses' },
];

/** Colour carries the action, not the severity of the number. Grey for
 *  `unparsed` on purpose: it is the batch job's backlog, and colouring
 *  it red would send officers chasing banks for files already in hand. */
function statusPill(s: string) {
  if (s === 'missing') return { background: '#fbe6e6', color: C_RED, label: 'No statement' };
  if (s === 'unreadable') return { background: 'rgba(198,124,29,0.16)', color: C_ORANGE, label: 'Unreadable' };
  if (s === 'unparsed') return { background: '#f0f0f0', color: C_GREY, label: 'Not yet parsed' };
  return { background: '#e6f5eb', color: C_GREEN, label: 'Parsed' };
}

function typePill(t: string | null) {
  if (t === 'Victim') return { background: '#e6f5eb', color: C_GREEN };
  if (t === 'Mule') return { background: '#fbe6e6', color: C_RED };
  if (t === 'Non-Mule') return { background: '#e6ecf5', color: C_NAVY };
  return { background: '#f0f0f0', color: '#444' };
}

function Kpi({ label, value, accent, sub, Icon, onClick, active }: {
  label: string; value: string; accent: string; sub?: string;
  Icon?: React.ComponentType<{ className?: string }>;
  onClick?: () => void; active?: boolean;
}) {
  return (
    <div className="rounded-2xl p-4"
      onClick={onClick}
      style={{
        ...cardStyle, borderTop: `4px solid ${accent}`,
        cursor: onClick ? 'pointer' : undefined,
        outline: active ? `2px solid ${accent}` : undefined,
      }}>
      <p className="text-[11px] uppercase tracking-wide font-bold flex items-center gap-1"
        style={{ color: accent }}>
        {Icon && <Icon className="w-3.5 h-3.5" />} {label}
      </p>
      <p className="text-2xl font-bold" style={{ color: C_NAVY }}>{value}</p>
      {sub && <p className="text-[11px] mt-0.5 opacity-60">{sub}</p>}
    </div>
  );
}

function filterLabel(scope: MoneyTrailScope, type: string, status: CoverageStatus) {
  const s = SCOPES.find((x) => x.value === scope)?.label ?? 'All India';
  const st = STATUSES.find((x) => x.value === status)?.label ?? 'All statuses';
  return `${s} · ${type === 'All' ? 'All account types' : type} · ${st}`;
}
function filterSlug(scope: MoneyTrailScope, type: string, status: CoverageStatus) {
  return `${scope}_${type.toLowerCase().replace(/[^a-z0-9]+/g, '-')}_${status}`;
}

const COLUMNS: { header: string; get: (r: StatementCoverageRow) => string | number }[] = [
  { header: 'Account Holder', get: (r) => r.account_holder_name || '' },
  { header: 'Account No', get: (r) => r.account_no || '' },
  { header: 'Bank', get: (r) => r.bank_name || '' },
  { header: 'Type', get: (r) => r.account_type || '' },
  { header: 'FIR No', get: (r) => r.fir_no || '' },
  { header: 'Police Station', get: (r) => r.ps_name || '' },
  { header: 'District', get: (r) => r.district || '' },
  { header: 'Branch State', get: (r) => r.branch_state || '' },
  { header: 'Status', get: (r) => statusPill(r.status).label },
  { header: 'Reason', get: (r) => r.detail || '' },
  { header: 'FIR Date', get: (r) => r.fir_date || '' },
  { header: 'Days Open', get: (r) => (r.days_open ?? '') },
];

type SortKey = 'holder' | 'account_no' | 'type' | 'fir' | 'ps' | 'state'
             | 'status' | 'age';
type SortDir = 'asc' | 'desc';

function SortTh({ label, k, dir, right, sortBy, sortDir, onSort }: {
  label: string; k: SortKey; dir: SortDir; right?: boolean;
  sortBy: SortKey; sortDir: SortDir; onSort: (k: SortKey, d: SortDir) => void;
}) {
  const active = sortBy === k;
  return (
    <th className="px-2 py-2 text-[10px] uppercase font-bold"
      aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
      style={{ background: active ? 'rgba(255,255,255,0.10)' : undefined }}>
      <button type="button" onClick={() => onSort(k, dir)} title={`Sort by ${label}`}
        className={`w-full flex items-center gap-0.5 uppercase font-bold ${
          right ? 'justify-end' : 'justify-start'}`}
        style={{ color: 'inherit', cursor: 'pointer', userSelect: 'none' }}>
        <span className="truncate">{label}</span>
        {active && <span className="opacity-80">{sortDir === 'asc' ? '▲' : '▼'}</span>}
      </button>
    </th>
  );
}

export function StatementCoverageTab() {
  const [data, setData] = useState<StatementCoverageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [scope, setScope] = useState<MoneyTrailScope>('all');
  const [acctType, setAcctType] = useState('All');
  // Defaults to the actionable view. "All statuses" is dominated by the
  // parser backlog, which is nobody's work and would bury the 1,415
  // accounts that are.
  const [status, setStatus] = useState<CoverageStatus>('missing');
  const [sortBy, setSortBy] = useState<SortKey>('age');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  function onSort(key: SortKey, naturalDir: SortDir) {
    if (sortBy === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortBy(key); setSortDir(naturalDir); }
    setPage(0);
  }

  useEffect(() => {
    let alive = true;
    setLoading(true);
    getStatementCoverage(scope, acctType, status, 25000)
      .then((d) => { if (alive) { setData(d); setLoading(false); setPage(0); } })
      .catch((e: unknown) => {
        if (!alive) return;
        setData(null); setLoading(false);
        toast.error(e instanceof Error ? e.message : 'Failed to load statement coverage');
      });
    return () => { alive = false; };
  }, [scope, acctType, status]);

  const rows = useMemo(() => {
    const all = data?.rows ?? [];
    const txt = (v: string | null) => (v || '').toLowerCase();
    const cmp = (a: StatementCoverageRow, b: StatementCoverageRow): number => {
      let r = 0;
      switch (sortBy) {
        case 'holder': r = txt(a.account_holder_name).localeCompare(txt(b.account_holder_name)); break;
        case 'account_no': r = txt(a.account_no).localeCompare(txt(b.account_no)); break;
        case 'type': r = txt(a.account_type).localeCompare(txt(b.account_type)); break;
        case 'fir': r = txt(a.fir_no).localeCompare(txt(b.fir_no)); break;
        case 'ps': r = txt(a.ps_name).localeCompare(txt(b.ps_name)); break;
        case 'state': r = txt(a.branch_state).localeCompare(txt(b.branch_state)); break;
        case 'status': r = txt(a.status).localeCompare(txt(b.status)); break;
        default:
          // Unknown age sinks in BOTH directions. An FIR with no usable
          // registration date is not a new one, and reversing the sort
          // must not float 19 undated rows to the top of a work list.
          if (a.days_open == null && b.days_open == null) r = 0;
          else if (a.days_open == null) return 1;
          else if (b.days_open == null) return -1;
          else r = a.days_open - b.days_open;
          break;
      }
      if (sortDir === 'desc') r = -r;
      return r || a.account_id.localeCompare(b.account_id);
    };
    return [...all].sort(cmp);
  }, [data, sortBy, sortDir]);

  const pg = paginate(rows.length, page);
  const pageRows = pg.slice(rows);

  function matrix() {
    return {
      header: COLUMNS.map((c) => c.header),
      body: rows.map((r) => COLUMNS.map((c) => c.get(r))),
    };
  }

  function downloadExcel() {
    if (!rows.length) { toast.error('Nothing to export.'); return; }
    const { header, body } = matrix();
    const ws = XLSX.utils.aoa_to_sheet([header, ...body]);
    ws['!cols'] = header.map((_, i) => ({
      wch: Math.min(40, Math.max(10, Math.max(
        String(header[i] ?? '').length,
        ...body.map((r) => String(r[i] ?? '').length)) + 2)),
    }));
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Statement Coverage');
    XLSX.writeFile(wb, `statement-coverage_${filterSlug(scope, acctType, status)}`
      + `_${new Date().toISOString().slice(0, 10)}.xlsx`);
  }

  function downloadPdf() {
    if (!rows.length) { toast.error('Nothing to export.'); return; }
    const { header, body } = matrix();
    const doc = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'a3' });
    doc.setFontSize(14);
    doc.text('Statement Coverage — accounts without a usable bank statement', 40, 40);
    doc.setFontSize(10);
    doc.text(`Filter: ${filterLabel(scope, acctType, status)}`, 40, 58);
    doc.text(`${formatNumber(rows.length)} account${rows.length === 1 ? '' : 's'}`
      + ` · generated ${new Date().toISOString().slice(0, 10)}`, 40, 72);
    autoTable(doc, {
      startY: 90,
      head: [header],
      body: body.map((r) => r.map((v) => String(v ?? ''))),
      styles: { fontSize: 7, cellPadding: 3, overflow: 'linebreak' },
      headStyles: { fillColor: [11, 44, 74] },
      alternateRowStyles: { fillColor: [245, 245, 247] },
      columnStyles: { 9: { cellWidth: 110 } },
    });
    doc.save(`statement-coverage_${filterSlug(scope, acctType, status)}`
      + `_${new Date().toISOString().slice(0, 10)}.pdf`);
  }

  if (loading) {
    return (
      <div className="text-center py-16 font-semibold" style={{ color: C_NAVY }}>
        Loading statement coverage…
      </div>
    );
  }
  if (!data) return null;

  const pct = (n: number) =>
    data.total_accounts ? `${(100 * n / data.total_accounts).toFixed(1)}%` : '—';

  // Compared against the count for the ACTIVE status, not the grand
  // total — the KPI counts deliberately ignore the status filter, so
  // total_accounts would flag a false truncation on every filtered view.
  const expected = status === 'all' ? data.total_accounts
    : status === 'missing' ? data.missing
    : status === 'unparsed' ? data.unparsed
    : status === 'unreadable' ? data.unreadable
    : data.parsed;
  const truncated = rows.length < expected;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        <Kpi label="Accounts in scope" value={formatNumber(data.total_accounts)}
          accent={C_NAVY} sub="under the filters below" />
        <Kpi label="No statement" value={formatNumber(data.missing)}
          accent={C_RED} sub={`${pct(data.missing)} — chase the bank`}
          Icon={FileWarning} active={status === 'missing'}
          onClick={() => setStatus('missing')} />
        <Kpi label="Unreadable" value={formatNumber(data.unreadable)}
          accent={C_ORANGE} sub={`${pct(data.unreadable)} — needs OCR`}
          Icon={ScanLine} active={status === 'unreadable'}
          onClick={() => setStatus('unreadable')} />
        <Kpi label="Not yet parsed" value={formatNumber(data.unparsed)}
          accent={C_GREY} sub={`${pct(data.unparsed)} — batch backlog`}
          Icon={Hourglass} active={status === 'unparsed'}
          onClick={() => setStatus('unparsed')} />
        <Kpi label="Parsed" value={formatNumber(data.parsed)}
          accent={C_GREEN}
          sub={`${formatNumber(data.parsed_verified)} reconciled`}
          Icon={CheckCircle2} active={status === 'parsed'}
          onClick={() => setStatus('parsed')} />
      </div>

      {truncated && (
        <div className="rounded-xl px-4 py-3 text-xs font-semibold"
          style={{ background: 'rgba(198,124,29,0.10)',
                   border: '1px solid rgba(198,124,29,0.35)', color: C_RED }}>
          ⚠ Showing {formatNumber(rows.length)} of {formatNumber(expected)}{' '}
          accounts for this status. The remaining{' '}
          {formatNumber(expected - rows.length)} are not on this page or in
          the export.
        </div>
      )}

      <div className="rounded-xl px-4 py-3 flex items-start gap-2"
        style={{ background: 'rgba(11,44,74,0.06)', border: '1px solid rgba(11,44,74,0.18)' }}>
        <Info className="w-4 h-4 mt-0.5 shrink-0" style={{ color: C_NAVY }} />
        <div className="text-xs" style={{ color: C_NAVY }}>
          <b>Only two of these four need anyone’s attention.</b>{' '}
          <b>No statement</b> means nothing was ever attached — that is a records
          request to the bank. <b>Unreadable</b> means a file exists but is a scanned
          image or a layout the parser does not know, so it needs OCR.{' '}
          <b>Not yet parsed</b> is the batch job’s own backlog and clears itself when
          it next runs; it is not a gap in your case file.
          {data.accounts_without_state > 0 && scope !== 'all' && (
            <> {formatNumber(data.accounts_without_state)} account
              {data.accounts_without_state === 1 ? ' has' : 's have'} no branch state
              recorded and appear only under “All India”.</>
          )}
        </div>
      </div>

      <div className="rounded-2xl overflow-hidden" style={cardStyle}>
        <div className="px-5 py-4 flex items-start justify-between gap-4 flex-wrap"
          style={{ borderBottom: '3px solid var(--ksp-yellow)' }}>
          <div>
            <h3 className="text-sm font-bold flex items-center gap-1.5" style={{ color: C_NAVY }}>
              <Clock className="w-4 h-4" /> Work list — oldest gap first
            </h3>
            <p className="text-xs mt-1 opacity-60">
              Aged from the FIR registration date, not from when the row was created.
              Accounts whose FIR has no usable date show “—” and sort last.
            </p>
            <p className="text-sm font-medium mt-1" style={{ color: C_RED }}>
              {rows.length === 0
                ? 'no accounts match'
                : `showing ${formatNumber(pg.firstIdx + 1)}–${formatNumber(pg.lastIdx)}`
                  + ` of ${formatNumber(rows.length)} account${rows.length === 1 ? '' : 's'}`}
            </p>
          </div>
          {/* justify-end keeps the downloads pinned to the right edge
              even when the three filters wrap onto their own line on a
              narrow screen; without it the buttons drift left under the
              dropdowns. */}
          <div className="flex gap-2 items-center flex-wrap justify-end">
            <select value={scope} onChange={(e) => setScope(e.target.value as MoneyTrailScope)}
              aria-label="Filter by state"
              className="px-2 py-1.5 rounded-lg text-sm font-semibold bg-white"
              style={{ border: `2px solid ${C_NAVY}`, color: C_NAVY }}>
              {SCOPES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <select value={acctType} onChange={(e) => setAcctType(e.target.value)}
              aria-label="Filter by account type"
              className="px-2 py-1.5 rounded-lg text-sm font-semibold bg-white"
              style={{ border: `2px solid ${C_NAVY}`, color: C_NAVY }}>
              {TYPES.map((t) => (
                <option key={t} value={t}>{t === 'All' ? 'All Types' : t}</option>
              ))}
            </select>
            <select value={status} onChange={(e) => setStatus(e.target.value as CoverageStatus)}
              aria-label="Filter by statement status"
              className="px-2 py-1.5 rounded-lg text-sm font-semibold bg-white"
              style={{ border: `2px solid ${C_NAVY}`, color: C_NAVY }}>
              {STATUSES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
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
            No accounts match these filters.
          </p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left" style={{ tableLayout: 'fixed' }}>
                <colgroup>
                  <col style={{ width: '2.25rem' }} />
                  <col />
                  <col style={{ width: '7.5rem' }} />
                  <col style={{ width: '4.5rem' }} />
                  <col style={{ width: '5.5rem' }} />
                  <col style={{ width: '8.5rem' }} />
                  <col style={{ width: '3.25rem' }} />
                  <col style={{ width: '6.5rem' }} />
                  <col style={{ width: '4.5rem' }} />
                </colgroup>
                <thead style={{ background: C_NAVY, color: 'var(--ksp-yellow)' }}>
                  <tr>
                    <th className="px-2 py-2 text-[10px] uppercase font-bold">#</th>
                    <SortTh label="Account holder" k="holder" dir="asc" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
                    <SortTh label="Account no" k="account_no" dir="asc" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
                    <SortTh label="Type" k="type" dir="asc" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
                    <SortTh label="FIR No" k="fir" dir="asc" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
                    <SortTh label="Police Station" k="ps" dir="asc" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
                    <SortTh label="State" k="state" dir="asc" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
                    <SortTh label="Status" k="status" dir="asc" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
                    <SortTh label="Days" k="age" dir="desc" right sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((r, i) => {
                    const sp = statusPill(r.status);
                    return (
                      <tr key={r.account_id} className="border-t"
                        style={{ borderColor: 'rgba(11,44,74,0.08)' }}>
                        <td className="px-2 py-1.5 font-bold opacity-50">
                          {formatNumber(pg.firstIdx + i + 1)}
                        </td>
                        <td className="px-2 py-1.5">
                          <span className="font-semibold block truncate"
                            style={{ color: C_NAVY }}
                            title={r.account_holder_name || undefined}>
                            {r.account_holder_name || '—'}
                          </span>
                          <span className="block text-[10px] opacity-55 truncate"
                            title={r.detail || r.bank_name || undefined}>
                            {r.bank_name || '—'}{r.detail ? ` · ${r.detail}` : ''}
                          </span>
                        </td>
                        <td className="px-2 py-1.5 font-mono text-[11px] truncate"
                          title={r.account_no || undefined}>{r.account_no || '—'}</td>
                        <td className="px-2 py-1.5">
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold"
                            style={typePill(r.account_type)}>{r.account_type || '—'}</span>
                        </td>
                        <td className="px-2 py-1.5 truncate" title={r.fir_no || undefined}>
                          {r.fir_no || '—'}
                        </td>
                        <td className="px-2 py-1.5">
                          <span className="block truncate" title={r.ps_name || undefined}>
                            {r.ps_name || '—'}
                          </span>
                          <span className="block text-[10px] opacity-55 truncate">
                            {r.district || ''}
                          </span>
                        </td>
                        <td className="px-2 py-1.5" title={r.branch_state || 'not recorded'}>
                          {r.branch_state
                            ? (stateAbbr(r.branch_state)
                                ?? <span className="truncate block">{r.branch_state}</span>)
                            : <span className="opacity-40">—</span>}
                        </td>
                        <td className="px-2 py-1.5">
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold whitespace-nowrap"
                            style={{ background: sp.background, color: sp.color }}>
                            {sp.label}
                          </span>
                        </td>
                        <td className="px-2 py-1.5 text-right font-bold"
                          style={{ color: (r.days_open ?? 0) >= 180 ? C_RED : undefined }}
                          title={r.fir_date ? `FIR dated ${r.fir_date}` : 'no usable FIR date'}>
                          {r.days_open == null ? '—' : formatNumber(r.days_open)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Pager total={rows.length} page={pg.safePage} pageCount={pg.pageCount}
              onPage={setPage} noun="accounts" size={PAGE_SIZE} />
          </>
        )}
      </div>
    </div>
  );
}
