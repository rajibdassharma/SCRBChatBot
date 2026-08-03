import { Fragment, useEffect, useMemo, useState } from 'react';

// Resolve upload paths against the backend base URL — matches how the
// entry form loads photos + statements. In prod BASE is empty and the
// signed path resolves against the current origin; in dev VITE_API_BASE
// points at http://localhost:8000 so the middleware can validate.
const BASE = import.meta.env.VITE_API_BASE ?? '';
import { ArrowLeft, ChevronDown, ChevronRight, FileSpreadsheet, FileText } from 'lucide-react';
import { toast } from 'sonner';
import * as XLSX from 'xlsx';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import { getAccountsDetailsByPs } from '../../lib/api/dashboard';
import type { AccountsPsComparison, AllAccount } from '../../types';

/** Drill-down panel: one Police Station's full account roster with
 *  every column from the entry screen, plus Excel + PDF export.
 *  Mule accounts show a chevron that expands a herder sub-panel.
 *
 *  Herders on export: collapsed into a single "Mule Herders" cell as
 *  "Name (mobile) — address; Name (mobile) — address" so the export
 *  stays a single row per account — easier to filter/sort in Excel. */

/** Rows per page in the drill-down. A busy PS returns hundreds of
 *  accounts and the table has 17 columns — rendering the lot made the
 *  panel unusable to scroll. Exports are deliberately NOT paginated:
 *  the download is the whole dataset, not the page you happen to be
 *  looking at. */
const PAGE_SIZE = 25;

const fmtInt = (n: number) => n.toLocaleString('en-IN');

const cardStyle = {
  background: '#fff',
  border: '1px solid rgba(0,0,0,0.06)',
  boxShadow: '0 6px 16px rgba(0,0,0,0.08)',
};

type Props = {
  ps: AccountsPsComparison;
  asOfDate: string;
  onBack: () => void;
};

/** Column definitions — one source of truth for grid + Excel + PDF. */
const COLUMNS: Array<{
  key: keyof AllAccount | 'mule_herders_summary';
  label: string;
  /** Formatter: raw AllAccount → string for export cells. */
  export: (row: AllAccount) => string;
}> = [
  { key: 'serial_no',           label: 'Serial',      export: (r) => String(r.serial_no) },
  { key: 'account_type',        label: 'Type',        export: (r) => r.account_type },
  { key: 'fir_no',              label: 'FIR No',      export: (r) => r.fir_no ?? '' },
  { key: 'ncrp_ack_no',         label: 'NCRP Ack',    export: (r) => r.ncrp_ack_no ?? '' },
  { key: 'account_no',          label: 'Account No',  export: (r) => r.account_no },
  { key: 'bank_name',           label: 'Bank',        export: (r) => r.bank_name },
  { key: 'branch_name',         label: 'Branch',      export: (r) => r.branch_name ?? '' },
  { key: 'branch_state',        label: 'Branch State', export: (r) => r.branch_state ?? '' },
  { key: 'branch_district',     label: 'Branch District', export: (r) => r.branch_district ?? '' },
  { key: 'ifsc_code',           label: 'IFSC',        export: (r) => r.ifsc_code ?? '' },
  { key: 'layer',               label: 'Layer',       export: (r) => r.layer != null ? String(r.layer) : '' },
  { key: 'account_holder_name', label: 'Holder Name', export: (r) => r.account_holder_name },
  { key: 'kyc_address',         label: 'KYC Address', export: (r) => r.kyc_address ?? '' },
  { key: 'kyc_mobile',          label: 'KYC Mobile',  export: (r) => r.kyc_mobile ?? '' },
  { key: 'id_photo_path',       label: 'ID Photo',    export: (r) => (r.id_photo_path ? 'Yes' : '') },
  { key: 'account_statement_path', label: 'Statement', export: (r) => r.account_statement_path ?? '' },
  {
    key: 'mule_herders_summary',
    label: 'Mule Herders',
    export: (r) => (r.mule_herders ?? []).map(h => {
      const parts = [h.name];
      if (h.mobile_no) parts.push(`(${h.mobile_no})`);
      if (h.address)   parts.push(`— ${h.address}`);
      return parts.join(' ');
    }).join('; '),
  },
  {
    key: 'created_at',
    label: 'Created At',
    export: (r) => new Date(r.created_at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }),
  },
];

function typeBadgeStyle(t: string): React.CSSProperties {
  if (t === 'Victim')   return { background: '#e6f5eb', color: '#0a6b28' };
  if (t === 'Mule')     return { background: '#fbe6e6', color: '#8b1919' };
  if (t === 'Non-Mule') return { background: '#e6ecf5', color: '#0b2c4a' };
  return { background: '#f0f0f0', color: '#444' };
}

/** Safe-ish filename slug — keeps letters/digits, replaces the rest with '-'. */
function slug(s: string): string {
  return s.trim().replace(/[^A-Za-z0-9]+/g, '-').replace(/^-|-$/g, '').toLowerCase() || 'ps';
}

export function AccountsPsDetailPanel({ ps, asOfDate, onBack }: Props) {
  const [rows, setRows] = useState<AllAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [page, setPage] = useState(0);

  useEffect(() => {
    setLoading(true);
    getAccountsDetailsByPs(asOfDate, ps.unit_id, ps.ps_id)
      .then((r) => { setRows(r); setPage(0); })
      .catch((e) => {
        toast.error(`Failed to load account details: ${e?.message ?? 'unknown error'}`);
        setRows([]);
      })
      .finally(() => setLoading(false));
  }, [asOfDate, ps.unit_id, ps.ps_id]);

  /** Page slice. Clamped rather than trusted: changing the date can
   *  shrink the result set while `page` still points past the end,
   *  which would otherwise render an empty table with rows available. */
  const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const firstIdx = safePage * PAGE_SIZE;
  const pageRows = useMemo(
    () => rows.slice(firstIdx, firstIdx + PAGE_SIZE),
    [rows, firstIdx],
  );

  function toggleExpand(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  /** Build the export matrix — the same shape reused by Excel + PDF. */
  const exportMatrix = useMemo(() => {
    const header = COLUMNS.map(c => c.label);
    const body = rows.map(r => COLUMNS.map(c => c.export(r)));
    return { header, body };
  }, [rows]);

  function downloadExcel() {
    if (!rows.length) { toast.error('Nothing to export.'); return; }
    const wsData = [exportMatrix.header, ...exportMatrix.body];
    const ws = XLSX.utils.aoa_to_sheet(wsData);
    // Auto-width-ish: cap each column at 40 chars based on longest cell.
    ws['!cols'] = exportMatrix.header.map((_, colIdx) => {
      const maxLen = Math.max(
        String(exportMatrix.header[colIdx] ?? '').length,
        ...exportMatrix.body.map(row => String(row[colIdx] ?? '').length),
      );
      return { wch: Math.min(40, Math.max(10, maxLen + 2)) };
    });
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Accounts');
    const filename = `account-details_${slug(ps.unit_name)}_${slug(ps.ps_name)}_${asOfDate}.xlsx`;
    XLSX.writeFile(wb, filename);
  }

  function downloadPdf() {
    if (!rows.length) { toast.error('Nothing to export.'); return; }
    // Landscape A3 — 14 columns won't fit comfortably in A4 portrait/landscape.
    const doc = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'a3' });
    doc.setFontSize(14);
    doc.text('Account Details', 40, 40);
    doc.setFontSize(10);
    doc.text(`${ps.unit_name} — ${ps.ps_name}`, 40, 58);
    doc.text(`As of: ${asOfDate}   |   ${rows.length} account${rows.length === 1 ? '' : 's'}`, 40, 72);
    autoTable(doc, {
      startY: 90,
      head: [exportMatrix.header],
      body: exportMatrix.body,
      styles: { fontSize: 7, cellPadding: 3, overflow: 'linebreak' },
      headStyles: { fillColor: [11, 44, 74] },   // ksp-navy
      alternateRowStyles: { fillColor: [245, 245, 247] },
      columnStyles: {
        12: { cellWidth: 90 },   // KYC Address — wider
        15: { cellWidth: 60 },   // Statement — path is long
        16: { cellWidth: 120 },  // Mule Herders — widest
      },
    });
    const filename = `account-details_${slug(ps.unit_name)}_${slug(ps.ps_name)}_${asOfDate}.pdf`;
    doc.save(filename);
  }

  return (
    <div>
      {/* Header row: back button + title + downloads */}
      <div className="flex items-start justify-between mb-6 gap-4">
        <div className="flex items-start gap-3">
          <button
            onClick={onBack}
            className="mt-1 inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-semibold"
            style={{ background: 'var(--ksp-navy)', color: '#fff' }}
          >
            <ArrowLeft className="w-4 h-4" /> Back to summary
          </button>
          <div>
            <h1 className="text-[22px] font-bold mb-1" style={{ color: 'var(--ksp-navy)' }}>
              Account Details — {ps.ps_name}
            </h1>
            <p className="text-sm font-medium" style={{ color: 'var(--ksp-red)' }}>
              {ps.unit_name} · as of {asOfDate} ·{' '}
              {rows.length === 0
                ? 'no accounts'
                : `showing ${fmtInt(firstIdx + 1)}–${fmtInt(Math.min(firstIdx + PAGE_SIZE, rows.length))} of ${fmtInt(rows.length)} account${rows.length === 1 ? '' : 's'}`}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={downloadExcel}
            disabled={loading || rows.length === 0}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-semibold disabled:opacity-40"
            style={{ background: '#0a6b28', color: '#fff' }}
          >
            <FileSpreadsheet className="w-4 h-4" /> Excel
          </button>
          <button
            onClick={downloadPdf}
            disabled={loading || rows.length === 0}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-semibold disabled:opacity-40"
            style={{ background: '#8b1919', color: '#fff' }}
          >
            <FileText className="w-4 h-4" /> PDF
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-16 font-semibold" style={{ color: 'var(--ksp-navy)' }}>
          Loading account details…
        </div>
      ) : rows.length === 0 ? (
        <div className="rounded-2xl p-10 text-center italic opacity-60" style={cardStyle}>
          No account records for this Police Station up to the selected date.
        </div>
      ) : (
        <div className="rounded-2xl overflow-hidden" style={cardStyle}>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead style={{ background: '#f5f5f7' }}>
                <tr>
                  <th className="px-2 py-2 text-left w-8" />
                  {COLUMNS.map(c => (
                    <th key={String(c.key)} className="px-3 py-2 text-left whitespace-nowrap font-semibold"
                        style={{ color: 'var(--ksp-navy)' }}>
                      {c.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {pageRows.map((r) => {
                  const herders = r.mule_herders ?? [];
                  const canExpand = herders.length > 0;
                  const isOpen = expanded.has(r.id);
                  return (
                    <Fragment key={r.id}>
                      <tr className="border-t border-slate-100 align-top">
                        <td className="px-2 py-2">
                          {canExpand ? (
                            <button onClick={() => toggleExpand(r.id)}
                                    className="p-1 rounded hover:bg-slate-100"
                                    aria-label={isOpen ? 'Collapse herders' : 'Expand herders'}>
                              {isOpen
                                ? <ChevronDown className="w-4 h-4" />
                                : <ChevronRight className="w-4 h-4" />}
                            </button>
                          ) : null}
                        </td>
                        <td className="px-3 py-2 font-mono">{r.serial_no}</td>
                        <td className="px-3 py-2">
                          <span className="px-2 py-0.5 rounded text-[11px] font-semibold"
                                style={typeBadgeStyle(r.account_type)}>
                            {r.account_type}
                          </span>
                        </td>
                        <td className="px-3 py-2">{r.fir_no ?? '—'}</td>
                        <td className="px-3 py-2">{r.ncrp_ack_no ?? '—'}</td>
                        <td className="px-3 py-2 font-mono">{r.account_no}</td>
                        <td className="px-3 py-2">{r.bank_name}</td>
                        <td className="px-3 py-2">{r.branch_name ?? '—'}</td>
                        <td className="px-3 py-2">{r.branch_state ?? '—'}</td>
                        <td className="px-3 py-2">{r.branch_district ?? '—'}</td>
                        <td className="px-3 py-2 font-mono">{r.ifsc_code ?? '—'}</td>
                        <td className="px-3 py-2 font-mono text-center">{r.layer != null ? r.layer : '—'}</td>
                        <td className="px-3 py-2">{r.account_holder_name}</td>
                        <td className="px-3 py-2 max-w-[240px] truncate" title={r.kyc_address ?? ''}>
                          {r.kyc_address ?? '—'}
                        </td>
                        <td className="px-3 py-2 font-mono">{r.kyc_mobile ?? '—'}</td>
                        <td className="px-3 py-2">
                          {r.id_photo_path
                            ? <a href={`${BASE}/${r.id_photo_path}`} target="_blank" rel="noreferrer"
                                 className="hover:underline font-semibold" style={{ color: 'var(--ksp-link-blue)' }}>
                                Yes
                              </a>
                            : '—'}
                        </td>
                        <td className="px-3 py-2">
                          {r.account_statement_path
                            ? <a href={`${BASE}/${r.account_statement_path}`} target="_blank" rel="noreferrer"
                                 className="hover:underline font-semibold" style={{ color: 'var(--ksp-link-blue)' }}>
                                Yes
                              </a>
                            : '—'}
                        </td>
                        <td className="px-3 py-2">
                          {herders.length > 0
                            ? <span className="font-semibold">{herders.length}</span>
                            : '—'}
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap">
                          {new Date(r.created_at).toLocaleString('en-IN', {
                            dateStyle: 'medium', timeStyle: 'short',
                          })}
                        </td>
                      </tr>
                      {isOpen && canExpand && (
                        <tr className="border-t border-slate-100"
                            style={{ background: '#fafbfd' }}>
                          <td />
                          <td colSpan={COLUMNS.length} className="px-4 py-3">
                            <div className="text-[11px] font-semibold uppercase tracking-wide mb-2 opacity-70">
                              Mule Herders ({herders.length})
                            </div>
                            <table className="w-full text-xs">
                              <thead>
                                <tr className="text-left opacity-60">
                                  <th className="px-2 py-1">Name</th>
                                  <th className="px-2 py-1">Mobile</th>
                                  <th className="px-2 py-1">Address</th>
                                </tr>
                              </thead>
                              <tbody>
                                {herders.map(h => (
                                  <tr key={h.id ?? h.name} className="border-t border-slate-100">
                                    <td className="px-2 py-1">{h.name}</td>
                                    <td className="px-2 py-1 font-mono">{h.mobile_no ?? '—'}</td>
                                    <td className="px-2 py-1">{h.address ?? '—'}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Pager. Hidden entirely on a single page — controls that
               can only do nothing are noise. Expanded herder rows are
               keyed by account id, so they survive paging rather than
               collapsing on every click. */}
          {pageCount > 1 && (
            <div className="flex items-center justify-between gap-3 px-4 py-3 flex-wrap"
              style={{ borderTop: '1px solid rgba(11,44,74,0.10)', background: '#fafbfd' }}>
              <span className="text-xs font-semibold" style={{ color: 'var(--ksp-navy)' }}>
                Page {safePage + 1} of {pageCount}
                <span className="opacity-60 font-normal">
                  {'  ·  '}{fmtInt(rows.length)} accounts, {PAGE_SIZE} per page
                </span>
              </span>
              <div className="flex items-center gap-1">
                <PagerBtn label="First" disabled={safePage === 0} onClick={() => setPage(0)} />
                <PagerBtn label="Prev"  disabled={safePage === 0} onClick={() => setPage(safePage - 1)} />
                {pageWindow(safePage, pageCount).map((n) => (
                  <button key={n} type="button" onClick={() => setPage(n)}
                    className="px-2.5 py-1 rounded-lg text-xs font-bold min-w-[30px]"
                    style={n === safePage
                      ? { background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }
                      : { background: '#fff', color: 'var(--ksp-navy)', border: '1px solid rgba(11,44,74,0.20)' }}>
                    {n + 1}
                  </button>
                ))}
                <PagerBtn label="Next" disabled={safePage >= pageCount - 1} onClick={() => setPage(safePage + 1)} />
                <PagerBtn label="Last" disabled={safePage >= pageCount - 1} onClick={() => setPage(pageCount - 1)} />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PagerBtn({ label, disabled, onClick }: {
  label: string; disabled: boolean; onClick: () => void;
}) {
  return (
    <button type="button" onClick={onClick} disabled={disabled}
      className="px-2.5 py-1 rounded-lg text-xs font-bold disabled:opacity-35"
      style={{ background: '#fff', color: 'var(--ksp-navy)', border: '1px solid rgba(11,44,74,0.20)' }}>
      {label}
    </button>
  );
}

/** Up to 5 page numbers centred on the current page. A PS with 400
 *  accounts is 16 pages — rendering every number turns the pager into
 *  its own scrolling problem. */
function pageWindow(current: number, total: number): number[] {
  const span = Math.min(5, total);
  let start = Math.max(0, current - Math.floor(span / 2));
  if (start + span > total) start = total - span;
  return Array.from({ length: span }, (_, i) => start + i);
}
