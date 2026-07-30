import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import {
  BarChart3, Landmark, Wallet, MapPin,
} from 'lucide-react';
import {
  BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import {
  getNcrpSummary, getNcrpPsComparison, getNcrpTopBanks,
  getNcrpLayerDistribution, getNcrpTopAtmLocations,
} from '../lib/api/dashboard';
import { formatNumber, todayISO, isoDaysAgo } from '../lib/utils/format';
import { useAuthStore } from '../lib/stores/auth-store';
import type {
  NcrpKpiSummary, NcrpPsReportCount, NcrpBankConcentration,
  NcrpAtmLocation, LayerBucket,
} from '../types';

/** NCRP Dashboard -- super_admin cross-PS view of everything in
 *  mule_reports + its six transaction children. KPI cards are
 *  cumulative to a picked date; the charts + per-PS table use a
 *  from/to range so trends can be sliced. mule_reports has no
 *  ps_id column (pre-dates migration 008) so the backend derives
 *  per-PS via users.ps_id from submitted_by. */

const cardStyle = {
  background: '#fff',
  border: '1px solid rgba(0,0,0,0.06)',
  boxShadow: '0 6px 16px rgba(0,0,0,0.08)',
};

const COLOR_NAVY   = '#0b2c4a';
const COLOR_MULE   = '#8b1919';
const COLOR_ORANGE = '#c67c1d';
const COLOR_PURPLE = '#6a1b9a';
const COLOR_TEAL   = '#00695c';

// Layer palette shared with the Accounts Deep Analysis colour map.
// Same layer -> same colour in both dashboards is a deliberate cue.
const LAYER_PALETTE = [
  '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
  '#8c564b', '#e377c2', '#17becf', '#bcbd22', '#7f7f7f',
  '#aec7e8', '#ffbb78', '#98df8a', '#ff9896', '#c5b0d5',
];
const layerColor = (l: number): string =>
  LAYER_PALETTE[(l - 1 + LAYER_PALETTE.length) % LAYER_PALETTE.length];

function KpiCard({ label, value, sub, accent, Icon }: {
  label: string; value: string; sub?: string; accent: string;
  Icon?: typeof Wallet;
}) {
  return (
    <div className="rounded-2xl p-4 relative overflow-hidden flex flex-col"
      style={{ ...cardStyle, borderLeft: `6px solid ${accent}` }}>
      {Icon && (
        <Icon className="absolute right-3 top-3 opacity-10 w-14 h-14"
          style={{ color: accent }} />
      )}
      <p className="text-[11px] uppercase tracking-wide font-bold leading-tight
                    min-h-[1.75rem] flex items-start"
        style={{ color: accent }}>{label}</p>
      <p className="text-2xl font-bold tabular-nums leading-none mt-1"
        style={{ color: 'var(--ksp-navy)' }}>{value}</p>
      <p className="text-xs opacity-60 mt-1 leading-tight min-h-[1rem]">
        {sub || ' '}
      </p>
    </div>
  );
}

function ChartCard({ title, hint, accent, children }: {
  title: string; hint?: string; accent: string; children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl overflow-hidden" style={cardStyle}>
      <div className="px-5 py-3" style={{ borderTop: `4px solid ${accent}` }}>
        <h3 className="text-sm font-bold" style={{ color: 'var(--ksp-navy)' }}>{title}</h3>
        {hint && <p className="text-xs opacity-60 mt-0.5">{hint}</p>}
      </div>
      <div className="px-5 pb-5">
        {children}
      </div>
    </div>
  );
}

// Money formatting -- ₹ 1.23L / ₹ 4.56Cr for chart axes; full
// grouped Indian formatting elsewhere.
function shortRupees(v: number): string {
  const n = Number(v) || 0;
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(1)}Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(1)}L`;
  if (n >= 1e3) return `₹${(n / 1e3).toFixed(1)}K`;
  return `₹${n.toFixed(0)}`;
}

export function NcrpDashboardPage() {
  const { user } = useAuthStore();
  const isSuperAdmin = user?.role === 'super_admin';

  // Cumulative KPI date (single picker) + independent from/to for
  // charts + table. Default range: last 30 days ending today.
  const [asOfDate, setAsOfDate] = useState(todayISO());
  const [rangeFrom, setRangeFrom] = useState(isoDaysAgo(30));
  const [rangeTo, setRangeTo] = useState(todayISO());

  const [summary, setSummary] = useState<NcrpKpiSummary | null>(null);
  const [psRows, setPsRows] = useState<NcrpPsReportCount[]>([]);
  const [topBanks, setTopBanks] = useState<NcrpBankConcentration[]>([]);
  const [layerDist, setLayerDist] = useState<LayerBucket[]>([]);
  const [topAtms, setTopAtms] = useState<NcrpAtmLocation[]>([]);
  const [loading, setLoading] = useState(true);

  // KPI cards -- reload only when the cumulative date changes.
  useEffect(() => {
    if (!isSuperAdmin) return;
    getNcrpSummary(asOfDate)
      .then(setSummary)
      .catch((e) => {
        setSummary(null);
        toast.error(`Summary: ${e instanceof Error ? e.message : 'failed'}`);
      });
  }, [asOfDate, isSuperAdmin]);

  // Range-scoped panels -- reload when from/to change.
  useEffect(() => {
    if (!isSuperAdmin) return;
    if (rangeFrom > rangeTo) {
      toast.error('Range "From" must be on or before "To".');
      return;
    }
    setLoading(true);
    Promise.allSettled([
      getNcrpPsComparison(rangeFrom, rangeTo),
      getNcrpTopBanks(rangeFrom, rangeTo, 10),
      getNcrpLayerDistribution(rangeFrom, rangeTo),
      getNcrpTopAtmLocations(rangeFrom, rangeTo, 10),
    ]).then(([p, b, l, a]) => {
      if (p.status === 'fulfilled') setPsRows(p.value);
      else { setPsRows([]); toast.error(`Per-PS: ${(p as any).reason?.message ?? 'failed'}`); }
      if (b.status === 'fulfilled') setTopBanks(b.value);
      else { setTopBanks([]); toast.error(`Top banks: ${(b as any).reason?.message ?? 'failed'}`); }
      if (l.status === 'fulfilled') setLayerDist(l.value);
      else { setLayerDist([]); toast.error(`Layers: ${(l as any).reason?.message ?? 'failed'}`); }
      if (a.status === 'fulfilled') setTopAtms(a.value);
      else { setTopAtms([]); toast.error(`ATM: ${(a as any).reason?.message ?? 'failed'}`); }
      setLoading(false);
    });
  }, [rangeFrom, rangeTo, isSuperAdmin]);

  const psSummary = useMemo(() => {
    const active = psRows.filter((r) => r.report_count > 0).length;
    const total = psRows.reduce((s, r) => s + r.report_count, 0);
    return { active, total };
  }, [psRows]);

  if (!isSuperAdmin) {
    return (
      <div className="rounded-2xl p-8 text-center italic" style={cardStyle}>
        NCRP Dashboard is restricted to super_admin.
      </div>
    );
  }

  return (
    <div>
      {/* Header + date pickers */}
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div>
          <h1 className="text-[22px] font-bold mb-1 flex items-center gap-2" style={{ color: 'var(--ksp-navy)' }}>
            <BarChart3 className="w-5 h-5" /> NCRP Dashboard
          </h1>
          <p className="text-sm font-medium" style={{ color: 'var(--ksp-red)' }}>
            Cross-PS mule-report activity. KPI cards are cumulative to the "As of" date; charts + per-PS
            table cover the "From → To" range.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-sm flex items-center gap-2">
            <span className="font-semibold" style={{ color: 'var(--ksp-navy)' }}>As of:</span>
            <input type="date" value={asOfDate} onChange={(e) => setAsOfDate(e.target.value)}
              className="px-3 py-1.5 rounded-lg text-sm bg-white"
              style={{ border: '2px solid var(--ksp-navy)' }} />
          </label>
          <label className="text-sm flex items-center gap-2">
            <span className="font-semibold" style={{ color: 'var(--ksp-navy)' }}>From:</span>
            <input type="date" value={rangeFrom} onChange={(e) => setRangeFrom(e.target.value)}
              className="px-3 py-1.5 rounded-lg text-sm bg-white"
              style={{ border: '2px solid var(--ksp-navy)' }} />
          </label>
          <label className="text-sm flex items-center gap-2">
            <span className="font-semibold" style={{ color: 'var(--ksp-navy)' }}>To:</span>
            <input type="date" value={rangeTo} onChange={(e) => setRangeTo(e.target.value)}
              className="px-3 py-1.5 rounded-lg text-sm bg-white"
              style={{ border: '2px solid var(--ksp-navy)' }} />
          </label>
        </div>
      </div>

      {/* KPI row -- cumulative to `asOfDate`. */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
        <KpiCard label="Total Mule Reports"
          value={formatNumber(summary?.total_reports ?? 0)}
          sub="Submitted NCRP reports"
          accent={COLOR_NAVY} Icon={BarChart3} />
        <KpiCard label="Unique Banks"
          value={formatNumber(summary?.unique_banks ?? 0)}
          sub="Distinct across money transfers"
          accent={COLOR_TEAL} Icon={Landmark} />
        <KpiCard label="Money Transferred"
          value={shortRupees(summary?.total_transfer_amount ?? 0)}
          sub="Sum of money_transfers.amount"
          accent={COLOR_MULE} Icon={Wallet} />
        <KpiCard label="ATM + AEPS Withdrawn"
          value={shortRupees(summary?.total_atm_aeps_amount ?? 0)}
          sub="Cash pulled at ATMs + AEPS"
          accent={COLOR_ORANGE} Icon={MapPin} />
      </div>

      {loading && (
        <p className="text-sm italic opacity-60 mb-3" style={{ color: 'var(--ksp-navy)' }}>
          Loading range panels…
        </p>
      )}

      {/* Row 1: Top Banks (left) + Layer Distribution (right) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <ChartCard title="Top 10 Banks by Money Transfers"
          hint="Distinct banks referenced in money_transfers rows within the range."
          accent={COLOR_MULE}>
          {topBanks.length === 0 ? (
            <div className="py-10 text-center italic opacity-60 text-sm">No money-transfer rows in this range.</div>
          ) : (
            <div style={{ width: '100%', height: 300 }}>
              <ResponsiveContainer>
                <BarChart data={topBanks} layout="vertical"
                          margin={{ top: 8, right: 16, bottom: 8, left: 120 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                  <XAxis type="number" tick={{ fontSize: 11 }} />
                  <YAxis type="category" dataKey="bank" tick={{ fontSize: 11 }} width={110}
                    interval={0} />
                  <Tooltip
                    formatter={(v, name) => {
                      if (name === 'transfer_count') return [formatNumber(Number(v)), 'Transfers'];
                      return [shortRupees(Number(v)), 'Amount'];
                    }} />
                  <Bar dataKey="transfer_count" name="transfer_count" fill={COLOR_MULE} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </ChartCard>

        <ChartCard title="Layer Distribution (Money Transfers)"
          hint="How deep the money trail goes. Layer 1 = first hop from victim."
          accent={COLOR_PURPLE}>
          {layerDist.length === 0 ? (
            <div className="py-10 text-center italic opacity-60 text-sm">No layered transfers in this range.</div>
          ) : (
            <div style={{ width: '100%', height: 300 }}>
              <ResponsiveContainer>
                <BarChart data={layerDist}
                          margin={{ top: 8, right: 16, bottom: 8, left: 16 }}
                          barCategoryGap="15%">
                  <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                  <XAxis dataKey="layer" tick={{ fontSize: 11 }}
                    tickFormatter={(v) => `L${v}`} />
                  <YAxis tick={{ fontSize: 11 }}
                    tickFormatter={(v) => formatNumber(v)} />
                  <Tooltip
                    formatter={(v) => [formatNumber(Number(v)), 'Transfers']}
                    labelFormatter={(v) => `Layer ${v}`} />
                  <Bar dataKey="count" name="Transfers">
                    {layerDist.map((p) => (
                      <Cell key={p.layer} fill={layerColor(p.layer)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </ChartCard>
      </div>

      {/* Row 2: Top ATM locations */}
      <ChartCard title="Top 10 ATM Locations by Withdrawn Amount"
        hint="Ranked by ₹ withdrawn. Location is free-text; same physical ATM may appear under multiple spellings."
        accent={COLOR_ORANGE}>
        {topAtms.length === 0 ? (
          <div className="py-10 text-center italic opacity-60 text-sm">No ATM withdrawals in this range.</div>
        ) : (
          <div style={{ width: '100%', height: 320 }}>
            <ResponsiveContainer>
              <BarChart data={topAtms} layout="vertical"
                        margin={{ top: 8, right: 16, bottom: 8, left: 160 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                <XAxis type="number" tick={{ fontSize: 11 }}
                  tickFormatter={(v) => shortRupees(Number(v))} />
                <YAxis type="category" dataKey="atm_location" tick={{ fontSize: 11 }} width={150}
                  interval={0} />
                <Tooltip
                  formatter={(v, name) => {
                    if (name === 'total_amount') return [shortRupees(Number(v)), 'Amount'];
                    return [formatNumber(Number(v)), 'Withdrawals'];
                  }} />
                <Bar dataKey="total_amount" name="total_amount" fill={COLOR_ORANGE} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </ChartCard>

      {/* Per-PS report count table -- every active PS, zero-filled. */}
      <div className="mt-6 rounded-2xl overflow-hidden" style={cardStyle}>
        <div className="px-5 py-3" style={{ borderTop: `4px solid ${COLOR_NAVY}` }}>
          <h3 className="text-sm font-bold" style={{ color: 'var(--ksp-navy)' }}>
            Per-PS Mule Report Count
          </h3>
          <p className="text-xs opacity-60 mt-0.5">
            All active PSes. Silent stations show 0. {psSummary.active} of {psRows.length} PSes
            reporting; {formatNumber(psSummary.total)} total reports in range.
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" style={{ tableLayout: 'fixed' }}>
            <colgroup>
              <col style={{ width: '10%' }} />
              <col style={{ width: '35%' }} />
              <col style={{ width: '40%' }} />
              <col style={{ width: '15%' }} />
            </colgroup>
            <thead style={{ background: '#f5f5f7' }}>
              <tr>
                <th className="px-3 py-2 text-left">#</th>
                <th className="px-3 py-2 text-left">District</th>
                <th className="px-3 py-2 text-left">Police Station</th>
                <th className="px-3 py-2 text-right">Reports</th>
              </tr>
            </thead>
            <tbody>
              {psRows.length === 0 && (
                <tr><td colSpan={4} className="px-3 py-8 text-center italic opacity-60">
                  No active PSes returned.
                </td></tr>
              )}
              {psRows.map((r, i) => (
                <tr key={r.ps_id} className="border-t border-slate-100">
                  <td className="px-3 py-2 font-mono">{i + 1}</td>
                  <td className="px-3 py-2 truncate" title={r.district}>{r.district}</td>
                  <td className="px-3 py-2 truncate" title={r.ps_name}>{r.ps_name}</td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums"
                    style={{
                      color: r.report_count > 0 ? 'var(--ksp-navy)' : 'rgba(0,0,0,0.35)',
                      fontWeight: r.report_count > 0 ? 700 : 400,
                    }}>
                    {formatNumber(r.report_count)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
