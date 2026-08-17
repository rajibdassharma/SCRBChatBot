/** All Mule Accounts — the roll, not the network.
 *
 *  WHY THIS EXISTS ALONGSIDE THE RANKING TABLE
 *  The Ranking view can only contain an account that HAS a link, which
 *  requires that account's statement to have been parsed AND someone it
 *  paid to also be on file. That is a minority of mule accounts. Read
 *  as "the mule accounts", it undercounts badly, and the gap is
 *  invisible unless both numbers are on screen. This view is the whole
 *  population, and it carries a Links column so the two questions stay
 *  visibly distinct: 0 links is not a cleared account, it is an account
 *  with nothing on file yet.
 *
 *  STATEMENT IS THREE STATES, NOT A TICK
 *  "Attached" and "parsed" are different facts — roughly 18% of the
 *  corpus is image-only PDFs that are attached and yield nothing. One
 *  boolean would report a chasing job as finished.
 */
import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import * as XLSX from 'xlsx';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import { FileSpreadsheet, FileText, Users } from 'lucide-react';

import { getMuleAccounts } from '../../lib/api/dashboard';
import { formatNumber } from '../../lib/utils/format';
import { Pager, paginate, PAGE_SIZE } from '../common/Pager';
import type {
  MuleAccountList, MuleAccountRow, MoneyTrailScope,
} from '../../types';
import CaveatNote from '../common/CaveatNote';

const C_NAVY = '#0b2c4a';
const C_RED = '#8b1919';
const C_GREEN = '#0a6b28';
const C_ORANGE = '#b45309';

const cardStyle: React.CSSProperties = {
  background: '#fff',
  border: '1px solid rgba(0,0,0,0.06)',
  boxShadow: '0 6px 16px rgba(0,0,0,0.08)',
};

/** Three states, in the order an officer acts on them. */
function statementState(r: MuleAccountRow): string {
  if (r.statement_parsed) return 'Parsed';
  if (r.has_statement_file) return 'Attached, not parsed';
  return 'Not attached';
}

function stateColour(r: MuleAccountRow): string {
  if (r.statement_parsed) return C_GREEN;
  if (r.has_statement_file) return C_ORANGE;
  return C_RED;
}

/** Export columns. One list drives the table, the Excel sheet and the
 *  PDF, so the three can never drift apart — a spreadsheet that does
 *  not match the screen it was exported from is a evidence problem, not
 *  a cosmetic one. */
const COLUMNS: { header: string; get: (r: MuleAccountRow) => string | number }[] = [
  { header: 'Account holder', get: (r) => r.account_holder_name ?? '' },
  { header: 'Account no', get: (r) => r.account_no ?? '' },
  { header: 'Bank', get: (r) => r.bank_name ?? '' },
  { header: 'Branch', get: (r) => r.branch_name ?? '' },
  { header: 'Branch district', get: (r) => r.branch_district ?? '' },
  // Its OWN column, never merged into the one above. A reader has to be
  // able to tell what an operator recorded from what a directory
  // inferred: they disagree on 209 accounts, and in the state-level
  // cases it is the entered value that is wrong.
  { header: 'Branch district (IFSC)', get: (r) => r.branch_district_ifsc ?? '' },
  { header: 'District mismatch', get: (r) => (r.district_mismatch ? 'YES' : '') },
  { header: 'Branch state', get: (r) => r.branch_state ?? '' },
  { header: 'IFSC', get: (r) => r.ifsc_code ?? '' },
  { header: 'Mobile', get: (r) => r.kyc_mobile ?? '' },
  { header: 'FIR no', get: (r) => r.fir_no ?? '' },
  { header: 'Police station', get: (r) => r.ps_name ?? '' },
  { header: 'PS district', get: (r) => r.district ?? '' },
  { header: 'Layer', get: (r) => (r.layer == null ? '' : r.layer) },
  { header: 'Links', get: (r) => r.links },
  { header: 'Cross-FIR links', get: (r) => r.cross_fir_links },
  { header: 'Statement', get: (r) => statementState(r) },
];

export function MuleAccountsList({ scope, scopeLabel }: {
  scope: MoneyTrailScope;
  /** Passed in rather than looked up, so the export label and the
   *  dropdown can never disagree about what was filtered. */
  scopeLabel: string;
}) {
  const [data, setData] = useState<MuleAccountList | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [q, setQ] = useState('');

  useEffect(() => {
    let alive = true;
    setLoading(true);
    getMuleAccounts(scope, 30000)
      .then((d) => { if (alive) { setData(d); setLoading(false); setPage(0); } })
      .catch((e: unknown) => {
        if (!alive) return;
        setData(null); setLoading(false);
        toast.error(e instanceof Error ? e.message : 'Failed to load mule accounts');
      });
    return () => { alive = false; };
  }, [scope]);

  const all = useMemo(() => data?.rows ?? [], [data]);

  // Client-side, because the whole set is already here. Matching is
  // deliberately permissive across the identity fields an officer
  // actually has to hand -- a name, half an account number, a mobile.
  const rows = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return all;
    return all.filter((r) => (
      (r.account_holder_name ?? '').toLowerCase().includes(t)
      || (r.account_no ?? '').toLowerCase().includes(t)
      || (r.bank_name ?? '').toLowerCase().includes(t)
      || (r.ifsc_code ?? '').toLowerCase().includes(t)
      || (r.kyc_mobile ?? '').toLowerCase().includes(t)
      || (r.fir_no ?? '').toLowerCase().includes(t)
      || (r.ps_name ?? '').toLowerCase().includes(t)
    ));
  }, [all, q]);

  useEffect(() => { setPage(0); }, [q]);

  const pg = paginate(rows.length, page);
  const pageRows = pg.slice(rows);

  // The server counts the total WITHOUT the row limit, so a truncated
  // response can say so instead of looking complete.
  const truncated = !!data && data.total_mule_accounts > all.length;

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
      wch: Math.min(40, Math.max(10, Math.max(String(header[i]).length,
        ...body.map((r) => String(r[i] ?? '').length)) + 2)) }));
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'All Mule Accounts');
    XLSX.writeFile(wb, `mule-accounts_${scope}`
      + `_${new Date().toISOString().slice(0, 10)}.xlsx`);
  }

  function downloadPdf() {
    if (!rows.length) { toast.error('Nothing to export.'); return; }
    const { header, body } = matrix();
    const doc = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'a3' });
    doc.setFontSize(14);
    doc.text('All Mule Accounts', 40, 40);
    doc.setFontSize(10);
    doc.text(`Filter: ${scopeLabel}`
      + (q.trim() ? ` · search "${q.trim()}"` : '')
      + ` · ${formatNumber(rows.length)} account${rows.length === 1 ? '' : 's'}`,
    40, 58);
    doc.setFontSize(8);
    // The caveat travels with the export. A PDF read away from this
    // screen is where "0 links" gets misread as "cleared".
    doc.text('Every account recorded as Mule, whether or not it is connected to '
      + 'another. "Links" counts transfers to other mule accounts: 0 means '
      + 'nothing is on file yet, not that the account is clear. "Statement" '
      + 'distinguishes a file being attached from it having been read.', 40, 74);
    autoTable(doc, {
      startY: 92, head: [header],
      body: body.map((r) => r.map((v) => String(v ?? ''))),
      styles: { fontSize: 7, cellPadding: 3, overflow: 'linebreak' },
      headStyles: { fillColor: [11, 44, 74] },
      alternateRowStyles: { fillColor: [245, 245, 247] },
    });
    doc.save(`mule-accounts_${scope}_${new Date().toISOString().slice(0, 10)}.pdf`);
  }

  if (loading) {
    return <div className="text-center py-16 font-semibold" style={{ color: C_NAVY }}>
      Loading mule accounts…
    </div>;
  }
  if (!data) return null;

  return (
    <div className="space-y-4">
      <CaveatNote summary={
        `${formatNumber(data.total_mule_accounts)} mule accounts · `
        + `${formatNumber(data.in_network)} connected · `
        + `0 links does not mean cleared`
      }>
        <b>{formatNumber(data.total_mule_accounts)}</b> accounts are recorded as
          Mule under this filter. <b>{formatNumber(data.in_network)}</b> have at
          least one link to another mule account and{' '}
          <b>{formatNumber(data.parsed)}</b> have a statement that has been read.
          A <b>Links</b> value of 0 means nothing is on file yet —{' '}
          <b>it is not evidence that the account is clear</b>.
          {data.accounts_without_state > 0 && (
            <> {formatNumber(data.accounts_without_state)} account
              {data.accounts_without_state === 1 ? ' has' : 's have'} no branch state
              recorded; they appear only under All States, because a missing state is
              not evidence of a branch outside Karnataka.</>
          )}
          {truncated && (
            <b className="block mt-1" style={{ color: C_ORANGE }}>
              Showing the first {formatNumber(all.length)} of{' '}
              {formatNumber(data.total_mule_accounts)}. Narrow the filter to see
              the rest — the export covers only what is loaded.
            </b>
          )}
      </CaveatNote>

      <div className="rounded-2xl overflow-hidden" style={cardStyle}>
        <div className="px-5 py-4 flex items-start justify-between gap-4 flex-wrap"
          style={{ borderBottom: '3px solid var(--ksp-yellow)' }}>
          <div>
            <h3 className="text-sm font-bold flex items-center gap-1.5" style={{ color: C_NAVY }}>
              <Users className="w-4 h-4" /> All mule accounts
            </h3>
            <p className="text-sm font-medium mt-1" style={{ color: C_RED }}>
              {rows.length === 0 ? 'no accounts'
                : `showing ${formatNumber(pg.firstIdx + 1)}–${formatNumber(pg.lastIdx)}`
                  + ` of ${formatNumber(rows.length)} account${rows.length === 1 ? '' : 's'}`}
            </p>
          </div>
          <div className="flex gap-2 items-center flex-wrap justify-end ml-auto">
            <input value={q} onChange={(e) => setQ(e.target.value)}
              placeholder="Search name, account, IFSC, FIR…"
              aria-label="Search mule accounts"
              className="px-2 py-1.5 rounded-lg text-sm bg-white"
              style={{ border: `2px solid ${C_NAVY}`, color: C_NAVY, minWidth: 230 }} />
            <button onClick={downloadExcel} disabled={!rows.length}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-semibold disabled:opacity-40"
              style={{ background: C_GREEN, color: '#fff' }}>
              <FileSpreadsheet className="w-4 h-4" /> Excel
            </button>
            <button onClick={downloadPdf} disabled={!rows.length}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-semibold disabled:opacity-40"
              style={{ background: C_RED, color: '#fff' }}>
              <FileText className="w-4 h-4" /> PDF
            </button>
          </div>
        </div>

        {rows.length === 0 ? (
          <p className="px-5 py-10 text-center text-sm opacity-60">
            No mule accounts match this filter.
          </p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ background: 'rgba(11,44,74,0.05)' }}>
                    {COLUMNS.map((c) => (
                      <th key={c.header}
                        className="px-3 py-2 text-left text-xs font-bold whitespace-nowrap"
                        style={{ color: C_NAVY }}>
                        {c.header}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((r, i) => (
                    <tr key={r.account_id}
                      style={{ background: i % 2 ? 'rgba(0,0,0,0.02)' : '#fff' }}>
                      <td className="px-3 py-2 font-semibold" style={{ color: C_NAVY }}>
                        {r.account_holder_name ?? '—'}
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap">{r.account_no ?? '—'}</td>
                      <td className="px-3 py-2">{r.bank_name ?? '—'}</td>
                      <td className="px-3 py-2">{r.branch_name ?? '—'}</td>
                      <td className="px-3 py-2 whitespace-nowrap">
                        {r.branch_district ? (
                          <span
                            className={r.district_mismatch ? 'font-semibold' : ''}
                            style={{ color: r.district_mismatch ? C_ORANGE : undefined }}
                            title={r.district_mismatch
                              ? `Entered value disagrees with the IFSC directory (${r.branch_district_ifsc})`
                              : undefined}>
                            {r.branch_district}{r.district_mismatch ? ' ⚠' : ''}
                          </span>
                        ) : r.branch_district_ifsc ? (
                          // Derived: muted and marked, never presented
                          // as though an operator recorded it.
                          <span className="italic opacity-60"
                            title="Resolved from the IFSC code, not entered">
                            {r.branch_district_ifsc}
                            <span className="not-italic"> ·ifsc</span>
                          </span>
                        ) : '—'}
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap">{r.branch_state ?? '—'}</td>
                      <td className="px-3 py-2 whitespace-nowrap">{r.ifsc_code ?? '—'}</td>
                      <td className="px-3 py-2 whitespace-nowrap">{r.kyc_mobile ?? '—'}</td>
                      <td className="px-3 py-2 whitespace-nowrap">{r.fir_no ?? '—'}</td>
                      <td className="px-3 py-2">{r.ps_name ?? '—'}</td>
                      <td className="px-3 py-2">{r.district ?? '—'}</td>
                      <td className="px-3 py-2 text-center">{r.layer ?? '—'}</td>
                      <td className="px-3 py-2 text-center font-semibold">
                        {formatNumber(r.links)}
                      </td>
                      <td className="px-3 py-2 text-center font-semibold"
                        style={{ color: r.cross_fir_links > 0 ? C_RED : undefined }}>
                        {formatNumber(r.cross_fir_links)}
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap font-semibold"
                        style={{ color: stateColour(r) }}>
                        {statementState(r)}
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
    </div>
  );
}
