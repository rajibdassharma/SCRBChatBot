/** Account Details -> Mule Network tab (2026-08-06).
 *
 *  Mule accounts that transfer directly to OTHER mule accounts.
 *
 *  WHAT COUNTS AS A CONNECTION
 *  ---------------------------
 *  A's own parsed bank statement records a transfer to B's account
 *  number, and both A and B are already recorded as Mule. Nothing is
 *  inferred.
 *
 *  This is deliberately NOT the shared-destination signal. Two mules
 *  paying the same payment gateway are not connected in any useful
 *  sense — every account pays BBPS, Amazon and utility bills, so
 *  linking on that would join every account to every other and produce
 *  a graph that says nothing.
 *
 *  WHY CROSS-FIR IS THE DEFAULT
 *  ----------------------------
 *  Two mules connected inside the SAME FIR is expected: they were
 *  reported together, which is why both are on file. A transfer between
 *  mules in DIFFERENT FIRs joins two investigations nobody had joined.
 *  Of 1,309 links found, 667 cross FIRs — that is the finding, and the
 *  rest is mostly confirmation of what the case file already said.
 *
 *  DIRECTION MATTERS
 *  -----------------
 *  An account with many INBOUND links and none outbound is a collection
 *  point; one with many outbound is a distributor. The first row found
 *  on real data — 101 accounts across 100 FIRs paying in, nothing out —
 *  is the shape worth recognising at a glance, so in/out are separate
 *  columns rather than one total.
 */
import { Fragment, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import * as XLSX from 'xlsx';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import {
  Waypoints, FileSpreadsheet, FileText,  Network, Users,
} from 'lucide-react';
import { getMuleNetwork } from '../../lib/api/dashboard';
import { formatNumber } from '../../lib/utils/format';
import { Pager, paginate, PAGE_SIZE } from '../common/Pager';
import { stateAbbr } from '../../lib/utils/geo-tile-grid';
import { MuleNetworkGraph } from './MuleNetworkGraph';
import { MuleNetworkFull } from './MuleNetworkFull';
import { MuleAccountsList } from './MuleAccountsList';
import type { MuleNetworkSummary, MuleNetworkRow, MoneyTrailScope } from '../../types';
import CaveatNote from '../common/CaveatNote';

const C_NAVY = '#0b2c4a';
const C_RED = '#8b1919';
const C_GREEN = '#0a6b28';
const C_ORANGE = '#c67c1d';

const cardStyle = {
  background: '#fff',
  border: '1px solid rgba(0,0,0,0.06)',
  boxShadow: '0 6px 16px rgba(0,0,0,0.08)',
};

const SCOPES: { value: MoneyTrailScope; label: string }[] = [
  { value: 'all', label: 'All States' },
  { value: 'karnataka', label: 'Karnataka' },
  { value: 'other', label: 'Rest of India' },
];

function rupees(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  const whole = Math.round(Math.abs(v)).toString();
  let out = whole;
  if (whole.length > 3) {
    const tail = whole.slice(-3);
    let head = whole.slice(0, -3);
    const parts: string[] = [];
    while (head.length > 2) { parts.unshift(head.slice(-2)); head = head.slice(0, -2); }
    if (head) parts.unshift(head);
    out = parts.join(',') + ',' + tail;
  }
  return (v < 0 ? '-₹' : '₹') + out;
}

/** Names that read as payment infrastructure rather than a person.
 *
 *  These accounts ARE recorded as Mule in all_accounts — an officer
 *  classified them that way — so they are not filtered out. Overriding
 *  a human classification silently would be worse than showing it. But
 *  a processor receiving from 53 mules across 53 FIRs is doing its job,
 *  not running a network, and letting it sit at the top unmarked would
 *  teach officers the ranking is noise. So it is flagged and left in
 *  place for a human to judge. */
const INFRA_WORDS = [
  'payu', 'razorpay', 'billdesk', 'ccavenue', 'cashfree', 'google',
  'paytm', 'phonepe', 'amazon', 'flipkart', 'ekart', 'worldline',
  'pine labs', 'bharatpe', 'payments pvt', 'payment gateway', 'npci',
];
function looksInfra(name: string | null): boolean {
  const n = (name || '').toLowerCase();
  return INFRA_WORDS.some((w) => n.includes(w));
}

function Kpi({ label, value, accent, sub }: {
  label: string; value: string; accent: string; sub?: string;
}) {
  return (
    <div className="rounded-2xl p-4" style={{ ...cardStyle, borderTop: `4px solid ${accent}` }}>
      <p className="text-[11px] uppercase tracking-wide font-bold" style={{ color: accent }}>
        {label}
      </p>
      <p className="text-2xl font-bold" style={{ color: C_NAVY }}>{value}</p>
      {sub && <p className="text-[11px] mt-0.5 opacity-60">{sub}</p>}
    </div>
  );
}

const COLUMNS: { header: string; get: (r: MuleNetworkRow) => string | number }[] = [
  { header: 'Account Holder', get: (r) => r.account_holder_name || '' },
  { header: 'Account No', get: (r) => r.account_no || '' },
  { header: 'Bank', get: (r) => r.bank_name || '' },
  { header: 'FIR No', get: (r) => r.fir_no || '' },
  { header: 'Police Station', get: (r) => r.ps_name || '' },
  { header: 'District', get: (r) => r.district || '' },
  { header: 'Branch State', get: (r) => r.branch_state || '' },
  { header: 'Connected Mules', get: (r) => r.connected },
  { header: 'Cross-FIR', get: (r) => r.cross_fir },
  { header: 'Paid Out To', get: (r) => r.out_links },
  { header: 'Received From', get: (r) => r.in_links },
  { header: 'Transactions', get: (r) => r.txns },
  { header: 'Amount', get: (r) => r.amount },
  { header: 'Likely Infrastructure',
    get: (r) => (looksInfra(r.account_holder_name) ? 'YES — review' : '') },
];

export function MuleNetworkTab({ onTrace }: {
  onTrace?: (firNo: string, psId: number) => void;
} = {}) {
  const [data, setData] = useState<MuleNetworkSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [crossOnly, setCrossOnly] = useState(true);
  const [scope, setScope] = useState<MoneyTrailScope>('all');
  // A single selected account, not a set of expanded rows. The
  // drill-down is a diagram now, and two diagrams open at once would
  // be two claims competing for the same screen.
  const [selected, setSelected] = useState<string | null>(null);
  // Ranking table vs whole-network diagram — the same data at two zoom
  // levels, so a toggle rather than a second tab.
  const [view, setView] = useState<'ranking' | 'network' | 'all'>('ranking');

  useEffect(() => {
    let alive = true;
    setLoading(true);
    getMuleNetwork(crossOnly, scope, 20000)
      .then((d) => { if (alive) { setData(d); setLoading(false); setPage(0); } })
      .catch((e: unknown) => {
        if (!alive) return;
        setData(null); setLoading(false);
        toast.error(e instanceof Error ? e.message : 'Failed to load mule network');
      });
    return () => { alive = false; };
  }, [crossOnly, scope]);

  const rows = data?.rows ?? [];
  const pg = paginate(rows.length, page);
  const pageRows = pg.slice(rows);
  const infraCount = useMemo(
    () => rows.filter((r) => looksInfra(r.account_holder_name)).length, [rows]);

  const selectedRow = useMemo(
    () => rows.find((r) => r.account_id === selected) ?? null, [rows, selected]);

  // Clearing the selection when the filters change matters: the
  // selected account may not exist in the new result set, and a
  // diagram left on screen describing a row that is no longer in the
  // table is worse than no diagram.
  useEffect(() => { setSelected(null); }, [crossOnly, scope]);

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
    XLSX.utils.book_append_sheet(wb, ws, 'Mule Network');
    XLSX.writeFile(wb, `mule-network_${scope}_${crossOnly ? 'cross-fir' : 'all'}`
      + `_${new Date().toISOString().slice(0, 10)}.xlsx`);
  }
  function downloadPdf() {
    if (!rows.length) { toast.error('Nothing to export.'); return; }
    const { header, body } = matrix();
    const doc = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'a3' });
    doc.setFontSize(14);
    doc.text('Mule Network — accounts transferring to other mule accounts', 40, 40);
    doc.setFontSize(10);
    doc.text(`Filter: ${SCOPES.find((s) => s.value === scope)?.label}`
      + ` · ${crossOnly ? 'cross-FIR links only' : 'all links'}`, 40, 58);
    doc.setFontSize(8);
    doc.text('A link means one account’s bank statement records a transfer to the '
      + 'other’s account number, and both are recorded as Mule. Rows flagged '
      + '"Likely Infrastructure" are payment processors classified as mule accounts '
      + 'in the source data — verify before acting.', 40, 74);
    autoTable(doc, {
      startY: 92, head: [header],
      body: body.map((r) => r.map((v) => String(v ?? ''))),
      styles: { fontSize: 7, cellPadding: 3, overflow: 'linebreak' },
      headStyles: { fillColor: [11, 44, 74] },
      alternateRowStyles: { fillColor: [245, 245, 247] },
    });
    doc.save(`mule-network_${scope}_${crossOnly ? 'cross-fir' : 'all'}`
      + `_${new Date().toISOString().slice(0, 10)}.pdf`);
  }

  if (loading) {
    return <div className="text-center py-16 font-semibold" style={{ color: C_NAVY }}>
      Loading mule network…
    </div>;
  }
  if (!data || data.total_links === 0) {
    // The roll does not depend on the link job, so offer it here rather
    // than showing a dead end. Without this, an installation that has
    // never run build_links reports "no mule data" while holding
    // thousands of mule accounts.
    if (view === 'all') {
      return (
        <div className="space-y-4">
          <div className="flex items-center gap-1.5">
            {([['ranking', 'Ranking'], ['all', 'All Mule Accounts']] as const)
              .map(([v, label]) => (
                <button key={v} type="button" onClick={() => setView(v)}
                  className="px-3 py-1.5 rounded-lg text-xs font-bold transition"
                  style={{
                    background: view === v ? C_NAVY : '#fff',
                    color: view === v ? 'var(--ksp-yellow)' : C_NAVY,
                    border: `1px solid ${view === v ? C_NAVY : 'rgba(11,44,74,0.18)'}`,
                  }}>
                  {label}
                </button>
              ))}
          </div>
          <MuleAccountsList
            scope={scope}
            scopeLabel={SCOPES.find((o) => o.value === scope)?.label ?? scope} />
        </div>
      );
    }
    return (
      <div className="rounded-2xl p-8" style={cardStyle}>
        <p className="text-sm font-bold mb-1" style={{ color: C_NAVY }}>
          No mule-to-mule links have been computed yet.
        </p>
        <p className="text-xs opacity-70">
          Links are found by a batch job, not on upload. Ask your administrator
          to run <code>python -m analysis.build_links</code>.
        </p>
        <button type="button" onClick={() => setView('all')}
          className="mt-3 inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-semibold"
          style={{ background: C_NAVY, color: '#fff' }}>
          <Users className="w-4 h-4" /> All mule accounts
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Kpi label="Direct links" value={formatNumber(data.total_links)}
          accent={C_NAVY} sub="mule → mule transfers" />
        <Kpi label="Cross-FIR links" value={formatNumber(data.cross_fir_links)}
          accent={C_RED} sub="join two investigations" />
        <Kpi label="Accounts in network" value={formatNumber(data.accounts_in_network)}
          accent={C_NAVY} sub="connected to at least one" />
        <Kpi label="Mules with statements" value={formatNumber(data.accounts_with_statements)}
          accent={C_GREEN} sub="the honest denominator" />
      </div>

        <CaveatNote summary={
          `Absence from this list is not evidence — only `
          + `${formatNumber(data.accounts_with_statements)} mules have a parsed statement`
        }>
          <b>A link means one account’s statement names the other’s account
          number</b>, and both are recorded as Mule. Nothing is inferred from shared
          destinations, and payment gateways are excluded from the matching — every
          account pays BBPS and Amazon, so linking on that would connect everyone to
          everyone. An account can only appear here if its statement has been
          parsed.
          {infraCount > 0 && (
            <b className="block mt-1" style={{ color: C_ORANGE }}>
              {infraCount} row{infraCount === 1 ? '' : 's'} on this page look like
              payment processors (PayU, Google, Razorpay…) that were classified as
              mule accounts in the source data. They are flagged, not hidden —
              overriding an officer’s classification is not this screen’s job.
            </b>
          )}
        </CaveatNote>

      {/* Ranking vs whole-network: the same data at two zoom levels.
          The table answers "which account should I look at"; the graph
          answers "what shape is this". Neither replaces the other, and
          both hand off to the per-account view on click. */}
      <div className="flex items-center gap-1.5">
        {([
          ['ranking', 'Ranking'],
          ['network', 'Network'],
          ['all', 'All Mule Accounts'],
        ] as const).map(([v, label]) => (
          <button key={v} type="button" onClick={() => setView(v)}
            className="px-3 py-1.5 rounded-lg text-xs font-bold transition"
            style={{
              background: view === v ? C_NAVY : '#fff',
              color: view === v ? 'var(--ksp-yellow)' : C_NAVY,
              border: `1px solid ${view === v ? C_NAVY : 'rgba(11,44,74,0.18)'}`,
            }}>
            {label}
          </button>
        ))}
      </div>

      {view === 'all' ? (
        <div className="space-y-4">
          <div className="flex items-center gap-2 justify-end">
            <label className="text-xs font-semibold" style={{ color: C_NAVY }}>
              State
            </label>
            <select value={scope}
              onChange={(e) => setScope(e.target.value as MoneyTrailScope)}
              aria-label="Filter mule accounts by state"
              className="px-2 py-1.5 rounded-lg text-sm font-semibold bg-white"
              style={{ border: `2px solid ${C_NAVY}`, color: C_NAVY }}>
              {SCOPES.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          <MuleAccountsList
            scope={scope}
            scopeLabel={SCOPES.find((o) => o.value === scope)?.label ?? scope} />
        </div>
      ) : view === 'network' && !selectedRow ? (
        <MuleNetworkFull rows={rows} onOpenAccount={setSelected} />
      ) : (
      <>
      {/* The diagram REPLACES the list rather than sitting above it.
          Stacked, the table pushed the graph off-screen on any laptop
          and the officer ended up scrolling between two views of the
          same thing. One view at a time, with a way back. */}
      {selectedRow ? (
        <MuleNetworkGraph
          centre={selectedRow}
          allRows={rows}
          onRecentre={setSelected}
          // Clearing the selection falls back to whichever view is
          // active, so the label follows `view`, not a constant.
          backTo={view === 'network' ? 'diagram' : 'list'}
          onClose={() => setSelected(null)} />
      ) : (
      <div className="rounded-2xl overflow-hidden" style={cardStyle}>
        <div className="px-5 py-4 flex items-start justify-between gap-4 flex-wrap"
          style={{ borderBottom: '3px solid var(--ksp-yellow)' }}>
          <div>
            <h3 className="text-sm font-bold flex items-center gap-1.5" style={{ color: C_NAVY }}>
              <Waypoints className="w-4 h-4" /> Connected mule accounts
            </h3>
            <div className="mt-1">
              <CaveatNote summary="Ranked by FIRs reached, not by link count">
                Links inside one FIR are the case file restating itself, so ranking
                on raw connection count would put the most-reported accounts on top
                rather than the most connected ones. <b>Click a row to draw its
                network.</b>
              </CaveatNote>
            </div>
            <p className="text-sm font-medium mt-1" style={{ color: C_RED }}>
              {rows.length === 0 ? 'no accounts'
                : `showing ${formatNumber(pg.firstIdx + 1)}–${formatNumber(pg.lastIdx)}`
                  + ` of ${formatNumber(rows.length)} account${rows.length === 1 ? '' : 's'}`}
            </p>
          </div>
          <div className="flex gap-2 items-center flex-wrap justify-end ml-auto">
            <label className="text-xs flex items-center gap-1.5 font-semibold"
              style={{ color: C_NAVY }}>
              <input type="checkbox" checked={crossOnly}
                onChange={(e) => setCrossOnly(e.target.checked)} />
              Cross-FIR only
            </label>
            <select value={scope} onChange={(e) => setScope(e.target.value as MoneyTrailScope)}
              aria-label="Filter by state"
              className="px-2 py-1.5 rounded-lg text-sm font-semibold bg-white"
              style={{ border: `2px solid ${C_NAVY}`, color: C_NAVY }}>
              {SCOPES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
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
            No connected accounts match these filters.
          </p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left" style={{ tableLayout: 'fixed' }}>
                <colgroup>
                  <col style={{ width: '2rem' }} />
                  <col style={{ width: '2.5rem' }} />
                  <col />
                  <col style={{ width: '5.5rem' }} />
                  <col style={{ width: '8.5rem' }} />
                  <col style={{ width: '3.25rem' }} />
                  <col style={{ width: '4rem' }} />
                  <col style={{ width: '4.5rem' }} />
                  <col style={{ width: '4rem' }} />
                  <col style={{ width: '4rem' }} />
                  <col style={{ width: '6.5rem' }} />
                </colgroup>
                <thead style={{ background: C_NAVY, color: 'var(--ksp-yellow)' }}>
                  <tr>
                    <th className="px-2 py-2" />
                    <th className="px-2 py-2 text-[10px] uppercase font-bold">#</th>
                    <th className="px-2 py-2 text-[10px] uppercase font-bold">Account holder</th>
                    <th className="px-2 py-2 text-[10px] uppercase font-bold">FIR No</th>
                    <th className="px-2 py-2 text-[10px] uppercase font-bold">Police Station</th>
                    <th className="px-2 py-2 text-[10px] uppercase font-bold">State</th>
                    <th className="px-2 py-2 text-[10px] uppercase font-bold text-right">Linked</th>
                    <th className="px-2 py-2 text-[10px] uppercase font-bold text-right">X-FIR</th>
                    <th className="px-2 py-2 text-[10px] uppercase font-bold text-right">Out</th>
                    <th className="px-2 py-2 text-[10px] uppercase font-bold text-right">In</th>
                    <th className="px-2 py-2 text-[10px] uppercase font-bold text-right">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((r, i) => {
                    const isOpen = selected === r.account_id;
                    const infra = looksInfra(r.account_holder_name);
                    return (
                      // Fragment must carry the key, not the <tr> inside
                      // it. React keys the outermost element returned
                      // from a map; a keyless fragment makes every
                      // expand/collapse a full re-mount of the rows.
                      <Fragment key={r.account_id}>
                        <tr onClick={() => setSelected(
                              selected === r.account_id ? null : r.account_id)}
                          className="border-t cursor-pointer"
                          style={{ borderColor: 'rgba(11,44,74,0.08)',
                                   background: isOpen ? 'rgba(11,44,74,0.04)' : undefined }}>
                          <td className="px-2 py-1.5">
                            <Network className="w-3.5 h-3.5"
                              style={{ color: isOpen ? C_NAVY : 'rgba(11,44,74,0.35)' }} />
                          </td>
                          <td className="px-2 py-1.5 font-bold opacity-50">
                            {formatNumber(pg.firstIdx + i + 1)}
                          </td>
                          <td className="px-2 py-1.5">
                            <span className="font-semibold block truncate"
                              style={{ color: C_NAVY }}
                              title={r.account_holder_name || undefined}>
                              {r.account_holder_name || '—'}
                              {infra && (
                                <span className="ml-1 px-1 py-px rounded text-[9px] font-bold align-middle"
                                  style={{ background: 'rgba(198,124,29,0.16)', color: C_ORANGE }}
                                  title="Looks like a payment processor classified as a mule account — verify">
                                  INFRA?
                                </span>
                              )}
                            </span>
                            <span className="block text-[10px] opacity-55 truncate">
                              {r.account_no || '—'} · {r.bank_name || '—'}
                            </span>
                          </td>
                          <td className="px-2 py-1.5">
                            {onTrace && r.fir_no && r.ps_id ? (
                              <button type="button"
                                onClick={(e) => { e.stopPropagation(); onTrace(r.fir_no!, r.ps_id!); }}
                                className="hover:underline" style={{ color: '#1d4ed8' }}
                                title={`Trace FIR ${r.fir_no}`}>{r.fir_no}</button>
                            ) : (r.fir_no || '—')}
                          </td>
                          <td className="px-2 py-1.5 truncate" title={r.ps_name || undefined}>
                            {r.ps_name || '—'}
                          </td>
                          <td className="px-2 py-1.5" title={r.branch_state || 'not recorded'}>
                            {r.branch_state ? (stateAbbr(r.branch_state) ?? r.branch_state)
                                            : <span className="opacity-40">—</span>}
                          </td>
                          <td className="px-2 py-1.5 text-right font-bold">
                            {formatNumber(r.connected)}
                          </td>
                          <td className="px-2 py-1.5 text-right font-bold"
                            style={{ color: r.cross_fir >= 3 ? C_RED : undefined }}>
                            {formatNumber(r.cross_fir)}
                          </td>
                          <td className="px-2 py-1.5 text-right" style={{ color: C_RED }}>
                            {r.out_links || '—'}
                          </td>
                          <td className="px-2 py-1.5 text-right" style={{ color: C_GREEN }}>
                            {r.in_links || '—'}
                          </td>
                          <td className="px-2 py-1.5 text-right font-semibold whitespace-nowrap">
                            {rupees(r.amount)}
                          </td>
                        </tr>
                      </Fragment>
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
      )}
      </>
      )}
    </div>
  );
}
