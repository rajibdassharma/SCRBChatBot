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
import { Bitcoin, ShieldCheck, Users, ArrowRightLeft } from 'lucide-react';
import { toast } from 'sonner';

import { getCryptoTrail } from '../../lib/api/dashboard';
import { Pager, paginate, PAGE_SIZE } from '../common/Pager';
import CaveatNote from '../common/CaveatNote';
import { formatNumber } from '../../lib/utils/format';
import type { CryptoTrailSummary, CryptoEvidenceRow } from '../../types';

const C_NAVY = 'var(--ksp-navy)';
const C_RED = '#b3261e';
const C_GREEN = '#1b7f4c';
const C_ORANGE = '#c67c1d';

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

export function CryptoTrailTab({ onTrace }: { onTrace?: (fir: string, psId: number) => void }) {
  const [data, setData] = useState<CryptoTrailSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [type, setType] = useState('All');
  const [page, setPage] = useState(1);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    getCryptoTrail(type)
      .then((d) => { if (alive) { setData(d); setPage(1); } })
      .catch((e) => { if (alive) toast.error(e?.message ?? 'Could not load crypto analysis'); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [type]);

  const rows = useMemo(() => data?.top_accounts ?? [], [data]);
  const pg = paginate(rows.length, page);
  const shown = pg.slice(rows);

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

      {/* ---- by exchange ---- */}
      {data.by_exchange.length > 0 && (
        <div className="rounded-2xl overflow-hidden" style={cardStyle}>
          <div className="px-5 py-4" style={{ borderBottom: '3px solid var(--ksp-yellow)' }}>
            <h3 className="text-sm font-bold" style={{ color: C_NAVY }}>By exchange / asset</h3>
          </div>
          <div className="p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-2">
            {data.by_exchange.map((e) => (
              <div key={e.exchange} className="flex justify-between text-xs">
                <span className="font-bold" style={{ color: C_NAVY }}>{e.exchange}</span>
                <span className="opacity-70">
                  {formatNumber(e.txns)} txn · {formatNumber(e.accounts)} acct · {shortRupees(e.debit)} out
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ---- accounts ---- */}
      <div className="rounded-2xl overflow-hidden" style={cardStyle}>
        <div className="px-5 py-4" style={{ borderBottom: '3px solid var(--ksp-yellow)' }}>
          <h3 className="text-sm font-bold" style={{ color: C_NAVY }}>
            Accounts with crypto activity
          </h3>
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
                    {['Account holder', 'FIR / PS', 'Exchanges', 'Txns', 'Out', 'In', 'Period']
                      .map((h, i) => (
                        <th key={h} className={`px-2 py-2 font-bold ${i >= 3 && i <= 5 ? 'text-right' : 'text-left'}`}
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
                        <div className="flex flex-wrap gap-1">
                          {a.exchanges.map((x) => (
                            <span key={x} className="px-1.5 py-px rounded text-[9px] font-bold"
                              style={{ background: 'rgba(198,124,29,0.16)', color: C_ORANGE }}>{x}</span>
                          ))}
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

      {/* ---- evidence ---- */}
      {data.evidence.length > 0 && (
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
            {data.evidence.map((e: CryptoEvidenceRow, i) => (
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
        </div>
      )}
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
