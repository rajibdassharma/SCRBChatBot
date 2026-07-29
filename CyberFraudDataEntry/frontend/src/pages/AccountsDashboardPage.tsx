import { useEffect, useMemo, useState } from 'react';
import {
  BarChart3, Users, ShieldAlert, HelpCircle, MapPin, Camera,
  Trophy, FileDown, FileSpreadsheet,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  LineChart, Line, ResponsiveContainer,
} from 'recharts';
import {
  getAccountsSummary, getAccountsComparison,
  getAccountsDailyGrowth, getAccountsLayerDistribution,
} from '../lib/api/dashboard';
import {
  downloadAccountsPsComparisonExcel, downloadAccountsPsComparisonPdf,
} from '../lib/api/reports';
import { formatNumber, todayISO, localISO } from '../lib/utils/format';
import { AccountsPsDetailPanel } from '../components/dashboard/AccountsPsDetailPanel';
import type {
  AccountsKpiSummary, AccountsPsComparison,
  AccountsDailyPoint, AccountsLayerDistribution,
} from '../types';

/** Account Details Dashboard — mirrors the shell + feel of the DSR
 *  Overview tab (KPI cards + charts + per-PS table) but populated
 *  from all_accounts. Colour cues match the entry-form type chips
 *  (green Victim / red Mule / slate Non-Mule) so operators can scan
 *  cross-view without re-learning. */

const cardStyle = {
  background: '#fff',
  border: '1px solid rgba(0,0,0,0.06)',
  boxShadow: '0 6px 16px rgba(0,0,0,0.08)',
};

// Reused across cards, bars, and pie slices so the same account-type
// always reads as the same colour. Victim / Mule / Non-Mule live
// together on the donut, stacked bars, KPI cards, and per-PS text
// rows — three clearly distinct hues at any size.
const COLOR_VICTIM   = '#EF4444';  // red-500 — bright red
const COLOR_MULE     = '#8b1919';  // dark red — offender
const COLOR_NONMULE  = '#1d4ed8';  // blue-700 — neutral / unknown
const COLOR_NAVY     = '#0b2c4a';
const COLOR_PURPLE   = '#6a1b9a';
const COLOR_ORANGE   = '#c67c1d';
const COLOR_TEAL     = '#00695c';

function KpiCard({
  label, value, sub, accent, Icon,
}: {
  label: string; value: string; sub?: string; accent: string;
  Icon?: typeof Users;
}) {
  // Fixed slots keep labels/numbers/subs aligned across every card in
  // the row even when label text length varies (e.g. "Total Accounts"
  // fits 1 line, "KA Mule Accounts" wraps to 2) and when some cards
  // have a `sub` line and others don't. Sub slot always renders (with
  // a non-breaking space when empty) so the card heights match.
  //
  // Numbers use `tabular-nums` so digit widths line up column-to-
  // column when the row is scanned diagonally.
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
        {sub || ' '}
      </p>
    </div>
  );
}

/** Simple card wrapper with a coloured title bar. */
function ChartCard({
  title, hint, accent, children,
}: {
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

/** Compute yesterday's date (relative to the "as of" picker), both
 *  the ISO string and a short human label like "22 Jul".
 *
 *  Uses `localISO` for the ISO output -- the old `.toISOString()`
 *  path was wrong: any local-midnight date in a +HH:MM zone (IST is
 *  UTC+5:30) serialises to the PREVIOUS UTC day, so "yesterday" came
 *  back as two days ago through the growth chart. */
function yesterdayOf(dateISO: string): { iso: string; label: string; header: string } {
  const [y, m, d] = dateISO.split('-').map(Number);
  const dt = new Date(y, (m || 1) - 1, d || 1);
  dt.setDate(dt.getDate() - 1);
  return {
    iso: localISO(dt),
    label: dt.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' }),
    header: dt.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: '2-digit' }),
  };
}

export function AccountsDashboardPage() {
  const [date, setDate] = useState(todayISO());
  const [summary, setSummary] = useState<AccountsKpiSummary | null>(null);
  const [rows, setRows] = useState<AccountsPsComparison[]>([]);
  const [dailyGrowth, setDailyGrowth] = useState<AccountsDailyPoint[]>([]);
  const [layerDist, setLayerDist] = useState<AccountsLayerDistribution | null>(null);
  const [loading, setLoading] = useState(true);
  const [drilldown, setDrilldown] = useState<AccountsPsComparison | null>(null);
  const [dl, setDl] = useState<'pdf' | 'xlsx' | null>(null);

  useEffect(() => {
    setLoading(true);
    // Growth chart ends at YESTERDAY (day-before-picker), not the
    // picker date itself — today's partial-day count would drag the
    // line down and read as a fake dip. All other panels stay on the
    // full "as of" date.
    const growthCutoff = yesterdayOf(date).iso;
    Promise.allSettled([
      getAccountsSummary(date),
      getAccountsComparison(date),
      getAccountsDailyGrowth(growthCutoff, 30),
      getAccountsLayerDistribution(date),
    ]).then(([s, u, g, l]) => {
      if (s.status === 'fulfilled') setSummary(s.value);
      else { setSummary(null); toast.error(`Summary: ${(s as any).reason?.message ?? 'failed'}`); }
      if (u.status === 'fulfilled') setRows(u.value);
      else { setRows([]); toast.error(`Per-PS: ${(u as any).reason?.message ?? 'failed'}`); }
      if (g.status === 'fulfilled') setDailyGrowth(g.value);
      else { setDailyGrowth([]); toast.error(`Growth: ${(g as any).reason?.message ?? 'failed'}`); }
      if (l.status === 'fulfilled') setLayerDist(l.value);
      else { setLayerDist(null); toast.error(`Layers: ${(l as any).reason?.message ?? 'failed'}`); }
    }).finally(() => setLoading(false));
  }, [date]);

  // Top 10 PSes by total — backend already sorts DESC. Bottom 10 =
  // the 10 lowest-count PSes (zeros bubble to the top of the bottom
  // list, which is exactly the "silent stations" signal we want).
  const top10Ps = useMemo(() => rows.slice(0, 10), [rows]);
  const bottom10Ps = useMemo(
    () => [...rows]
      .sort((a, b) => (a.total - b.total) || a.ps_name.localeCompare(b.ps_name))
      .slice(0, 10),
    [rows],
  );

  // Yesterday date derived from the "as of" picker — drives both the
  // Yesterday column header and the tooltip inside the table.
  const yday = useMemo(() => yesterdayOf(date), [date]);

  const handleDownload = async (kind: 'pdf' | 'xlsx') => {
    setDl(kind);
    try {
      if (kind === 'pdf') await downloadAccountsPsComparisonPdf(date);
      else await downloadAccountsPsComparisonExcel(date);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : `Failed to download ${kind.toUpperCase()}`);
    } finally {
      setDl(null);
    }
  };

  // Layer 1..15 zero-filled + merged into a single series so the
  // BarChart can render one grouped bar (KA next to Rest) per
  // layer. Fixed axis means every layer is present even when both
  // sides are zero -- which is the whole point of a money-trail
  // comparison chart.
  const layerSeries = useMemo(() => {
    const kaMap = new Map<number, number>((layerDist?.ka ?? []).map((b) => [b.layer, b.count]));
    const restMap = new Map<number, number>((layerDist?.rest ?? []).map((b) => [b.layer, b.count]));
    return Array.from({ length: 15 }, (_, i) => {
      const layer = i + 1;
      return {
        layer,
        ka: kaMap.get(layer) ?? 0,
        rest: restMap.get(layer) ?? 0,
      };
    });
  }, [layerDist]);
  const kaTotal = useMemo(() => layerSeries.reduce((s, p) => s + p.ka, 0), [layerSeries]);
  const restTotal = useMemo(() => layerSeries.reduce((s, p) => s + p.rest, 0), [layerSeries]);

  // Drill-down: full account detail grid for a single PS, with Excel + PDF export.
  // Clicking a row in the per-PS comparison table sets this; the Back button on
  // the detail panel clears it and we fall back to the summary view.
  if (drilldown) {
    return (
      <AccountsPsDetailPanel
        ps={drilldown}
        asOfDate={date}
        onBack={() => setDrilldown(null)}
      />
    );
  }

  return (
    <div>
      {/* Header + date picker */}
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div>
          <h1 className="text-[22px] font-bold mb-1 flex items-center gap-2" style={{ color: 'var(--ksp-navy)' }}>
            <BarChart3 className="w-5 h-5" /> Account Details Dashboard
          </h1>
          <p className="text-sm font-medium" style={{ color: 'var(--ksp-red)' }}>
            Cumulative account KPIs, top performers and bank concentration as of the selected date.
          </p>
        </div>
        <label className="text-sm flex items-center gap-2">
          <span className="font-semibold" style={{ color: 'var(--ksp-navy)' }}>As of:</span>
          <input type="date" value={date}
            onChange={(e) => setDate(e.target.value)}
            className="px-3 py-1.5 rounded-lg text-sm bg-white"
            style={{ border: '2px solid var(--ksp-navy)' }} />
        </label>
      </div>

      {loading ? (
        <div className="text-center py-16 font-semibold" style={{ color: 'var(--ksp-navy)' }}>Loading dashboard...</div>
      ) : (
        <div className="space-y-6">
          {/* Colourful KPI cards row — one accent per metric.
               Six cards since the 2026-07-27 reshape: dropped Unique
               Banks + Mule Herders, added Karnataka Mule Accounts
               (subset of Mule with branch_state='Karnataka'). */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
            <KpiCard label="Total Accounts"     value={formatNumber(summary?.total_accounts     ?? 0)} accent={COLOR_NAVY}    Icon={BarChart3} />
            <KpiCard label="Victim Accounts"    value={formatNumber(summary?.victim_accounts    ?? 0)} accent={COLOR_VICTIM}  Icon={Users} />
            <KpiCard label="Mule Accounts"      value={formatNumber(summary?.mule_accounts      ?? 0)} accent={COLOR_MULE}    Icon={ShieldAlert} />
            <KpiCard label="KA Mule Accounts"   value={formatNumber(summary?.karnataka_mule_accounts ?? 0)} accent={COLOR_ORANGE} Icon={MapPin} sub="branch in KA" />
            <KpiCard label="Non-Mule Accounts"  value={formatNumber(summary?.non_mule_accounts  ?? 0)} accent={COLOR_NONMULE} Icon={HelpCircle} />
            <KpiCard label="With ID Photo"      value={formatNumber(summary?.accounts_with_photo ?? 0)} accent={COLOR_TEAL}    Icon={Camera} />
          </div>

          {/* PS reporting coverage — one-line summary strip. */}
          <div className="rounded-2xl px-5 py-3 flex items-center justify-between flex-wrap gap-3"
               style={{ background: 'linear-gradient(90deg, rgba(11,44,74,0.06), rgba(255,212,0,0.10))',
                        border: '1px solid rgba(11,44,74,0.10)' }}>
            <div className="text-sm">
              <span className="font-bold" style={{ color: 'var(--ksp-navy)' }}>Reporting coverage:</span>{' '}
              <span className="font-mono">{summary?.units_submitted ?? 0}</span> / <span className="font-mono">{summary?.units_total ?? 0}</span> PS{(summary?.units_total ?? 0) === 1 ? '' : 'es'} have entered account data.
            </div>
            <div className="text-xs opacity-70">
              {rows.length > 0 && (
                <>Leading PS: <span className="font-semibold" style={{ color: 'var(--ksp-navy)' }}>{rows[0].ps_name}</span> ({formatNumber(rows[0].total)})</>
              )}
            </div>
          </div>

          {/* Row 1 — Daily growth (1/2) + Layer comparison (1/2).
               Layer comparison replaces the old Type Distribution
               donut on the 2026-07-29 reshape -- the V/M/NM split
               is already surfaced by the KPI cards above, whereas
               a KA-vs-Rest layer chart answers "how deep is the
               money trail on each side" at a glance. Rendered as
               one grouped bar chart (KA and Rest side by side per
               layer) so the two sides compare directly instead of
               requiring an eye jump between two cards. */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div>
              <ChartCard
                title="Daily Growth — Accounts"
                hint="New accounts created per day. Series runs from 20 Jul 2026 launch through yesterday (today's partial-day count is omitted so the trendline doesn't dip artificially). Zero days shown so the line stays continuous."
                accent={COLOR_NAVY}
              >
                {dailyGrowth.length === 0 ? (
                  <div className="py-10 text-center italic opacity-60 text-sm">No growth data yet.</div>
                ) : (
                  <div style={{ width: '100%', height: 320 }}>
                    <ResponsiveContainer>
                      <LineChart data={dailyGrowth}
                                margin={{ top: 8, right: 24, left: 24, bottom: 68 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                        <XAxis dataKey="day" tick={{ fontSize: 10 }}
                          /* Explicit ticks list guarantees every day in the
                             series renders — interval={0} alone still lets
                             Recharts drop overlapping labels. */
                          ticks={dailyGrowth.map((d) => d.day)}
                          interval={0}
                          angle={-45}
                          textAnchor="end"
                          height={60}
                          tickFormatter={(v: string) => v.slice(5)} /* MM-DD */
                          label={{
                            value: 'Date',
                            position: 'bottom',
                            offset: 10,
                            style: { fontSize: 12, fontWeight: 700, fill: COLOR_NAVY },
                          }} />
                        <YAxis allowDecimals={false} tick={{ fontSize: 11 }}
                          label={{
                            value: 'No. of Accounts',
                            angle: -90,
                            position: 'insideLeft',
                            offset: 10,
                            style: { fontSize: 12, fontWeight: 700, fill: COLOR_NAVY, textAnchor: 'middle' },
                          }} />
                        <Tooltip
                          formatter={(v) => [formatNumber(Number(v ?? 0)), 'New accounts']}
                          labelStyle={{ color: COLOR_NAVY, fontWeight: 700 }} />
                        <Line type="monotone" dataKey="count" name="New accounts"
                          stroke={COLOR_NAVY} strokeWidth={2}
                          dot={{ r: 2 }} activeDot={{ r: 5 }} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </ChartCard>
            </div>

            <ChartCard
              title={`Layers — KA vs Rest  (KA ${formatNumber(kaTotal)} · Rest ${formatNumber(restTotal)})`}
              hint={
                (() => {
                  const ka = layerDist?.unknown_layer_ka ?? 0;
                  const rest = layerDist?.unknown_layer_rest ?? 0;
                  const parts: string[] = [];
                  if (ka > 0) parts.push(`${formatNumber(ka)} KA`);
                  if (rest > 0) parts.push(`${formatNumber(rest)} Rest`);
                  return parts.length
                    ? `Money-trail depth 1..15. Unknown-layer accounts excluded: ${parts.join(' · ')}.`
                    : 'Money-trail depth 1..15. Rest bucket includes accounts with unknown branch_state.';
                })()
              }
              accent={COLOR_ORANGE}
            >
              {kaTotal === 0 && restTotal === 0 ? (
                <div className="py-10 text-center italic opacity-60 text-sm">No layered accounts yet.</div>
              ) : (
                <div style={{ width: '100%', height: 320 }}>
                  <ResponsiveContainer>
                    <BarChart data={layerSeries}
                              margin={{ top: 8, right: 8, bottom: 30, left: 8 }}
                              barCategoryGap="8%" barGap={3}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                      <XAxis dataKey="layer" tick={{ fontSize: 11 }}
                        label={{
                          value: 'Layer',
                          position: 'bottom',
                          offset: 6,
                          style: { fontSize: 12, fontWeight: 700, fill: COLOR_NAVY },
                        }} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                      <Tooltip
                        formatter={(v, key) => [formatNumber(Number(v ?? 0)), String(key)]}
                        labelFormatter={(v) => `Layer ${v}`}
                        labelStyle={{ color: COLOR_NAVY, fontWeight: 700 }} />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <Bar dataKey="ka"   name="Karnataka"     fill={COLOR_ORANGE} />
                      <Bar dataKey="rest" name="Rest of India" fill={COLOR_PURPLE} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </ChartCard>
          </div>

          {/* Row 2 — Top 10 PS (left) + Bottom 10 PS (right), both
               horizontal bars stacked by account type. Bottom-10
               surfaces the silent stations (all-zero rows bubble to
               the top of the bottom list) so operators can see at a
               glance who hasn't reported. */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ChartCard
              title={`Top ${Math.min(10, top10Ps.length)} Police Stations by Account Count`}
              hint="Highest account counts as of the selected date. Click a table row below to drill in."
              accent={COLOR_NAVY}
            >
              {top10Ps.length === 0 ? (
                <div className="py-10 text-center italic opacity-60 text-sm">No PS data yet.</div>
              ) : (
                <div style={{ width: '100%', height: 40 + top10Ps.length * 30 }}>
                  <ResponsiveContainer>
                    <BarChart data={top10Ps} layout="vertical"
                              margin={{ top: 6, right: 24, left: 6, bottom: 6 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#eee" horizontal={false} />
                      <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
                      <YAxis type="category" dataKey="ps_name" tick={{ fontSize: 10 }} width={130} />
                      <Tooltip formatter={(v, key) => [formatNumber(Number(v ?? 0)), String(key)]}
                        labelStyle={{ color: COLOR_NAVY, fontWeight: 700 }} />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <Bar dataKey="victims"   stackId="a" name="Victim"   fill={COLOR_VICTIM} />
                      <Bar dataKey="mules"     stackId="a" name="Mule"     fill={COLOR_MULE} />
                      <Bar dataKey="non_mules" stackId="a" name="Non-Mule" fill={COLOR_NONMULE} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </ChartCard>

            <ChartCard
              title={`Bottom ${Math.min(10, bottom10Ps.length)} Police Stations by Account Count`}
              hint="Lowest account counts, ascending. Zero-account PSes rise to the top — a fast read on who hasn't reported."
              accent={COLOR_PURPLE}
            >
              {bottom10Ps.length === 0 ? (
                <div className="py-10 text-center italic opacity-60 text-sm">No PS data yet.</div>
              ) : (
                <div style={{ width: '100%', height: 40 + bottom10Ps.length * 30 }}>
                  <ResponsiveContainer>
                    <BarChart data={bottom10Ps} layout="vertical"
                              margin={{ top: 6, right: 24, left: 6, bottom: 6 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#eee" horizontal={false} />
                      <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
                      <YAxis type="category" dataKey="ps_name" tick={{ fontSize: 10 }} width={130} />
                      <Tooltip formatter={(v, key) => [formatNumber(Number(v ?? 0)), String(key)]}
                        labelStyle={{ color: COLOR_NAVY, fontWeight: 700 }} />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <Bar dataKey="victims"   stackId="b" name="Victim"   fill={COLOR_VICTIM} />
                      <Bar dataKey="mules"     stackId="b" name="Mule"     fill={COLOR_MULE} />
                      <Bar dataKey="non_mules" stackId="b" name="Non-Mule" fill={COLOR_NONMULE} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </ChartCard>
          </div>

          {/* Download toolbar — sits above the Per-PS table, right-
               aligned. Excel = openpyxl, PDF = reportlab. Both share
               the /reports/accounts-ps-comparison endpoint aggregation
               so the file mirrors what's on screen. */}
          <div className="flex justify-end gap-2">
            <button type="button"
              onClick={() => handleDownload('xlsx')}
              disabled={dl !== null || loading || rows.length === 0}
              title="Download the Per-PS Comparison as an Excel (.xlsx) file"
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-bold transition disabled:opacity-50"
              style={{ background: '#0a5c2a', color: '#fff' }}>
              <FileSpreadsheet className="w-3.5 h-3.5" />
              {dl === 'xlsx' ? 'Generating…' : 'Excel'}
            </button>
            <button type="button"
              onClick={() => handleDownload('pdf')}
              disabled={dl !== null || loading || rows.length === 0}
              title="Download the Per-PS Comparison as a PDF file"
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-bold transition disabled:opacity-50"
              style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}>
              <FileDown className="w-3.5 h-3.5" />
              {dl === 'pdf' ? 'Generating…' : 'PDF'}
            </button>
          </div>

          {/* Per-PS comparison table — clickable rows open the detail grid. */}
          <div className="rounded-2xl overflow-hidden" style={cardStyle}>
            <div className="px-5 py-3 border-b" style={{ borderTop: `4px solid ${COLOR_NAVY}` }}>
              <h3 className="text-sm font-bold flex items-center gap-2" style={{ color: 'var(--ksp-navy)' }}>
                <Trophy className="w-4 h-4" style={{ color: COLOR_ORANGE }} /> Per-PS Account Comparison
              </h3>
              <p className="text-xs opacity-60">
                Descending by total account count. Click any Police Station to see the full
                account list with Excel / PDF download. "Yesterday" column = accounts created
                on {yday.header} (the day before the "as of" cut-off).
              </p>
            </div>
            <table className="w-full text-sm">
              <thead style={{ background: '#f5f5f7' }}>
                <tr>
                  <th className="px-3 py-2 text-left">#</th>
                  <th className="px-3 py-2 text-left">District</th>
                  <th className="px-3 py-2 text-left">Police Station</th>
                  <th className="px-3 py-2 text-right">Total</th>
                  <th className="px-3 py-2 text-right whitespace-nowrap"
                    title={`Accounts created on ${yday.header}`}>
                    {yday.label}
                  </th>
                  <th className="px-3 py-2 text-right">Victim</th>
                  <th className="px-3 py-2 text-right">Mule</th>
                  <th className="px-3 py-2 text-right">Non-Mule</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-3 py-8 text-center italic opacity-60">
                      No account records yet for this cut-off date.
                    </td>
                  </tr>
                )}
                {rows.map((r, i) => (
                  <tr key={`${r.unit_id}-${r.ps_id}`}
                      className="border-t border-slate-100 cursor-pointer hover:bg-slate-50"
                      onClick={() => setDrilldown(r)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setDrilldown(r); }}>
                    <td className="px-3 py-2 text-xs font-mono opacity-70">{i + 1}</td>
                    <td className="px-3 py-2">{r.unit_name}</td>
                    <td className="px-3 py-2 font-semibold" style={{ color: 'var(--ksp-navy)' }}>
                      {r.ps_name}
                    </td>
                    <td className="px-3 py-2 text-right font-mono font-bold">{formatNumber(r.total)}</td>
                    <td className="px-3 py-2 text-right font-mono">
                      <span style={{ color: r.yesterday_count > 0 ? COLOR_VICTIM : 'rgba(0,0,0,0.35)', fontWeight: r.yesterday_count > 0 ? 700 : 400 }}>
                        {r.yesterday_count > 0 ? formatNumber(r.yesterday_count) : '—'}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      <span style={{ color: COLOR_VICTIM }}>{formatNumber(r.victims)}</span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      <span style={{ color: COLOR_MULE }}>{formatNumber(r.mules)}</span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      <span style={{ color: COLOR_NONMULE }}>{formatNumber(r.non_mules)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
