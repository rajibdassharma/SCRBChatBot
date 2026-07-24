import { useEffect, useMemo, useState } from 'react';
import {
  BarChart3, Users, ShieldAlert, HelpCircle, Landmark, UserPlus, Camera,
  Trophy, FileDown, FileSpreadsheet,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  LineChart, Line, PieChart, Pie, Cell, ResponsiveContainer,
} from 'recharts';
import {
  getAccountsSummary, getAccountsComparison, getAccountsTopBanks,
  getAccountsDailyGrowth,
} from '../lib/api/dashboard';
import {
  downloadAccountsPsComparisonExcel, downloadAccountsPsComparisonPdf,
} from '../lib/api/reports';
import { formatNumber, todayISO } from '../lib/utils/format';
import { AccountsPsDetailPanel } from '../components/dashboard/AccountsPsDetailPanel';
import type {
  AccountsKpiSummary, AccountsPsComparison, AccountsBankConcentration,
  AccountsDailyPoint,
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
  return (
    <div className="rounded-2xl p-4 relative overflow-hidden"
      style={{ ...cardStyle, borderLeft: `6px solid ${accent}` }}>
      {Icon && (
        <Icon className="absolute right-3 top-3 opacity-10 w-14 h-14"
          style={{ color: accent }} />
      )}
      <p className="text-[11px] uppercase tracking-wide font-bold mb-1"
        style={{ color: accent }}>{label}</p>
      <p className="text-2xl font-bold" style={{ color: 'var(--ksp-navy)' }}>{value}</p>
      {sub && <p className="text-xs mt-1 opacity-60">{sub}</p>}
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
 *  the ISO string and a short human label like "22 Jul". */
function yesterdayOf(dateISO: string): { iso: string; label: string; header: string } {
  // Parse as local — the picker gives us a bare YYYY-MM-DD.
  const [y, m, d] = dateISO.split('-').map(Number);
  const dt = new Date(y, (m || 1) - 1, d || 1);
  dt.setDate(dt.getDate() - 1);
  const iso = dt.toISOString().slice(0, 10);
  const label = dt.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
  const header = dt.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: '2-digit' });
  return { iso, label, header };
}

export function AccountsDashboardPage() {
  const [date, setDate] = useState(todayISO());
  const [summary, setSummary] = useState<AccountsKpiSummary | null>(null);
  const [rows, setRows] = useState<AccountsPsComparison[]>([]);
  const [topBanks, setTopBanks] = useState<AccountsBankConcentration[]>([]);
  const [dailyGrowth, setDailyGrowth] = useState<AccountsDailyPoint[]>([]);
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
      getAccountsTopBanks(date, 10),
      getAccountsDailyGrowth(growthCutoff, 30),
    ]).then(([s, u, b, g]) => {
      if (s.status === 'fulfilled') setSummary(s.value);
      else { setSummary(null); toast.error(`Summary: ${(s as any).reason?.message ?? 'failed'}`); }
      if (u.status === 'fulfilled') setRows(u.value);
      else { setRows([]); toast.error(`Per-PS: ${(u as any).reason?.message ?? 'failed'}`); }
      if (b.status === 'fulfilled') setTopBanks(b.value);
      else { setTopBanks([]); toast.error(`Top banks: ${(b as any).reason?.message ?? 'failed'}`); }
      if (g.status === 'fulfilled') setDailyGrowth(g.value);
      else { setDailyGrowth([]); toast.error(`Growth: ${(g as any).reason?.message ?? 'failed'}`); }
    }).finally(() => setLoading(false));
  }, [date]);

  // Top 10 PSes by total — sorted desc so the tallest bar is on top.
  const top10Ps = useMemo(() => rows.slice(0, 10), [rows]);

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

  // Pie of account types — pulled from summary counters.
  const typePie = useMemo(() => ([
    { name: 'Victim',   value: summary?.victim_accounts   ?? 0, fill: COLOR_VICTIM },
    { name: 'Mule',     value: summary?.mule_accounts     ?? 0, fill: COLOR_MULE },
    { name: 'Non-Mule', value: summary?.non_mule_accounts ?? 0, fill: COLOR_NONMULE },
  ].filter(d => d.value > 0)), [summary]);

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
          {/* Colourful KPI cards row — one accent per metric. */}
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-4">
            <KpiCard label="Total Accounts"     value={formatNumber(summary?.total_accounts     ?? 0)} accent={COLOR_NAVY}    Icon={BarChart3} />
            <KpiCard label="Victim Accounts"    value={formatNumber(summary?.victim_accounts    ?? 0)} accent={COLOR_VICTIM}  Icon={Users} />
            <KpiCard label="Mule Accounts"      value={formatNumber(summary?.mule_accounts      ?? 0)} accent={COLOR_MULE}    Icon={ShieldAlert} />
            <KpiCard label="Non-Mule Accounts"  value={formatNumber(summary?.non_mule_accounts  ?? 0)} accent={COLOR_NONMULE} Icon={HelpCircle} />
            <KpiCard label="Unique Banks"       value={formatNumber(summary?.unique_banks       ?? 0)} accent={COLOR_PURPLE}  Icon={Landmark} />
            <KpiCard label="Mule Herders"       value={formatNumber(summary?.unique_mule_herders ?? 0)} accent={COLOR_ORANGE}  Icon={UserPlus} sub="distinct names" />
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

          {/* Row 1 — Daily growth (2/3) + Type distribution pie (1/3).
               Growth replaces the old Top-10-PS position per the
               2026-07-24 dashboard reshape. */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2">
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

            <ChartCard title="Account Type Distribution"
              hint="Share of Victim / Mule / Non-Mule across all PSes in scope."
              accent={COLOR_ORANGE}
            >
              {typePie.length === 0 ? (
                <div className="py-10 text-center italic opacity-60 text-sm">No accounts yet.</div>
              ) : (
                <div style={{ width: '100%', height: 280 }}>
                  <ResponsiveContainer>
                    <PieChart margin={{ top: 8, right: 8, bottom: 24, left: 8 }}>
                      <Pie data={typePie} dataKey="value" nameKey="name"
                        cx="50%" cy="45%" innerRadius={48} outerRadius={80}
                        paddingAngle={2}
                        // % INSIDE the arc, absolute count in the legend
                        // below. Custom renderer so the % text fill is
                        // fixed navy regardless of slice colour
                        // (Recharts default inherits fill from the
                        // slice, which vanishes on pale slices).
                        label={(props: any) => {
                          const total = typePie.reduce((s, x) => s + x.value, 0);
                          if (!total || !props.value) return null;
                          const pct = (props.value / total) * 100;
                          if (pct < 5) return null;
                          const RADIAN = Math.PI / 180;
                          const r = props.innerRadius + (props.outerRadius - props.innerRadius) * 0.5;
                          const x = props.cx + r * Math.cos(-props.midAngle * RADIAN);
                          const y = props.cy + r * Math.sin(-props.midAngle * RADIAN);
                          return (
                            <text x={x} y={y} fill={COLOR_NAVY}
                              fontSize={12} fontWeight={700}
                              textAnchor="middle" dominantBaseline="central">
                              {pct.toFixed(0)}%
                            </text>
                          );
                        }}
                        labelLine={false}
                      >
                        {typePie.map((d) => <Cell key={d.name} fill={d.fill} />)}
                      </Pie>
                      <Tooltip formatter={(v) => formatNumber(Number(v ?? 0))} />
                      <Legend verticalAlign="bottom" height={24}
                        formatter={(name, entry: any) =>
                          `${name}: ${formatNumber(entry?.payload?.value ?? 0)}`}
                        wrapperStyle={{ fontSize: 11 }} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              )}
            </ChartCard>
          </div>

          {/* Row 2 — Top 10 Banks + Top 10 PS side by side (both
               horizontal bars, stacked by type). Halved from full-
               width so they sit alongside each other per the
               2026-07-24 reshape. */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ChartCard title={`Top ${Math.min(10, topBanks.length)} Banks by Account Count`}
              hint="Banks that appear most often across the account records in scope."
              accent={COLOR_PURPLE}
            >
              {topBanks.length === 0 ? (
                <div className="py-10 text-center italic opacity-60 text-sm">No bank data yet.</div>
              ) : (
                <div style={{ width: '100%', height: 40 + topBanks.length * 30 }}>
                  <ResponsiveContainer>
                    <BarChart data={topBanks} layout="vertical"
                              margin={{ top: 6, right: 24, left: 6, bottom: 6 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#eee" horizontal={false} />
                      <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
                      <YAxis type="category" dataKey="bank_name" tick={{ fontSize: 10 }} width={130} />
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

            <ChartCard
              title={`Top ${Math.min(10, top10Ps.length)} Police Stations by Account Count`}
              hint="Click a row in the table below to drill into any PS."
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
