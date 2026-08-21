/** Account Details -> Crypto Analysis tab.
 *
 *  Surfaces transactions whose bank narration names a crypto exchange
 *  or asset — the cash-out leg a mule network uses to leave the rupee
 *  banking system.
 *
 *  THE EVIDENCE PANEL IS NOT DECORATION.
 *  This detector has produced convincing false findings twice:
 *
 *    LIKE '%okx%'  168 "OKX" transactions. Inspecting them: "ASHOKX",
 *                  "ZOaazcokX010373" — a common Indian name and IMPS
 *                  reference characters.
 *    \beth\b       58 "Ethereum" transactions, which would have been
 *                  the largest category on this screen. Every one was
 *                  the same statement header: "JOINT HOLDERS : Cust ID
 *                  : 40943276 ETH".
 *
 *  Word boundaries fixed the first class and did nothing for the
 *  second, because ETH there IS a standalone word — just not the asset.
 *  Three-letter tickers were dropped entirely as a result.
 *
 *  That class of error is not closed: a new bank's narration format
 *  could reintroduce it tomorrow. So the screen shows real narrations
 *  with the matched term highlighted, and an officer can dismiss a bad
 *  finding in seconds instead of opening an inquiry on it.
 *
 *  MONEY FOLLOWS THE MONEY TRAIL RULE — chain-passed rows only, with
 *  untested rows reported as a COUNT and never summed.
 */
import { useEffect, useMemo, useState } from 'react';
import {
  Bitcoin, ShieldCheck, Users, ArrowRightLeft, FileSpreadsheet, FileText,
} from 'lucide-react';
import { toast } from 'sonner';
import * as XLSX from 'xlsx';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';

import { getCryptoTrail } from '../../lib/api/dashboard';
import { Pager, paginate, PAGE_SIZE } from '../common/Pager';
import CaveatNote from '../common/CaveatNote';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts';

import { bankKey, formatNumber } from '../../lib/utils/format';
import type {
  CryptoTrailSummary, CryptoEvidenceRow, CryptoAccountRow,
  CryptoExchangeRow,
} from '../../types';

const C_NAVY = 'var(--ksp-navy)';
const C_RED = '#b3261e';
const C_GREEN = '#1b7f4c';
const C_ORANGE = '#c67c1d';

//: Chart fills. Validated rather than chosen by eye -- both sit inside
//: the lightness band and above the chroma floor, and they separate by
//: dE 24.7 under protanopia and 32.7 under tritanopia against the chart
//: surface.
//:
//: The app's own navy was tried first and FAILED two checks: at
//: lightness 0.287 it is outside the band, and at chroma 0.067 it reads
//: as grey rather than as a colour. It is a good ink and a poor fill.
const C_BAR_MONEY = '#2a78d6';
const C_BAR_TXNS = '#eb6834';

const cardStyle = {
  background: '#fff',
  border: '1px solid rgba(11,44,74,0.12)',
  boxShadow: '0 1px 3px rgba(11,44,74,0.08)',
};

/** Whole rupees. Paise on a screen of 6-figure sums is noise. */
function rupees(n: number): string {
  return `₹${Math.round(n).toLocaleString('en-IN')}`;
}

function shortRupees(n: number): string {
  if (Math.abs(n) >= 1e7) return `₹${(n / 1e7).toFixed(2)} Cr`;
  if (Math.abs(n) >= 1e5) return `₹${(n / 1e5).toFixed(2)} L`;
  return rupees(n);
}

/** Labels that are a KEYWORD, not a counterparty.
 *
 *  The distinction is operational, not cosmetic. "BINANCE" or
 *  "MAPLETWIST" name somebody a request can be sent to; "CRYPTO" or
 *  "BITCOIN" only mean the narration used the word. Ranking them in one
 *  undifferentiated list invites reading a keyword count as an exchange
 *  exposure. */
const GENERIC_LABELS = new Set(['CRYPTO', 'USDT', 'BITCOIN', 'ETHEREUM']);

/** Direction of flow separates two operationally different behaviours
 *  that the Mule / Non-Mule tag alone does not.
 *
 *    OUT  the account sends fiat to a crypto venue -- the classic
 *         layering leg, fiat becomes crypto and leaves the jurisdiction.
 *    IN   the account RECEIVES fiat, with a venue named in the
 *         narration -- it sold crypto peer-to-peer. The people who paid
 *         it are ordinary buyers who will be traced next, and whose
 *         accounts get frozen when the chain is followed.
 *
 *  Measured on this corpus: 120 accounts are in-only and 55 out-only,
 *  and 89 of the in-only ones carry the Mule tag. Treating both with
 *  one investigative posture is how good-faith counterparties end up
 *  frozen.
 *
 *  Chain-verified amounts only, matching every other money figure here.
 *  An account with no verified amount is UNKNOWN, never guessed --
 *  14 of them, and a wrong guess is the expensive kind of wrong. */
type FlowRole = 'out' | 'in' | 'mixed' | 'unknown';

function flowRole(r: CryptoAccountRow): FlowRole {
  const out = r.debit > 0;
  const inn = r.credit > 0;
  if (out && inn) return 'mixed';
  if (out) return 'out';
  if (inn) return 'in';
  return 'unknown';
}

const ROLE_LABEL: Record<FlowRole, string> = {
  out: 'sends to venue',
  in: 'receives (P2P sale)',
  mixed: 'both directions',
  unknown: 'no verified amount',
};

const ROLE_SHORT: Record<FlowRole, string> = {
  out: 'OUT', in: 'IN', mixed: 'BOTH', unknown: '—',
};

const TYPES = ['All', 'Mule', 'Non-Mule', 'Victim'];

/** Highlight the matched term inside the narration.
 *
 *  Case-insensitive and literal — the label is a fixed token from a
 *  curated list, never a user-supplied pattern, so there is nothing to
 *  escape and no injection surface. Falls back to plain text when the
 *  label does not appear verbatim (e.g. "USDT" matched via "tether"). */
function Narration({ text, term }: { text: string; term: string }) {
  const i = text.toLowerCase().indexOf(term.toLowerCase());
  if (i < 0) return <span className="opacity-80">{text}</span>;
  return (
    <span className="opacity-80">
      {text.slice(0, i)}
      <mark style={{ background: 'rgba(198,124,29,0.28)', color: C_NAVY,
        fontWeight: 700, padding: '0 2px', borderRadius: 3 }}>
        {text.slice(i, i + term.length)}
      </mark>
      {text.slice(i + term.length)}
    </span>
  );
}

/** One definition per table, driving the screen's meaning AND both
 *  exports. Amounts stay NUMERIC for Excel so a spreadsheet can total a
 *  column; the PDF formats them on the way out. A rupee figure exported
 *  as "Rs 1.2L" is a string an officer cannot add up. */
const ACCOUNT_COLS: {
  header: string; get: (r: CryptoAccountRow) => string | number;
}[] = [
  { header: 'Account holder', get: (r) => r.account_holder_name ?? '' },
  { header: 'Account no', get: (r) => r.account_no ?? '' },
  { header: 'Bank', get: (r) => r.bank_name ?? '' },
  // Grouping key, exported alongside the entered spelling rather than
  // replacing it -- 327 stored names differ from another only by case
  // or spacing, which splits any pivot on the raw column.
  { header: 'Bank (grouping key)', get: (r) => bankKey(r.bank_name) },
  { header: 'Account type', get: (r) => r.account_type ?? '' },
  { header: 'FIR no', get: (r) => r.fir_no ?? '' },
  { header: 'Police station', get: (r) => r.ps_name ?? '' },
  { header: 'District', get: (r) => r.district ?? '' },
  { header: 'Exchanges', get: (r) => (r.exchanges ?? []).join(', ') },
  { header: 'Platforms used', get: (r) => (r.exchanges ?? []).length },
  { header: 'Flow direction', get: (r) => ROLE_SHORT[flowRole(r)] },
  { header: 'Flow reading', get: (r) => ROLE_LABEL[flowRole(r)] },
  { header: 'Spread flag',
    get: (r) => ((r.exchanges ?? []).length >= 3 ? 'YES' : '') },
  { header: 'Txns', get: (r) => r.txns },
  { header: 'Money out', get: (r) => r.debit },
  { header: 'Money in', get: (r) => r.credit },
  { header: 'First txn', get: (r) => r.first_txn ?? '' },
  { header: 'Last txn', get: (r) => r.last_txn ?? '' },
  // Carried into the export because the money columns above EXCLUDE
  // these rows. Without the count, a total looks complete when it is
  // not, and the qualification lives only on the screen it came from.
  { header: 'Unchecked txns', get: (r) => r.untested_txns },
];

const EXCHANGE_COLS: {
  header: string; get: (r: CryptoExchangeRow) => string | number;
}[] = [
  { header: 'Exchange / asset', get: (r) => r.exchange },
  { header: 'Txns', get: (r) => r.txns },
  { header: 'Accounts', get: (r) => r.accounts },
  { header: 'Money out', get: (r) => r.debit },
  { header: 'Money in', get: (r) => r.credit },
];

/** The narration is the point of this sheet. It is what lets an officer
 *  reject a false positive without opening the statement, and this
 *  detector has produced four of them on real data. */
const EVIDENCE_COLS: {
  header: string; get: (r: CryptoEvidenceRow) => string | number;
}[] = [
  { header: 'Exchange / asset', get: (r) => r.exchange },
  { header: 'Account holder', get: (r) => r.account_holder_name ?? '' },
  { header: 'Account no', get: (r) => r.account_no ?? '' },
  { header: 'FIR no', get: (r) => r.fir_no ?? '' },
  { header: 'Date', get: (r) => r.txn_date ?? '' },
  { header: 'Debit', get: (r) => r.debit },
  { header: 'Credit', get: (r) => r.credit },
  { header: 'Balance chain', get: (r) => (
    r.chain_ok === 1 ? 'passed' : r.chain_ok === 0 ? 'REJECTED' : 'untested') },
  { header: 'Bank narration (why it was flagged)', get: (r) => r.description ?? '' },
];

function sheet<T>(
  cols: { header: string; get: (r: T) => string | number }[], rows: T[],
) {
  const header = cols.map((c) => c.header);
  const body = rows.map((r) => cols.map((c) => c.get(r)));
  return { header, body };
}

export function CryptoTrailTab({ onTrace }: { onTrace?: (fir: string, psId: number) => void }) {
  const [data, setData] = useState<CryptoTrailSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [type, setType] = useState('All');
  const [page, setPage] = useState(1);
  // Evidence was the last panel on a long page, so the narrations that
  // let somebody REJECT a false positive were the hardest thing on the
  // screen to reach. Its own view, and its own page counter -- sharing
  // `page` with the accounts table would move both at once.
  const [section, setSection] = useState<'analysis' | 'evidence'>('analysis');
  const [evPage, setEvPage] = useState(1);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    getCryptoTrail(type)
      .then((d) => { if (alive) { setData(d); setPage(1); setEvPage(1); } })
      .catch((e) => { if (alive) toast.error(e?.message ?? 'Could not load crypto analysis'); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [type]);

  const rows = useMemo(() => data?.top_accounts ?? [], [data]);
  const pg = paginate(rows.length, page);
  const shown = pg.slice(rows);

  const stamp = new Date().toISOString().slice(0, 10);

  //: Every export carries this. A crypto finding read away from the
  //: screen it came from is exactly where a pattern match gets treated
  //: as a confirmed exchange transfer.
  const CAVEAT =
    'Flagged by matching the bank narration against a list of exchange '
    + 'and asset names. A match is a LEAD, not proof: verify the '
    + 'narration before acting. Money columns count only transactions '
    + 'whose statement balance chain reconciled; unchecked rows are '
    + 'counted separately and excluded from the totals.';

  function downloadExcel() {
    if (!data || !rows.length) { toast.error('Nothing to export.'); return; }
    const wb = XLSX.utils.book_new();
    // Three sheets, not one flattened table: the three answer different
    // questions and have no common grain.
    const add = (name: string, m: { header: string[]; body: (string | number)[][] }) => {
      if (!m.body.length) return;
      const ws = XLSX.utils.aoa_to_sheet([m.header, ...m.body]);
      ws['!cols'] = m.header.map((_, i) => ({
        wch: Math.min(60, Math.max(10, Math.max(String(m.header[i]).length,
          ...m.body.map((r) => String(r[i] ?? '').length)) + 2)) }));
      XLSX.utils.book_append_sheet(wb, ws, name);
    };
    add('Accounts', sheet(ACCOUNT_COLS, rows));
    add('By exchange', sheet(EXCHANGE_COLS, data.by_exchange));
    add('Evidence', sheet(EVIDENCE_COLS, data.evidence));
    XLSX.writeFile(wb, `crypto-analysis_${type.toLowerCase()}_${stamp}.xlsx`);
  }

  function downloadPdf() {
    if (!data || !rows.length) { toast.error('Nothing to export.'); return; }
    const doc = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'a3' });
    doc.setFontSize(14);
    doc.text('Crypto Analysis', 40, 40);
    doc.setFontSize(10);
    doc.text(`Account type: ${type}`
      + ` · ${formatNumber(data.total_txns)} flagged transaction`
      + `${data.total_txns === 1 ? '' : 's'}`
      + ` · ${formatNumber(data.accounts)} account`
      + `${data.accounts === 1 ? '' : 's'}`
      + ` · ${formatNumber(data.exchanges_seen)} exchange/asset`
      + `${data.exchanges_seen === 1 ? '' : 's'}`, 40, 58);
    doc.setFontSize(8);
    doc.text(doc.splitTextToSize(CAVEAT, 1050), 40, 74);

    const money = new Set(['Money out', 'Money in', 'Debit', 'Credit']);
    const section = <T,>(
      title: string,
      cols: { header: string; get: (r: T) => string | number }[],
      src: T[], startY: number,
    ): number => {
      if (!src.length) return startY;
      const { header, body } = sheet(cols, src);
      doc.setFontSize(11);
      doc.text(title, 40, startY);
      autoTable(doc, {
        startY: startY + 8, head: [header],
        body: body.map((r) => r.map((v, i) => (
          money.has(header[i]) ? rupees(Number(v) || 0) : String(v ?? '')))),
        styles: { fontSize: 7, cellPadding: 3, overflow: 'linebreak' },
        headStyles: { fillColor: [11, 44, 74] },
        alternateRowStyles: { fillColor: [245, 245, 247] },
      });
      // @ts-expect-error jspdf-autotable stamps this on the doc
      return (doc.lastAutoTable?.finalY ?? startY) + 28;
    };

    let y = section('Accounts with crypto activity', ACCOUNT_COLS, rows, 112);
    y = section('By exchange / asset', EXCHANGE_COLS, data.by_exchange, y);
    section('Evidence — why these were flagged', EVIDENCE_COLS, data.evidence, y);
    doc.save(`crypto-analysis_${type.toLowerCase()}_${stamp}.pdf`);
  }

  if (loading) {
    return <div className="text-center py-16 font-semibold" style={{ color: C_NAVY }}>
      Loading crypto analysis...
    </div>;
  }
  if (!data) return null;

  // "Never scanned" must not read as "no crypto found". One says the
  // corpus is clean; the other says nobody has looked.
  if (!data.scanned) {
    return (
      <div className="rounded-2xl p-8 text-center" style={cardStyle}>
        <Bitcoin className="w-10 h-10 mx-auto mb-3" style={{ color: C_ORANGE }} />
        <h3 className="font-bold text-lg mb-2" style={{ color: C_NAVY }}>
          Not yet analysed
        </h3>
        <p className="text-sm opacity-70 max-w-xl mx-auto">
          The crypto scan has never been run on this corpus, so this is not a
          statement that no crypto activity exists — only that nothing has
          looked for it yet. Run{' '}
          <code className="px-1.5 py-0.5 rounded" style={{ background: 'rgba(11,44,74,0.07)' }}>
            python -m analysis.build_crypto
          </code>{' '}
          to populate it.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        <Kpi label="Crypto transactions" value={formatNumber(data.total_txns)}
          accent={C_NAVY} sub="narration names an exchange" Icon={ArrowRightLeft} />
        <Kpi label="Accounts" value={formatNumber(data.accounts)}
          accent={C_RED} sub="with crypto activity" Icon={Users} />
        <Kpi label="Exchanges seen" value={formatNumber(data.exchanges_seen)}
          accent={C_NAVY} sub="distinct platforms" Icon={Bitcoin} />
        <Kpi label="Money out" value={shortRupees(data.total_debit)}
          accent={C_RED} sub="chain-verified only" Icon={ArrowRightLeft} />
        <Kpi label="Verified" value={data.untested_txns > 0
          ? `${formatNumber(data.untested_txns)} unchecked` : 'all checked'}
          accent={data.untested_txns > 0 ? C_ORANGE : C_GREEN}
          sub="excluded from the money" Icon={ShieldCheck} />
      </div>

      <CaveatNote summary="Matched from free-text narration">
        <strong>Read the narration before acting.</strong> These are matched from
        free-text bank narration, which has produced convincing false positives
        before — 168 “OKX” hits that were men named Ashok, and 58 “Ethereum” hits
        that were one bank header repeated. Three-letter tickers were removed as a
        result, but the risk is not closed. Every row below shows the text it
        matched on, with the term highlighted.
      </CaveatNote>

      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs font-bold uppercase tracking-wide opacity-60"
          style={{ color: C_NAVY }}>Account type</span>
        {TYPES.map((t) => (
          <button key={t} type="button" onClick={() => setType(t)}
            className="px-3 py-1 rounded-lg text-xs font-bold transition"
            style={{
              background: type === t ? C_NAVY : '#fff',
              color: type === t ? 'var(--ksp-yellow)' : C_NAVY,
              border: `1px solid ${type === t ? C_NAVY : 'rgba(11,44,74,0.18)'}`,
            }}>
            {t}
          </button>
        ))}
      </div>

      {/* Two views rather than one long scroll. The charts and the
          accounts table answer "what is happening"; the evidence answers
          "is this row real", which is a different job and was buried
          three panels below the fold. */}
      <div className="flex items-center gap-1.5">
        {([
          ['analysis', `Analysis`],
          ['evidence', `Evidence (${formatNumber(data.evidence.length)})`],
        ] as const).map(([v, label]) => (
          <button key={v} type="button" onClick={() => setSection(v)}
            className="px-3 py-1.5 rounded-lg text-xs font-bold transition"
            style={{
              background: section === v ? C_NAVY : '#fff',
              color: section === v ? 'var(--ksp-yellow)' : C_NAVY,
              border: `1px solid ${section === v ? C_NAVY : 'rgba(11,44,74,0.18)'}`,
            }}>
            {label}
          </button>
        ))}
      </div>

      {section === 'analysis' && (<>

      {/* ---- by exchange: two column charts ----
           TWO CHARTS, NOT ONE WITH TWO AXES. Money and transaction count
           are different measures on different scales, and putting them
           on a shared plot with two y-axes lets the reader infer a
           relationship from whichever scaling was chosen. Side by side,
           each chart carries one honest scale.

           The comparison is the point: MUDREX is tallest on the right
           and barely visible on the left; MAPLETWIST is the reverse.
           Busiest and biggest are different counterparties, and seeing
           both at once is what makes that legible. */}
      {data.by_exchange.length > 0 && (() => {
        const rows = data.by_exchange;          // server order: money desc
        // Each chart ranked by ITS OWN measure, so both read as a clean
        // descending staircase. The categories therefore appear in a
        // different order in each panel -- which is the finding, not a
        // defect: the counterparty at the top of one is not the one at
        // the top of the other. Copy before sorting; sort() mutates.
        const rowsByTxns = [...rows].sort((a, b) => b.txns - a.txns);
        // Wide enough that ~20 categories keep readable labels; the
        // container scrolls rather than compressing them into noise.
        // Per PANEL now, not for the pair. 44px a category keeps the
        // rotated labels apart; the panel scrolls to reach the rest.
        const chartW = Math.max(420, rows.length * 44);

        const axis = { fontSize: 10, fill: '#52514e' };
        // `interval` is a prop of <XAxis>, NOT part of `tick`. Setting
        // it here did nothing, so recharts kept its default of dropping
        // labels that would collide -- which is why some columns had no
        // name under them. Every category is nameable here, so the axis
        // below passes interval={0} and the panel scrolls instead.
        const tick = {
          angle: -45, textAnchor: 'end' as const, ...axis, dy: 4,
        };

        return (
        <div className="rounded-2xl overflow-hidden" style={cardStyle}>
          <div className="px-5 py-4" style={{ borderBottom: '3px solid var(--ksp-yellow)' }}>
            <h3 className="text-sm font-bold" style={{ color: C_NAVY }}>
              Where the money went
            </h3>
            <p className="text-xs mt-1 opacity-60">
              Left: <b>chain-verified money out</b>. Right: <b>transaction count</b>. Each ranked by its own measure, so the order differs between them — the biggest counterparty is not the busiest.
              Separate scales on purpose — the busiest counterparty and the
              biggest one are not the same. Each panel scrolls on its own, so one can be held still while the
              other is moved. Hover any column for detail.
            </p>
          </div>

          {/* TWO scrollers, not one. A single shared scroll moved both
              charts together, so the reader could never hold one still
              and travel the other -- which is the whole point of showing
              them together, since the tall column is in a different
              place on each. Each panel now owns its scrollbar and its
              half of the width. */}
          <div className="flex gap-4 p-4 items-start">

              {/* money */}
              <div className="flex-1 min-w-0 rounded-xl"
                style={{ border: '2px solid rgba(11,44,74,0.28)',
                         background: '#fff' }}>
                <div className="text-sm font-bold px-3 py-2 tracking-tight"
                  style={{ color: C_NAVY, background: 'rgba(11,44,74,0.07)',
                           borderBottom: '1px solid rgba(11,44,74,0.18)' }}>
                  Money out (chain-verified)
                </div>
                <div className="overflow-x-auto pb-1">
                <div style={{ width: chartW }}>
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={rows} margin={{ top: 6, right: 8, left: 4, bottom: 62 }}>
                    <CartesianGrid strokeDasharray="0" stroke="rgba(11,44,74,0.08)"
                      vertical={false} />
                    <XAxis dataKey="exchange" tick={tick} height={62}
                      interval={0} stroke="rgba(11,44,74,0.25)" />
                    <YAxis tick={axis} stroke="rgba(11,44,74,0.25)"
                      tickFormatter={(v: number) => shortRupees(v)} width={64} />
                    <Tooltip
                      formatter={(v) => [shortRupees(Number(v)), 'Money out']}
                      contentStyle={{ fontSize: 11, borderRadius: 8 }} />
                    {/* 4px rounded data-end, square at the baseline. */}
                    <Bar dataKey="debit" radius={[4, 4, 0, 0]} maxBarSize={24}
                      isAnimationActive={false}>
                      {rows.map((e) => (
                        // Same hue throughout: height is the encoding, so
                        // shading by magnitude would say it twice. Asset
                        // mentions are held back because they are not a
                        // counterparty anyone can act on.
                        <Cell key={e.exchange} fill={C_BAR_MONEY}
                          fillOpacity={GENERIC_LABELS.has(e.exchange) ? 0.42 : 1} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                </div>
                </div>
              </div>

              {/* transactions */}
              <div className="flex-1 min-w-0 rounded-xl"
                style={{ border: '2px solid rgba(11,44,74,0.28)',
                         background: '#fff' }}>
                <div className="text-sm font-bold px-3 py-2 tracking-tight"
                  style={{ color: C_NAVY, background: 'rgba(11,44,74,0.07)',
                           borderBottom: '1px solid rgba(11,44,74,0.18)' }}>
                  Transactions
                </div>
                <div className="overflow-x-auto pb-1">
                <div style={{ width: chartW }}>
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={rowsByTxns} margin={{ top: 6, right: 8, left: 4, bottom: 62 }}>
                    <CartesianGrid strokeDasharray="0" stroke="rgba(11,44,74,0.08)"
                      vertical={false} />
                    <XAxis dataKey="exchange" tick={tick} height={62}
                      interval={0} stroke="rgba(11,44,74,0.25)" />
                    <YAxis tick={axis} stroke="rgba(11,44,74,0.25)"
                      tickFormatter={(v: number) => formatNumber(v)} width={44} />
                    <Tooltip
                      formatter={(v, _k, item) => [
                        `${formatNumber(Number(v))} txn · `
                        + `${formatNumber(Number(item?.payload?.accounts ?? 0))} account(s)`,
                        'Activity']}
                      contentStyle={{ fontSize: 11, borderRadius: 8 }} />
                    <Bar dataKey="txns" radius={[4, 4, 0, 0]} maxBarSize={24}
                      isAnimationActive={false}>
                      {rowsByTxns.map((e) => (
                        <Cell key={e.exchange} fill={C_BAR_TXNS}
                          fillOpacity={GENERIC_LABELS.has(e.exchange) ? 0.42 : 1} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                </div>
                </div>
              </div>

          </div>

          <div className="px-5 pb-4 flex flex-wrap gap-4 text-[10px]"
            style={{ color: '#52514e' }}>
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-3 h-3 rounded-sm"
                style={{ background: C_BAR_MONEY }} />
              named counterparty — somebody a request can be sent to
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-3 h-3 rounded-sm"
                style={{ background: C_BAR_MONEY, opacity: 0.42 }} />
              asset mention — the narration only used the word
            </span>
            <span className="opacity-70">
              A short money bar beside a tall transaction bar means the amounts
              failed the balance check, not that little moved.
            </span>
          </div>
        </div>
        );
      })()}

      {/* ---- accounts ---- */}
      <div className="rounded-2xl overflow-hidden" style={cardStyle}>
        <div className="px-5 py-4 flex items-center gap-4 flex-wrap"
          style={{ borderBottom: '3px solid var(--ksp-yellow)' }}>
          <div>
            <h3 className="text-sm font-bold" style={{ color: C_NAVY }}>
              Accounts with crypto activity
            </h3>
            {/* The Flow column exists because of a specific risk, and a
                column nobody understands is a column nobody uses. */}
            <p className="text-xs mt-1 opacity-70" style={{ maxWidth: 640 }}>
              <b>Flow</b> is the direction of the money.
              <b> OUT</b> — the account paid a venue: the layering leg.
              <b> IN</b> — the account was paid, with a venue named in the
              narration: it sold crypto peer-to-peer, and the people who
              paid it are the next accounts a trace will reach.
              Two different behaviours; the same investigative posture on
              both is how good-faith counterparties get frozen.
            </p>
          </div>
          {/* ml-auto, not justify-end: these are flex ITEMS sized to
              their content, so without it they sit next to the heading
              rather than at the far edge. */}
          <div className="flex gap-2 items-center ml-auto">
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
          <div className="px-5 py-8 text-center text-sm opacity-60">
            No crypto-linked transactions for this account type.
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr style={{ background: 'rgba(11,44,74,0.05)' }}>
                    {['Account holder', 'FIR / PS', 'Flow', 'Exchanges', 'Txns', 'Out', 'In', 'Period']
                      .map((h, i) => (
                        <th key={h} className={`px-2 py-2 font-bold ${i >= 4 && i <= 6 ? 'text-right' : 'text-left'}`}
                          style={{ color: C_NAVY }}>{h}</th>
                      ))}
                  </tr>
                </thead>
                <tbody>
                  {shown.map((a) => (
                    <tr key={a.account_id} style={{ borderTop: '1px solid rgba(11,44,74,0.07)' }}>
                      <td className="px-2 py-1.5 max-w-[210px]">
                        {onTrace && a.fir_no && a.ps_id ? (
                          <button type="button" onClick={() => onTrace(a.fir_no!, a.ps_id!)}
                            title={`Trace FIR ${a.fir_no}`}
                            className="font-semibold block truncate text-left w-full hover:underline"
                            style={{ color: C_NAVY, cursor: 'pointer' }}>
                            {a.account_holder_name || '—'}
                          </button>
                        ) : (
                          <span className="font-semibold block truncate" style={{ color: C_NAVY }}>
                            {a.account_holder_name || '—'}
                          </span>
                        )}
                        <span className="block text-[10px] opacity-55 truncate">
                          {a.bank_name || ''} · {a.account_no || ''}
                        </span>
                      </td>
                      <td className="px-2 py-1.5">
                        <span className="block truncate">{a.fir_no || '—'}</span>
                        <span className="block text-[10px] opacity-55 truncate">{a.ps_name || ''}</span>
                      </td>
                      <td className="px-2 py-1.5">
                        {(() => {
                          const role = flowRole(a);
                          const tone = role === 'out'
                            ? { bg: 'rgba(235,104,52,0.16)', fg: '#b8461c' }
                            : role === 'in'
                            ? { bg: 'rgba(42,120,214,0.16)', fg: '#1c5cab' }
                            : role === 'mixed'
                            ? { bg: 'rgba(11,44,74,0.10)', fg: C_NAVY }
                            : { bg: 'rgba(11,44,74,0.05)', fg: '#8a94a0' };
                          return (
                            <span className="px-1.5 py-px rounded text-[9px] font-bold whitespace-nowrap"
                              style={{ background: tone.bg, color: tone.fg }}
                              title={ROLE_LABEL[role]}>
                              {ROLE_SHORT[role]}
                            </span>
                          );
                        })()}
                      </td>
                      <td className="px-2 py-1.5">
                        <div className="flex flex-wrap gap-1 items-center">
                          {a.exchanges.map((x) => (
                            <span key={x} className="px-1.5 py-px rounded text-[9px] font-bold"
                              style={{ background: 'rgba(198,124,29,0.16)', color: C_ORANGE }}>{x}</span>
                          ))}
                          {/* Spreading across three or more platforms is a
                              behaviour, not a volume. 9 accounts in the
                              corpus do it (one uses five); most use one.
                              Worth seeing without counting chips. */}
                          {a.exchanges.length >= 3 && (
                            <span
                              className="px-1.5 py-px rounded text-[9px] font-bold"
                              style={{ background: C_RED, color: '#fff' }}
                              title={`Uses ${a.exchanges.length} different platforms — `
                                + `deliberate spreading, not incidental`}>
                              {a.exchanges.length}&times; SPREAD
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-2 py-1.5 text-right">
                        {formatNumber(a.txns)}
                        {a.untested_txns > 0 && (
                          <span className="block text-[9px] font-semibold" style={{ color: C_ORANGE }}
                            title={`${a.untested_txns} rows had no balance column to check against`}>
                            {formatNumber(a.untested_txns)} unchecked
                          </span>
                        )}
                      </td>
                      <td className="px-2 py-1.5 text-right font-semibold whitespace-nowrap"
                        style={{ color: C_RED }}>{rupees(a.debit)}</td>
                      <td className="px-2 py-1.5 text-right font-semibold whitespace-nowrap"
                        style={{ color: C_GREEN }}>{rupees(a.credit)}</td>
                      <td className="px-2 py-1.5 text-[10px] opacity-70 whitespace-nowrap">
                        {a.first_txn || '—'}<br />{a.last_txn || ''}
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

      </>)}

      {/* ---- evidence ---- */}
      {section === 'evidence' && data.evidence.length > 0 && (() => {
        const ev = paginate(data.evidence.length, evPage);
        const evRows = ev.slice(data.evidence);
        return (
        <div className="rounded-2xl overflow-hidden" style={cardStyle}>
          <div className="px-5 py-4" style={{ borderBottom: '3px solid var(--ksp-yellow)' }}>
            <h3 className="text-sm font-bold" style={{ color: C_NAVY }}>Evidence — why these were flagged</h3>
            <div className="mt-1">
              <CaveatNote summary="Raw narration — check for false positives">
                The actual bank narration, with the matched term highlighted. If a
                row looks like a reference code or a person’s name rather than a
                crypto platform, it is a false positive — tell us and the pattern
                gets removed.
              </CaveatNote>
            </div>
          </div>
          <div className="divide-y" style={{ borderColor: 'rgba(11,44,74,0.07)' }}>
            {evRows.map((e: CryptoEvidenceRow, i) => (
              <div key={i} className="px-4 py-2 text-xs">
                <div className="flex items-center gap-2 flex-wrap mb-0.5">
                  <span className="px-1.5 py-px rounded text-[9px] font-bold"
                    style={{ background: 'rgba(198,124,29,0.16)', color: C_ORANGE }}>{e.exchange}</span>
                  <span className="font-semibold" style={{ color: C_NAVY }}>
                    {e.account_holder_name || '—'}
                  </span>
                  <span className="opacity-55">{e.fir_no || ''}</span>
                  <span className="opacity-55">{e.txn_date || ''}</span>
                  {e.debit > 0 && <span style={{ color: C_RED }}>{rupees(e.debit)} out</span>}
                  {e.credit > 0 && <span style={{ color: C_GREEN }}>{rupees(e.credit)} in</span>}
                  {e.chain_ok !== 1 && (
                    <span className="px-1 rounded text-[9px] font-bold"
                      style={{ background: 'rgba(198,124,29,0.16)', color: C_ORANGE }}
                      title={e.chain_ok === 0
                        ? 'This row failed its balance check — amounts excluded'
                        : 'Nothing to check this row against — amounts excluded'}>
                      {e.chain_ok === 0 ? 'REJECTED' : 'UNCHECKED'}
                    </span>
                  )}
                </div>
                <div className="font-mono text-[10px] leading-relaxed break-all">
                  <Narration text={e.description || ''} term={e.exchange} />
                </div>
              </div>
            ))}
          </div>
          <Pager total={data.evidence.length} page={ev.safePage}
            pageCount={ev.pageCount} onPage={setEvPage}
            noun="narrations" size={PAGE_SIZE} />
        </div>
        );
      })()}
    </div>
  );
}

function Kpi({ label, value, sub, accent, Icon }: {
  label: string; value: string; sub?: string; accent: string;
  Icon: React.ComponentType<{ className?: string; style?: React.CSSProperties }>;
}) {
  return (
    <div className="rounded-2xl p-4" style={cardStyle}>
      <div className="flex items-center gap-2 mb-1">
        <Icon className="w-4 h-4" style={{ color: accent }} />
        <span className="text-[11px] font-bold uppercase tracking-wide opacity-60"
          style={{ color: C_NAVY }}>{label}</span>
      </div>
      <div className="text-2xl font-black tabular-nums" style={{ color: accent }}>{value}</div>
      {sub && <div className="text-[10px] opacity-55 mt-0.5">{sub}</div>}
    </div>
  );
}
