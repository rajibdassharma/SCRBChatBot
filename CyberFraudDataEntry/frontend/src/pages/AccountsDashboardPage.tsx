import { useEffect, useMemo, useState } from 'react';
import {
  BarChart3, Users, ShieldAlert, HelpCircle, Landmark, UserPlus, Camera, Trophy,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  PieChart, Pie, Cell, ResponsiveContainer,
} from 'recharts';
import {
  getAccountsSummary, getAccountsComparison, getAccountsTopBanks,
} from '../lib/api/dashboard';
import { formatNumber, todayISO } from '../lib/utils/format';
import { AccountsPsDetailPanel } from '../components/dashboard/AccountsPsDetailPanel';
import type {
  AccountsKpiSummary, AccountsPsComparison, AccountsBankConcentration,
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
// always reads as the same colour.
const COLOR_VICTIM   = '#0a6b28';
const COLOR_MULE     = '#8b1919';
const COLOR_NONMULE  = '#5b6b7a';
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

export function AccountsDashboardPage() {
  const [date, setDate] = useState(todayISO());
  const [summary, setSummary] = useState<AccountsKpiSummary | null>(null);
  const [rows, setRows] = useState<AccountsPsComparison[]>([]);
  const [topBanks, setTopBanks] = useState<AccountsBankConcentration[]>([]);
  const [loading, setLoading] = useState(true);
  const [drilldown, setDrilldown] = useState<AccountsPsComparison | null>(null);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      getAccountsSummary(date),
      getAccountsComparison(date),
      getAccountsTopBanks(date, 10),
    ]).then(([s, u, b]) => {
      if (s.status === 'fulfilled') setSummary(s.value);
      else { setSummary(null); toast.error(`Summary: ${(s as any).reason?.message ?? 'failed'}`); }
      if (u.status === 'fulfilled') setRows(u.value);
      else { setRows([]); toast.error(`Per-PS: ${(u as any).reason?.message ?? 'failed'}`); }
      if (b.status === 'fulfilled') setTopBanks(b.value);
      else { setTopBanks([]); toast.error(`Top banks: ${(b as any).reason?.message ?? 'failed'}`); }
    }).finally(() => setLoading(false));
  }, [date]);

  // Top 10 PSes by total — sorted desc so the tallest bar is on top.
  const top10Ps = useMemo(() => rows.slice(0, 10), [rows]);

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

          {/* Row: Top 10 PS bar (wide) + Type Distribution pie (narrow) */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2">
              <ChartCard
                title={`Top ${Math.min(10, top10Ps.length)} Police Stations by Account Count`}
                hint="Click a row in the table below to drill into any PS."
                accent={COLOR_NAVY}
              >
                {top10Ps.length === 0 ? (
                  <div className="py-10 text-center italic opacity-60 text-sm">No PS data yet.</div>
                ) : (
                  <div style={{ width: '100%', height: 40 + top10Ps.length * 34 }}>
                    <ResponsiveContainer>
                      <BarChart data={top10Ps} layout="vertical"
                                margin={{ top: 6, right: 30, left: 10, bottom: 6 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#eee" horizontal={false} />
                        <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
                        <YAxis type="category" dataKey="ps_name" tick={{ fontSize: 11 }} width={140} />
                        <Tooltip formatter={(v: number, key: string) => [formatNumber(v), key]}
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

            <ChartCard title="Account Type Distribution"
              hint="Share of Victim / Mule / Non-Mule across all PSes in scope."
              accent={COLOR_ORANGE}
            >
              {typePie.length === 0 ? (
                <div className="py-10 text-center italic opacity-60 text-sm">No accounts yet.</div>
              ) : (
                <div style={{ width: '100%', height: 260 }}>
                  <ResponsiveContainer>
                    <PieChart>
                      <Pie data={typePie} dataKey="value" nameKey="name"
                        cx="50%" cy="50%" innerRadius={55} outerRadius={95}
                        paddingAngle={2}
                        label={(d: any) => `${d.name}: ${formatNumber(d.value)}`}
                        labelLine={false}
                      >
                        {typePie.map((d) => <Cell key={d.name} fill={d.fill} />)}
                      </Pie>
                      <Tooltip formatter={(v: number) => formatNumber(v)} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              )}
            </ChartCard>
          </div>

          {/* Top Banks — horizontal bar chart, stacked by type. */}
          <ChartCard title={`Top ${Math.min(10, topBanks.length)} Banks by Account Count`}
            hint="Banks that appear most often across the account records in scope. Stacked bars show the type mix."
            accent={COLOR_PURPLE}
          >
            {topBanks.length === 0 ? (
              <div className="py-10 text-center italic opacity-60 text-sm">No bank data yet.</div>
            ) : (
              <div style={{ width: '100%', height: 40 + topBanks.length * 34 }}>
                <ResponsiveContainer>
                  <BarChart data={topBanks} layout="vertical"
                            margin={{ top: 6, right: 30, left: 10, bottom: 6 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#eee" horizontal={false} />
                    <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
                    <YAxis type="category" dataKey="bank_name" tick={{ fontSize: 11 }} width={160} />
                    <Tooltip formatter={(v: number, key: string) => [formatNumber(v), key]}
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

          {/* Per-PS comparison table — clickable rows open the detail grid. */}
          <div className="rounded-2xl overflow-hidden" style={cardStyle}>
            <div className="px-5 py-3 border-b" style={{ borderTop: `4px solid ${COLOR_NAVY}` }}>
              <h3 className="text-sm font-bold flex items-center gap-2" style={{ color: 'var(--ksp-navy)' }}>
                <Trophy className="w-4 h-4" style={{ color: COLOR_ORANGE }} /> Per-PS Account Comparison
              </h3>
              <p className="text-xs opacity-60">
                Descending by total account count. Click any Police Station to see the full account list with Excel / PDF download.
              </p>
            </div>
            <table className="w-full text-sm">
              <thead style={{ background: '#f5f5f7' }}>
                <tr>
                  <th className="px-3 py-2 text-left">#</th>
                  <th className="px-3 py-2 text-left">District</th>
                  <th className="px-3 py-2 text-left">Police Station</th>
                  <th className="px-3 py-2 text-right">Total</th>
                  <th className="px-3 py-2 text-right">Victim</th>
                  <th className="px-3 py-2 text-right">Mule</th>
                  <th className="px-3 py-2 text-right">Non-Mule</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-3 py-8 text-center italic opacity-60">
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
