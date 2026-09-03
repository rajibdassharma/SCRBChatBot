import {
  useEffect, useLayoutEffect, useMemo, useRef, useState,
  type ReactNode,
} from 'react';
import {
  BarChart3, Users, ShieldAlert, HelpCircle, MapPin, Camera,
  Trophy, FileDown, FileSpreadsheet, Search, Network, Waypoints, Repeat,
  // Aliased: an unqualified `Map` would shadow the global Map constructor.
  Map as MapIcon, Fingerprint, Banknote, FileWarning, ArrowLeft,
  LayoutDashboard, Bitcoin} from 'lucide-react';
import { toast } from 'sonner';
import * as XLSX from 'xlsx';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  LineChart, Line, ResponsiveContainer,
} from 'recharts';
import {
  getAccountsSummary, getAccountsComparison,
  getAccountsDailyGrowth, getAccountsLayerDistribution,
  getAccountsFirTrace, getRepeatAccounts, getAccountFirHistory,
  getAccountsByGeography,
} from '../lib/api/dashboard';
import { AccountsGeoMap } from '../components/dashboard/AccountsGeoMap';
import { DuplicateIdsTab } from '../components/dashboard/DuplicateIdsTab';
import { MoneyTrailTab } from '../components/dashboard/MoneyTrailTab';
import { Pager, paginate, PAGE_SIZE } from '../components/common/Pager';
import TabBar, { type TabDef } from '../components/common/TabBar';
import { CryptoTrailTab } from '../components/dashboard/CryptoTrailTab';
import { StatementCoverageTab } from '../components/dashboard/StatementCoverageTab';
import { MuleNetworkTab } from '../components/dashboard/MuleNetworkTab';
import CaveatNote from '../components/common/CaveatNote';
import { INDIA_LAYOUT, KARNATAKA_LAYOUT, KARNATAKA_REGION_ALIASES } from '../lib/utils/geo-tile-grid';
import {
  downloadAccountsPsComparisonExcel, downloadAccountsPsComparisonPdf,
} from '../lib/api/reports';
import { getAllPoliceStationsPublic } from '../lib/api/auth';
import { formatINR, formatNumber, todayISO, localISO } from '../lib/utils/format';
import { useAuthStore } from '../lib/stores/auth-store';
import { AccountsPsDetailPanel } from '../components/dashboard/AccountsPsDetailPanel';
import type {
  AccountsKpiSummary, AccountsPsComparison,
  AccountsDailyPoint, AccountsLayerDistribution,
  AccountsFirTrace, FirTraceAccount, FirTraceSource, FirTraceFlow,
  FirTraceUnlinked,
  RepeatAccount, AccountFirOccurrence,
  AccountsGeoRegion, AccountsGeoScope,
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
// Navy, matching the FIR dashboard's navy/red pair and the Non-Mule
// pill in the drill-down panel, which already used it. Was blue-700
// (#1d4ed8) — a third hue that appeared nowhere else in the app.
// Validated against Mule red: deuteranopia dE 11.1, all-pairs PASS.
const COLOR_NONMULE  = '#0b2c4a';  // navy — neutral / unknown
const COLOR_NAVY     = '#0b2c4a';
const CRYPTO_COLOR   = '#b45309';   // amber-700 -- crypto cash-out
const FLOW_COLOR     = '#0b2c4a';
const FLOW_CROSS_FIR = '#8b1919';
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

type TabId =
  | 'overview' | 'map'
  | 'deep' | 'graph' | 'repeat' | 'dupids'
  | 'money' | 'coverage' | 'network' | 'crypto';

/**
 * Tabs, in the order an investigation moves through them.
 *
 * The GROUPS are the point. "Statements" tells an officer that those
 * four tabs are derived from parsed bank-statement uploads — so they
 * are partial while parsing is behind, and blank on a fresh corpus,
 * which is not true of the others. That distinction was invisible when
 * all ten sat in one undifferentiated row.
 */
const TABS: TabDef<TabId>[] = [
  { group: 'Accounts',      id: 'overview', label: 'Overview',     icon: LayoutDashboard },
  { group: 'Accounts',      id: 'map',      label: 'Map View',     icon: MapIcon },

  { group: 'Investigation', id: 'deep',     label: 'Deep Analysis',      icon: Network },
  { group: 'Investigation', id: 'graph',    label: 'Graphical Analysis', icon: Waypoints },
  { group: 'Investigation', id: 'repeat',   label: 'Repeat Accounts',    icon: Repeat },
  { group: 'Investigation', id: 'dupids',   label: 'Duplicate IDs',      icon: Fingerprint },

  { group: 'Bank Statements Analysis', id: 'money',    label: 'Money Trail',    icon: Banknote },
  { group: 'Bank Statements Analysis', id: 'coverage', label: 'Coverage',       icon: FileWarning },
  { group: 'Bank Statements Analysis', id: 'network',  label: 'Mule Network',   icon: Waypoints },
  { group: 'Bank Statements Analysis', id: 'crypto',   label: 'Crypto Analysis', icon: Bitcoin },
];

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

  // Layer 1..15 merged into a single series so the BarChart can
  // render one grouped bar (KA next to Rest) per layer. Layers with
  // zero on BOTH sides are dropped -- otherwise they take up X-axis
  // slots that squeeze the real bars. This means the axis is a
  // discrete list of active layers, not a fixed 1..15 (a middle
  // gap, e.g. active 1/2/4/5, shows as 1 2 4 5 with no empty 3).
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
    }).filter((p) => p.ka + p.rest > 0);
  }, [layerDist]);
  const kaTotal = useMemo(() => layerSeries.reduce((s, p) => s + p.ka, 0), [layerSeries]);
  const restTotal = useMemo(() => layerSeries.reduce((s, p) => s + p.rest, 0), [layerSeries]);

  // Tab state — Overview always visible; Deep Analysis appears only
  // for super_admin (SCRB HQ investigation tool). Non-super_admins
  // don't even see the second tab, so switching state doesn't need
  // to be role-gated separately.
  const { user } = useAuthStore();
  const isSuperAdmin = user?.role === 'super_admin';
  const [tab, setTab] = useState<TabId>('overview');

  // Set when an account row in Money Trail is clicked. Carries the two
  // things a trace actually keys on -- FIR numbers repeat across
  // stations, so the id is not optional -- plus where to go back to.
  //
  // Held here rather than inside DeepAnalysisTab because that component
  // unmounts whenever another tab is shown: state living in it would be
  // discarded on the very navigation this feature performs.
  const [focus, setFocus] = useState<{
    firNo: string; psId: number; from: typeof tab;
  } | null>(null);

  const traceFir = (firNo: string, psId: number) => {
    setFocus({ firNo, psId, from: tab });
    setTab('deep');
  };

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
      {/* Header + date picker.
          The strapline that used to sit under the title ("Cumulative
          account KPIs, top performers and bank concentration as of the
          selected date") is gone: it described only the Overview tab,
          was wrong on the other nine, and cost a line of vertical space
          on every one of them. The tab group labels now say what each
          view is, which is where that information belongs. */}
      <div className="flex items-center justify-between mb-3 flex-wrap gap-3">
        <div>
          <h1 className="text-[19px] font-bold flex items-center gap-2" style={{ color: 'var(--ksp-navy)' }}>
            <BarChart3 className="w-5 h-5" /> Account Details Dashboard
          </h1>
        </div>
        <label className="text-sm flex items-center gap-2"
          // Date picker hidden on Deep Analysis tab -- that view is
          // FIR-scoped and doesn't use a cutoff date.
          style={{ visibility: tab === 'overview' || tab === 'map' ? 'visible' : 'hidden' }}
          aria-hidden={tab !== 'overview' && tab !== 'map'}
          // Date picker is meaningful on the cumulative Overview and Map
          // tabs (both are "as of" rollups); Deep / Graph / Repeat views
          // are FIR- or account-scoped and ignore date entirely.
        >
          <span className="font-semibold" style={{ color: 'var(--ksp-navy)' }}>As of:</span>
          <input type="date" value={date}
            onChange={(e) => setDate(e.target.value)}
            className="px-3 py-1.5 rounded-lg text-sm bg-white"
            style={{ border: '2px solid var(--ksp-navy)' }} />
        </label>
      </div>

      {/* Tab bar -- the analysis tabs are super_admin only. */}
      {isSuperAdmin && (
        <TabBar tabs={TABS} active={tab} onChange={setTab} />
      )}

      {(tab === 'deep' || tab === 'graph') && isSuperAdmin ? (
        <DeepAnalysisTab mode={tab === 'graph' ? 'graph' : 'table'}
          focus={focus}
          onBack={focus ? () => { const t = focus.from; setFocus(null); setTab(t); } : undefined} />
      ) : tab === 'map' && isSuperAdmin ? (
        <GeoMapTab date={date} />
      ) : tab === 'repeat' && isSuperAdmin ? (
        <RepeatAccountsTab />
      ) : tab === 'dupids' && isSuperAdmin ? (
        <DuplicateIdsTab />
      ) : tab === 'money' && isSuperAdmin ? (
        <MoneyTrailTab onTrace={traceFir} />
      ) : tab === 'coverage' && isSuperAdmin ? (
        <StatementCoverageTab />
      ) : tab === 'network' && isSuperAdmin ? (
        <MuleNetworkTab onTrace={traceFir} />
      ) : tab === 'crypto' && isSuperAdmin ? (
        <CryptoTrailTab onTrace={traceFir} />
      ) : loading ? (
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
                              margin={{ top: 32, right: 8, bottom: 8, left: 8 }}
                              barCategoryGap="4%" barGap={2}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                      {/* X-axis "Layer" label removed -- was overlapping
                          the legend at the bottom. Card title already
                          says "Layers"; ticks are the numbers. */}
                      <XAxis dataKey="layer" tick={{ fontSize: 11 }}
                        tickFormatter={(v) => `L${v}`} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                      <Tooltip
                        formatter={(v, key) => [formatNumber(Number(v ?? 0)), String(key)]}
                        labelFormatter={(v) => `Layer ${v}`}
                        labelStyle={{ color: COLOR_NAVY, fontWeight: 700 }} />
                      {/* Legend at top so it doesn't fight the X-axis
                          for bottom real estate. */}
                      <Legend verticalAlign="top" align="right" height={24}
                        wrapperStyle={{ fontSize: 11 }} />
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


// ── Deep Analysis Tab (super_admin only) ─────────────────────────
// Investigator flow: type an FIR No, hit Trace, get everything the
// DB knows about that FIR pulled from 5 source tables + summed by
// layer for the money-flow chart. Runs standalone -- no shared
// state with the Overview tab besides super_admin gating.

const SOURCE_LABELS: Record<FirTraceSource, string> = {
  all_accounts: 'All Accounts',
  lien_accounts: 'Lien',
  victim_accounts: 'Victim Account',
  accused_accounts: 'Accused Account',
  money_transfer: 'Mule Transfer',
  // Not one of this FIR's tables. An account reached from one of them.
  outside: 'Outside this FIR',
};

// Distinct colour per money-trail layer -- reused across the
// per-layer bar chart and the graphical node view so operators
// pattern-match "same colour = same layer" across both surfaces.
// Layer values in the DB range 1..15 (see all_accounts.layer). We
// keep a rolling palette so anything beyond 15 wraps -- 15 layers
// deep is already deeper than any real case.
const LAYER_PALETTE = [
  '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
  '#8c564b', '#e377c2', '#17becf', '#bcbd22', '#7f7f7f',
  '#aec7e8', '#ffbb78', '#98df8a', '#ff9896', '#c5b0d5',
];
const LAYER_UNKNOWN_COLOR = '#94a3b8';   // slate-400 -- for NULL-layer accounts
const NON_MULE_COLOR      = '#374151';   // slate-700 -- Non-Mule stays dark grey regardless of layer
const layerColor = (layer: number | null | undefined): string =>
  layer == null ? LAYER_UNKNOWN_COLOR : LAYER_PALETTE[(layer - 1 + LAYER_PALETTE.length) % LAYER_PALETTE.length];

/** Node colour for the Graphical Analysis view. Non-Mule accounts
 *  always render dark grey so they stay visually distinct from
 *  layer-coloured Mule / Victim accounts; everyone else follows
 *  the layer palette. */
const nodeColorFor = (a: { source: string; account_type: string | null; layer: number | null }): string =>
  a.source === 'all_accounts' && a.account_type === 'Non-Mule'
    ? NON_MULE_COLOR
    : layerColor(a.layer);

function DeepAnalysisTab({ mode, focus, onBack }: {
  mode: 'table' | 'graph';
  /** Set when the user arrived by clicking an account in Money Trail.
   *  Both fields are required by the trace: FIR numbers are only unique
   *  per station. */
  focus?: { firNo: string; psId: number } | null;
  /** Present only on an arrival-by-click, so the officer can get back
   *  to the row they came from. */
  onBack?: () => void;
}) {
  // Same component instance owns both the table and graph views so
  // switching tabs at the top preserves trace state -- no re-fetch.
  const [firInput, setFirInput] = useState('');
  const [firSubmitted, setFirSubmitted] = useState('');
  const [trace, setTrace] = useState<AccountsFirTrace | null>(null);
  const [loading, setLoading] = useState(false);

  // PS picker: FIR Nos are only unique per (unit_id, ps_id) so a
  // super_admin trace MUST specify which PS to look at -- '0001/2026'
  // can legitimately exist at multiple stations. Load the full list
  // once on mount; dropdown groups by district for readability.
  const [psList, setPsList] = useState<{id: number, district_name: string, station_name: string}[]>([]);
  const [selectedPsId, setSelectedPsId] = useState<number | ''>('');

  useEffect(() => {
    let alive = true;
    getAllPoliceStationsPublic()
      .then((rows) => {
        if (!alive) return;
        const sorted = [...rows].sort((a, b) =>
          a.district_name.localeCompare(b.district_name) ||
          a.station_name.localeCompare(b.station_name));
        setPsList(sorted);
      })
      .catch((e) => toast.error(e instanceof Error ? e.message : 'Failed to load PS list'));
    return () => { alive = false; };
  }, []);

  // Group PSes by district for the <optgroup> nesting so a 45-row
  // dropdown stays scannable.
  const psByDistrict = useMemo(() => {
    const map = new Map<string, {id: number, station_name: string}[]>();
    for (const p of psList) {
      const arr = map.get(p.district_name) ?? [];
      arr.push({ id: p.id, station_name: p.station_name });
      map.set(p.district_name, arr);
    }
    return Array.from(map.entries()).map(([district, stations]) => ({ district, stations }));
  }, [psList]);

  const handleTrace = async () => {
    const fir = firInput.trim();
    if (!fir) {
      toast.error('Enter an FIR No to trace.');
      return;
    }
    if (selectedPsId === '') {
      toast.error('Pick a Police Station -- FIR Nos are only unique per PS.');
      return;
    }
    setFirSubmitted(fir);
    setLoading(true);
    try {
      const t = await getAccountsFirTrace(fir, selectedPsId);
      setTrace(t);
    } catch (e) {
      setTrace(null);
      toast.error(e instanceof Error ? e.message : 'Trace failed');
    } finally {
      setLoading(false);
    }
  };

  // Arriving from a Money Trail click: fill both inputs and run the
  // trace immediately.
  //
  // Keyed on firNo + psId rather than on the object, because the parent
  // creates a fresh object on every click — depending on the object
  // itself would re-fire the trace on unrelated re-renders. Clicking
  // the SAME row twice deliberately does nothing: the result is already
  // on screen.
  const autoKey = focus ? `${focus.firNo}|${focus.psId}` : '';
  const [tracedKey, setTracedKey] = useState('');
  useEffect(() => {
    if (!focus || autoKey === tracedKey) return;
    setFirInput(focus.firNo);
    setSelectedPsId(focus.psId);
    setTracedKey(autoKey);
    setFirSubmitted(focus.firNo);
    setLoading(true);
    getAccountsFirTrace(focus.firNo, focus.psId)
      .then(setTrace)
      .catch((e) => {
        setTrace(null);
        toast.error(e instanceof Error ? e.message : 'Trace failed');
      })
      .finally(() => setLoading(false));
  }, [autoKey, tracedKey, focus]);

  // Account-state split: how many accounts of a given account_type
  // touching this FIR sit in Karnataka vs elsewhere. `all_accounts`
  // is the only source with `account_type`. NULL branch_state counts
  // as "not confirmed KA" -> Rest, matching the convention in the
  // AccountsLayerDistribution schema docs.
  const stateSplitFor = (accountType: 'Mule' | 'Non-Mule') => {
    if (!trace) return { total: 0, ka: 0, rest: 0 };
    const rows = trace.accounts.filter(
      (a) => a.source === 'all_accounts' && a.account_type === accountType,
    );
    const ka = rows.filter((a) => a.branch_state === 'Karnataka').length;
    return { total: rows.length, ka, rest: rows.length - ka };
  };
  const muleStateStats    = useMemo(() => stateSplitFor('Mule'),     [trace]);      // eslint-disable-line react-hooks/exhaustive-deps
  const nonMuleStateStats = useMemo(() => stateSplitFor('Non-Mule'), [trace]);      // eslint-disable-line react-hooks/exhaustive-deps

  // Group accounts by layer for the table. Unknown-layer rows come
  // last under a synthetic "—" bucket so they're visible but not
  // mixed into the numeric layers.
  const accountsByLayer = useMemo(() => {
    if (!trace) return [] as { layer: number | null; rows: FirTraceAccount[] }[];
    const buckets = new Map<number | null, FirTraceAccount[]>();
    for (const a of trace.accounts) {
      const k = a.layer ?? null;
      const arr = buckets.get(k) ?? [];
      arr.push(a);
      buckets.set(k, arr);
    }
    const knownLayers = Array.from(buckets.keys()).filter((k): k is number => k !== null).sort((a, b) => a - b);
    const out: { layer: number | null; rows: FirTraceAccount[] }[] = [];
    for (const l of knownLayers) out.push({ layer: l, rows: buckets.get(l)! });
    if (buckets.has(null)) out.push({ layer: null, rows: buckets.get(null)! });
    return out;
  }, [trace]);

  return (
    <div className="space-y-6">
      {/* FIR input bar -- PS dropdown + FIR text + Trace. Both are
           required because FIR Nos are only unique per (unit_id, ps_id). */}
      {/* Shown only when the officer arrived by clicking a row, so the
          way back is on screen at the moment it is wanted. Without it
          the return trip means re-picking the tab, then the filters,
          then the page — and the row they were reading is gone. */}
      {onBack && (
        <button type="button" onClick={onBack}
          className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-semibold"
          style={{ background: 'var(--ksp-navy)', color: '#fff' }}>
          <ArrowLeft className="w-4 h-4" /> Back to Money Trail
        </button>
      )}
      <div className="rounded-2xl p-4 flex flex-wrap items-center gap-3" style={cardStyle}>
        <label className="flex items-center gap-2 min-w-[260px]">
          <span className="text-xs font-semibold" style={{ color: 'var(--ksp-navy)' }}>PS:</span>
          <select
            value={selectedPsId === '' ? '' : String(selectedPsId)}
            onChange={(e) => setSelectedPsId(e.target.value === '' ? '' : Number(e.target.value))}
            className="flex-1 px-3 py-2 rounded-lg text-sm outline-none bg-white"
            style={{ border: '2px solid var(--ksp-navy)' }}>
            <option value="">— pick a Police Station —</option>
            {psByDistrict.map(({ district, stations }) => (
              <optgroup key={district} label={district}>
                {stations.map((s) => (
                  <option key={s.id} value={String(s.id)}>{s.station_name}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 flex-1 min-w-[240px]">
          <Search className="w-4 h-4" style={{ color: 'var(--ksp-navy)' }} />
          <input type="text"
            value={firInput}
            onChange={(e) => setFirInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') void handleTrace(); }}
            placeholder="Enter FIR No (e.g. 0042/2026) and press Enter"
            className="flex-1 px-3 py-2 rounded-lg text-sm outline-none"
            style={{ border: '2px solid var(--ksp-navy)', background: '#fff' }} />
        </label>
        <button type="button" onClick={handleTrace} disabled={loading}
          className="px-4 py-2 text-sm font-bold rounded-lg disabled:opacity-50"
          style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}>
          {loading ? 'Tracing…' : 'Trace FIR'}
        </button>
      </div>

      {/* Empty state before first trace */}
      {!trace && !loading && (
        <div className="rounded-2xl p-8 text-center italic opacity-70" style={cardStyle}>
          Pick a Police Station and enter an FIR No to see every account touching it — pulled from
          All Accounts, Lien, Victim Accounts, Accused Accounts, and Mule Transfers — grouped by
          money-trail layer. FIR Nos are only unique per PS, so both fields are required.
        </div>
      )}

      {trace && (
        <>
          {/* Case metadata header */}
          <div className="rounded-2xl p-5" style={cardStyle}>
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div>
                <h3 className="text-lg font-bold" style={{ color: 'var(--ksp-navy)' }}>
                  FIR {trace.fir_no}
                </h3>
                {trace.case && (
                  <p className="text-xs opacity-70 mt-1">
                    {trace.case.crime_type ?? '—'} · {trace.case.case_type ?? '—'} ·
                    Registered {trace.case.registration_date ?? '—'} ·
                    {' '}{trace.case.ps_name ?? '—'} ({trace.case.unit_name ?? '—'})
                  </p>
                )}
              </div>
              {trace.case && (
                <div className="text-right">
                  <p className="text-[11px] uppercase tracking-wide font-bold" style={{ color: COLOR_VICTIM }}>Victim</p>
                  <p className="text-sm font-bold" style={{ color: 'var(--ksp-navy)' }}>{trace.case.victim_name ?? '—'}</p>
                  <p className="text-[11px] uppercase tracking-wide font-bold mt-1" style={{ color: COLOR_MULE }}>Amount Lost</p>
                  <p className="text-sm font-mono font-bold" style={{ color: 'var(--ksp-navy)' }}>
                    ₹ {formatNumber(Math.round(trace.case.amount_lost))}
                  </p>
                </div>
              )}
            </div>
          </div>

          {mode === 'graph' && (
            <div className="space-y-4">
              <GraphicalAnalysisView trace={trace} />
              {/* Directly under the diagram, because it exists to answer
                  the question the diagram provokes: money clearly left
                  these accounts, so why are there no arrows. */}
              <UnlinkedOutflows rows={trace.unlinked ?? []} />
            </div>
          )}

          {mode === 'table' && (<>
          {/* KA vs Rest split panels -- one for Mule accounts, one
               for Non-Mule. Side-by-side on lg+ screens, stacked
               below. Both pulled from the All Accounts register
               filtered by account_type. Unknown branch_state counts
               as Out-of-State. */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <StateSplitCard
              title={`Mule Accounts by State — FIR ${firSubmitted}`}
              typeLabel="mule"
              totalAccent={COLOR_NAVY}
              outOfStateAccent={COLOR_MULE}
              stats={muleStateStats}
            />
            <StateSplitCard
              title={`Non-Mule Accounts by State — FIR ${firSubmitted}`}
              typeLabel="non-mule"
              totalAccent={NON_MULE_COLOR}
              outOfStateAccent={NON_MULE_COLOR}
              stats={nonMuleStateStats}
            />
          </div>

          {/* Layered accounts table */}
          <div className="rounded-2xl overflow-hidden" style={cardStyle}>
            <div className="px-5 py-3" style={{ borderTop: '4px solid #0b2c4a' }}>
              <h3 className="text-sm font-bold" style={{ color: 'var(--ksp-navy)' }}>
                Accounts by Layer — {trace.accounts.length} rows across {accountsByLayer.length} bucket(s)
              </h3>
              <p className="text-xs opacity-60 mt-0.5">
                Type column shows the account tag (Mule / Non-Mule / Victim for register rows; Lien / Victim / Accused for case-child rows). Badge colour = layer.
              </p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead style={{ background: '#f5f5f7' }}>
                  <tr>
                    <th className="px-3 py-2 text-left">Layer</th>
                    <th className="px-3 py-2 text-left">Type</th>
                    <th className="px-3 py-2 text-left">Account No</th>
                    <th className="px-3 py-2 text-left">Holder</th>
                    <th className="px-3 py-2 text-left">Bank</th>
                    <th className="px-3 py-2 text-left">Branch / State</th>
                    <th className="px-3 py-2 text-left">IFSC</th>
                  </tr>
                </thead>
                <tbody>
                  {accountsByLayer.length === 0 && (
                    <tr>
                      <td colSpan={7} className="px-3 py-8 text-center italic opacity-60">
                        No accounts, liens, or transfers found for this FIR.
                      </td>
                    </tr>
                  )}
                  {accountsByLayer.map(({ layer, rows }) => rows.map((r, i) => (
                    <tr key={`${layer}-${r.source}-${i}`}
                        className="border-t border-slate-100">
                      <td className="px-3 py-2 font-bold"
                          style={{ color: 'var(--ksp-navy)', background: 'rgba(11,44,74,0.04)' }}>
                        {layer == null ? '—' : `L${layer}`}
                      </td>
                      <td className="px-3 py-2">
                        {/* Show account_type (Mule / Non-Mule / Victim) for
                             all_accounts rows; fall back to a role label
                             for the case-child sources. Badge colour =
                             layer colour, EXCEPT Non-Mule which always
                             renders dark grey (matches the graph). */}
                        <span className="inline-block px-2 py-0.5 rounded text-xs font-semibold text-white"
                              style={{ background: nodeColorFor(r) }}>
                          {r.source === 'all_accounts'
                            ? (r.account_type === 'Non-Mule' ? 'NM' : (r.account_type ?? 'Account'))
                            : r.source === 'lien_accounts' ? 'Lien'
                            : r.source === 'victim_accounts' ? 'Victim'
                            : r.source === 'accused_accounts' ? 'Accused'
                            : SOURCE_LABELS[r.source]}
                        </span>
                      </td>
                      <td className="px-3 py-2 font-mono text-xs">{r.account_no ?? '—'}</td>
                      <td className="px-3 py-2">{r.account_holder_name ?? '—'}</td>
                      <td className="px-3 py-2">{r.bank_name ?? '—'}</td>
                      <td className="px-3 py-2 text-xs">
                        {r.branch_name ?? '—'}{r.branch_state ? ` / ${r.branch_state}` : ''}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs">{r.ifsc_code ?? '—'}</td>
                    </tr>
                  )))}
                </tbody>
              </table>
            </div>
          </div>
          </>)}
        </>
      )}
    </div>
  );
}


// ── Graphical Analysis view (super_admin only) ───────────────────
// Neo4j-style columnar money-flow layout: victim on the left,
// then one column per money-trail layer. Each account = coloured
// circle; hover reveals the full account card (holder, bank,
// branch, amount). Connections between nodes are not drawn yet --
// the DB only carries source→dest pairs in `money_transfers`,
// which we'll wire up as edges in a follow-up once the layout is
// signed off.

function GraphicalAnalysisView({ trace }: { trace: AccountsFirTrace }) {
  /** Transfers between accounts ON THIS FIR, plus the victim's opening
   *  hop.
   *
   *  Deliberately NOT every link these accounts have. This screen is
   *  case investigation: the officer is asking what happened inside
   *  their own FIR, and an account filed under somebody else's case is
   *  a lead for the Mule Network tab rather than a node in this one.
   *  Widening it here turned a 16-account case into a 221-account
   *  starburst and answered a question nobody on this screen had asked.
   *
   *  The victim's opening hop IS included, because the victim is part
   *  of the case. It comes from the network payload rather than from
   *  `flows`, since no bank statement records it. */
  const allFlows = useMemo<FirTraceFlow[]>(() => {
    const seen = new Set<string>();
    const out: FirTraceFlow[] = [];
    for (const f of trace.flows ?? []) {
      seen.add(`${f.src_account_id}>${f.dst_account_id}`);
      out.push(f);
    }
    // Only the victim row adds anything beyond that.
    for (const r of (trace.network ?? []).filter((x) => x.layer === 0)) {
      for (const p of r.peers) {
        const outgoing = (p.direction || '').toLowerCase().startsWith('out');
        const src = outgoing ? r.account_id : p.account_id;
        const dst = outgoing ? p.account_id : r.account_id;
        const k = `${src}>${dst}`;
        if (seen.has(k)) continue;
        seen.add(k);
        out.push({
          src_account_id: src, dst_account_id: dst,
          txns: p.txns, amount: p.amount, cross_fir: p.cross_fir,
        });
      }
    }
    return out;
  }, [trace]);

  // Group accounts into layer columns. Unknown-layer accounts get
  // their own column at the far right so nothing is silently hidden.
  const columns = useMemo(() => {
    const buckets = new Map<number | null, FirTraceAccount[]>();
    for (const a of trace.accounts) {
      const k = a.layer ?? null;
      const arr = buckets.get(k) ?? [];
      arr.push(a);
      buckets.set(k, arr);
    }
    const numeric = Array.from(buckets.keys())
      .filter((k): k is number => k !== null)
      .sort((a, b) => a - b);
    const maxLayer = numeric.length ? numeric[numeric.length - 1] : 0;
    const cols: { key: string; label: string; layer: number | null; accounts: FirTraceAccount[] }[] = [];
    for (let l = 1; l <= maxLayer; l++) {
      cols.push({ key: `L${l}`, label: `Layer ${l}`, layer: l, accounts: buckets.get(l) ?? [] });
    }
    if (buckets.has(null)) {
      cols.push({ key: 'Lx', label: 'Unlayered', layer: null, accounts: buckets.get(null)! });
    }
    return cols;
  }, [trace]);

  const hasVictim = !!(trace.case && (trace.case.victim_name || trace.case.amount_lost));
  /** The layer-0 row the server places at the head of the trail. Its id
   *  is what the victim's dashed edges are measured against, so the
   *  node has to register under exactly this key. */
  const victimId = useMemo(
    () => (trace.network ?? []).find((r) => r.layer === 0)?.account_id ?? null,
    [trace]);

  // Hover-state tooltip. Rendered as a position:fixed floating card
  // that tracks the mouse -- fixed position escapes any overflow-x
  // ancestor (a plain absolute popup gets clipped when the graph
  // scrolls horizontally). Coordinates come from onMouseMove on
  // each node so the card follows the cursor rather than anchoring
  // on entry.
  const [hovered, setHovered] = useState<{ content: ReactNode; x: number; y: number } | null>(null);

  // ---- money-flow edges ------------------------------------------
  //
  // Measured from the DOM rather than modelled alongside it. The
  // columns are a flex layout whose node positions depend on how many
  // accounts each layer holds and how wide the viewport is; a parallel
  // coordinate model would have to reproduce all of that and would go
  // wrong the first time either changed.
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const nodeEls = useRef(new Map<string, HTMLDivElement>());
  const [edges, setEdges] = useState<{
    key: string; x1: number; y1: number; x2: number; y2: number;
    colour: string; label: string;
    /** Asserted by the case file rather than observed in a statement —
     *  only the victim's opening hop. Layer 1 is DEFINED as the account
     *  the victim paid, and no bank statement records that payment: a
     *  victim account never appears in the mule-to-mule link table.
     *  Drawn dashed and unlabelled, because every other arrow here is
     *  evidence and this screen ends up in case files. */
    asserted?: boolean;
  }[]>([]);
  const [canvas, setCanvas] = useState({ w: 0, h: 0 });

  // Crypto accounts get a terminal node of their own, so the cash-out
  // reads as the end of the flow instead of a badge bolted to a node.
  const cryptoAccounts = useMemo(
    () => trace.accounts.filter((a) => a.account_id && a.crypto_txns > 0),
    [trace]);

  const flows: FirTraceFlow[] = allFlows;

  useLayoutEffect(() => {
    const measure = () => {
      const cont = canvasRef.current;
      if (!cont) return;
      const cr = cont.getBoundingClientRect();
      const at = (k: string) => {
        const el = nodeEls.current.get(k);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return {
          cx: r.left - cr.left + r.width / 2,
          cy: r.top - cr.top + r.height / 2,
          rw: r.width / 2,
        };
      };
      const out: typeof edges = [];
      for (const f of flows) {
        const a = at(f.src_account_id); const b = at(f.dst_account_id);
        if (!a || !b) continue;
        const asserted = f.src_account_id === victimId;
        out.push({
          key: `f:${f.src_account_id}:${f.dst_account_id}`,
          x1: a.cx, y1: a.cy, x2: b.cx, y2: b.cy,
          colour: f.cross_fir ? FLOW_CROSS_FIR : FLOW_COLOR,
          label: asserted ? '' : `${formatNumber(f.txns)} txn`,
          asserted,
        });
      }
      for (const a of cryptoAccounts) {
        const p = at(a.account_id!); const q = at(`crypto:${a.account_id}`);
        if (!p || !q) continue;
        out.push({
          key: `c:${a.account_id}`,
          x1: p.cx, y1: p.cy, x2: q.cx, y2: q.cy,
          colour: CRYPTO_COLOR,
          label: `${formatNumber(a.crypto_txns)} txn`,
        });
      }
      setEdges(out);
      setCanvas({ w: cont.scrollWidth, h: cont.scrollHeight });
    };
    measure();
    const ro = new ResizeObserver(measure);
    if (canvasRef.current) ro.observe(canvasRef.current);
    window.addEventListener('resize', measure);
    return () => { ro.disconnect(); window.removeEventListener('resize', measure); };
  }, [trace, flows, cryptoAccounts]);

  const externalTotal = trace.accounts.reduce(
    (n, a) => n + (a.external_links || 0), 0);

  const layersPresent = columns.filter((c) => c.layer != null && c.accounts.length > 0)
                               .map((c) => c.layer as number);
  const hasUnlayered = columns.some((c) => c.layer == null && c.accounts.length > 0);
  const hasNonMule = trace.accounts.some(
    (a) => a.source === 'all_accounts' && a.account_type === 'Non-Mule',
  );

  return (
    <div className="space-y-4">
    <div className="rounded-2xl overflow-hidden" style={cardStyle}>
      <div className="px-5 py-3" style={{ borderTop: '4px solid #0b2c4a' }}>
        <h3 className="text-sm font-bold" style={{ color: 'var(--ksp-navy)' }}>
          Money Flow Graph — FIR {trace.fir_no}
        </h3>
        <p className="text-xs opacity-60 mt-0.5">
          Victim on the left, then one column per money-trail layer, then crypto cash-out.
          Hover any node for details. <b>Arrows are evidence, not layout</b> — one account's own
          bank statement names the other's account number.
          {flows.length > 40 && ` ${formatNumber(flows.length)} transfers — counts hidden to keep the shape readable.`}
        </p>
        {/* Say when there is nothing to draw, and why. A graph with no
            arrows otherwise reads as "no transfers happened", when it
            almost always means the statements are not on file. Only
            177 of 3,822 FIRs have a link between two of their OWN
            accounts. */}
        {flows.length === 0 && (
          <p className="text-xs mt-1" style={{ color: COLOR_MULE }}>
            No statement-derived transfer between two accounts of this FIR.
            {externalTotal > 0
              ? ` ${externalTotal} link(s) lead to mule accounts outside it — those accounts are ringed.`
              : ' Either the statements are not parsed yet, or the counterparties are not on file.'}
          </p>
        )}
      </div>

      <div className="px-5 pb-5">
        <div className="overflow-x-auto">
          <div ref={canvasRef} className="relative flex gap-6 items-start min-w-fit pt-3 pb-2">
            {/* Edge layer, behind the nodes. pointer-events none so it
                never steals a hover from the node it points at. */}
            {edges.length > 0 && (
              <svg width={canvas.w} height={canvas.h}
                className="absolute left-0 top-0"
                style={{ pointerEvents: 'none', zIndex: 0 }}>
                <defs>
                  <marker id="fir-arrow" viewBox="0 0 10 10" refX="9" refY="5"
                    markerWidth="5" markerHeight="5" orient="auto-start-reverse">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" />
                  </marker>
                </defs>
                {edges.map((e) => {
                  // Labels only while they can still be read. FIR
                  // 0007/2026 at PS 37 carries 364 internal edges -- a
                  // real mule farm, and every label on it would overlap
                  // its neighbours into a grey smear that hides the
                  // structure the arrows exist to show.
                  const showLabel = edges.length <= 40;
                  const dx = e.x2 - e.x1, dy = e.y2 - e.y1;
                  const len = Math.sqrt(dx * dx + dy * dy) || 1;
                  const gap = 25;
                  return (
                    <g key={e.key} style={{ color: e.colour }}>
                      <line
                        x1={e.x1 + (dx / len) * gap} y1={e.y1 + (dy / len) * gap}
                        x2={e.x2 - (dx / len) * gap} y2={e.y2 - (dy / len) * gap}
                        stroke={e.colour}
                        strokeWidth={e.asserted ? 1.4 : 1.8}
                        strokeOpacity={e.asserted ? 0.45 : 0.75}
                        strokeDasharray={e.asserted ? '6 5' : undefined}
                        markerEnd="url(#fir-arrow)" />
                      {showLabel && (
                        <text x={(e.x1 + e.x2) / 2} y={(e.y1 + e.y2) / 2 - 4}
                          textAnchor="middle"
                          style={{ fontSize: 9, fill: e.colour, fontWeight: 700 }}>
                          {e.label}
                        </text>
                      )}
                    </g>
                  );
                })}
              </svg>
            )}
            {/* Victim column -- rendered even when there's no case row so the layout is anchored. */}
            <div className="flex flex-col items-center gap-3 min-w-[100px]">
              <div className="text-[11px] font-bold uppercase tracking-wide"
                   style={{ color: COLOR_VICTIM }}>Victim</div>
              {hasVictim ? (
                <FlowNode
                  color={COLOR_VICTIM}
                  content={
                    <>
                      <div className="font-bold mb-1" style={{ color: 'var(--ksp-navy)' }}>
                        {trace.case?.victim_name ?? '—'}
                      </div>
                      <div><span className="opacity-60">Amount Lost:</span> ₹ {formatNumber(Math.round(trace.case?.amount_lost ?? 0))}</div>
                      <div><span className="opacity-60">FIR:</span> {trace.fir_no}</div>
                      <div><span className="opacity-60">PS:</span> {trace.case?.ps_name ?? '—'}</div>
                      <div><span className="opacity-60">Registered:</span> {trace.case?.registration_date ?? '—'}</div>
                    </>
                  }
                  nodeRef={(el) => {
                    if (!victimId) return;
                    if (el) nodeEls.current.set(victimId, el);
                    else nodeEls.current.delete(victimId);
                  }}
                  onHover={(c, x, y) => setHovered({ content: c, x, y })}
                  onLeave={() => setHovered(null)}
                />
              ) : (
                /* DRAWN EVEN WHEN THERE IS NOTHING TO DRAW.
                   A case with no victim recorded and a case that simply
                   has not been opened look identical if the node is
                   omitted. Hollow, labelled, and it still anchors the
                   dashed layer-1 edges so the shape of the trail is
                   unchanged -- an officer sees where the victim SHOULD
                   be and that the file does not say. */
                <>
                  <FlowNode
                    color={COLOR_VICTIM}
                    hollow
                    nodeRef={(el) => {
                      if (!victimId) return;
                      if (el) nodeEls.current.set(victimId, el);
                      else nodeEls.current.delete(victimId);
                    }}
                    content={
                      <>
                        <div className="font-bold mb-1" style={{ color: 'var(--ksp-navy)' }}>
                          Victim — data not available
                        </div>
                        <div className="opacity-70">
                          No victim details are recorded against this FIR.
                          The node is drawn so the gap is visible rather
                          than silent.
                        </div>
                      </>
                    }
                    onHover={(c, x, y) => setHovered({ content: c, x, y })}
                    onLeave={() => setHovered(null)}
                  />
                  <div className="text-[10px] italic opacity-50 text-center leading-tight"
                       style={{ maxWidth: 92 }}>
                    data not available
                  </div>
                </>
              )}
            </div>

            {/* Layer columns */}
            {columns.map((col) => (
              <div key={col.key} className="flex flex-col items-center gap-3 min-w-[100px]">
                <div className="text-[11px] font-bold uppercase tracking-wide flex items-center gap-1.5"
                     style={{ color: 'var(--ksp-navy)' }}>
                  <span className="inline-block w-2.5 h-2.5 rounded-full"
                        style={{ background: layerColor(col.layer) }} />
                  {col.label}
                  {col.accounts.length > 0 && (
                    <span className="opacity-60">({col.accounts.length})</span>
                  )}
                </div>
                {col.accounts.length === 0 ? (
                  <div className="text-xs italic opacity-40">empty</div>
                ) : col.accounts.map((a, i) => (
                  <FlowNode
                    key={`${col.key}-${i}`}
                    color={nodeColorFor(a)}
                    nodeRef={(el) => {
                      if (!a.account_id) return;
                      if (el) nodeEls.current.set(a.account_id, el);
                      else nodeEls.current.delete(a.account_id);
                    }}
                    // An account paying mules outside this FIR is a lead
                    // out of the case file. Ringed rather than drawn:
                    // drawing it would put a node on screen that this
                    // FIR does not cover.
                    ring={a.external_links > 0 ? COLOR_MULE : undefined}
                    badge={a.crypto_txns > 0 ? (
                      <span
                        className="absolute -top-1 -right-1 w-4 h-4 rounded-full flex items-center justify-center"
                        style={{ background: CRYPTO_COLOR, color: '#fff',
                                 fontSize: 9, fontWeight: 800 }}
                        title={`${a.crypto_txns} crypto transaction(s)`}>
                        ₿
                      </span>
                    ) : undefined}
                    content={
                      <>
                        <div className="font-bold mb-1" style={{ color: 'var(--ksp-navy)' }}>
                          {a.account_holder_name ?? '—'}
                        </div>
                        <div><span className="opacity-60">Source:</span> {SOURCE_LABELS[a.source]}{a.account_type ? ` · ${a.account_type}` : ''}</div>
                        <div><span className="opacity-60">Layer:</span> {a.layer == null ? '—' : `L${a.layer}`}</div>
                        <div><span className="opacity-60">Account:</span> {a.account_no ?? '—'}</div>
                        <div><span className="opacity-60">Bank:</span> {a.bank_name ?? '—'}</div>
                        <div><span className="opacity-60">Branch:</span> {a.branch_name ?? '—'}{a.branch_state ? ` / ${a.branch_state}` : ''}</div>
                        <div><span className="opacity-60">IFSC:</span> {a.ifsc_code ?? '—'}</div>
                        {a.amount > 0 && (
                          <div className="mt-1 font-bold" style={{ color: COLOR_MULE }}>
                            Amount: ₹ {formatNumber(Math.round(a.amount))}
                          </div>
                        )}
                        {a.crypto_txns > 0 && (
                          <div className="mt-1 font-bold" style={{ color: CRYPTO_COLOR }}>
                            Crypto: {formatNumber(a.crypto_txns)} txn ·{' '}
                            {a.crypto_exchanges.join(', ')}
                            {a.crypto_debit > 0
                              && ` · ₹ ${formatNumber(Math.round(a.crypto_debit))} out`}
                            <div className="font-normal opacity-70">
                              matched on the bank narration — a lead, not proof
                            </div>
                          </div>
                        )}
                        {a.external_links > 0 && (
                          <div className="mt-1" style={{ color: COLOR_MULE }}>
                            Pays {a.external_links} mule account(s) outside this FIR
                          </div>
                        )}
                      </>
                    }
                    onHover={(c, x, y) => setHovered({ content: c, x, y })}
                    onLeave={() => setHovered(null)}
                  />
                ))}
              </div>
            ))}

            {/* Crypto cash-out column. Placed after the deepest layer
                because that is what it is: the end of the trail, where
                money leaves the banking system. Rendered only when
                there is something in it — an always-present empty
                column would imply every FIR was checked and cleared,
                and only 128 of 3,822 have any crypto at all. */}
            {cryptoAccounts.length > 0 && (
              <div className="flex flex-col items-center gap-3 min-w-[110px]">
                <div className="text-[11px] font-bold uppercase tracking-wide flex items-center gap-1.5"
                     style={{ color: CRYPTO_COLOR }}>
                  <span className="inline-block w-2.5 h-2.5 rounded-full"
                        style={{ background: CRYPTO_COLOR }} />
                  Crypto
                  <span className="opacity-60">({cryptoAccounts.length})</span>
                </div>
                {cryptoAccounts.map((a) => (
                  <FlowNode
                    key={`crypto-${a.account_id}`}
                    color={CRYPTO_COLOR}
                    nodeRef={(el) => {
                      const k = `crypto:${a.account_id}`;
                      if (el) nodeEls.current.set(k, el);
                      else nodeEls.current.delete(k);
                    }}
                    content={
                      <>
                        <div className="font-bold mb-1" style={{ color: CRYPTO_COLOR }}>
                          {a.crypto_exchanges.join(', ') || 'Crypto'}
                        </div>
                        <div><span className="opacity-60">From:</span> {a.account_holder_name ?? '—'}</div>
                        <div><span className="opacity-60">Transactions:</span> {formatNumber(a.crypto_txns)}</div>
                        {a.crypto_debit > 0 && (
                          <div><span className="opacity-60">Money out:</span> ₹ {formatNumber(Math.round(a.crypto_debit))}</div>
                        )}
                        <div className="mt-1 opacity-70">
                          Flagged by matching the bank narration against
                          exchange and asset names. Verify the narration
                          before acting — money figures count only
                          chain-reconciled rows.
                        </div>
                      </>
                    }
                    onHover={(c, x, y) => setHovered({ content: c, x, y })}
                    onLeave={() => setHovered(null)}
                  />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Compact layer legend -- only layers actually present. */}
        <div className="flex flex-wrap gap-3 mt-4 pt-3 border-t text-xs items-center"
             style={{ borderColor: 'rgba(11,44,74,0.15)' }}>
          <span className="font-bold" style={{ color: 'var(--ksp-navy)' }}>Node colour:</span>
          <LegendChip color={COLOR_VICTIM} label="Victim" />
          {layersPresent.map((l) => (
            <LegendChip key={l} color={layerColor(l)} label={`Layer ${l}`} />
          ))}
          {hasUnlayered && (
            <LegendChip color={LAYER_UNKNOWN_COLOR} label="Unlayered" />
          )}
          {hasNonMule && (
            <LegendChip color={NON_MULE_COLOR} label="NM (Non-Mule)" />
          )}
          {cryptoAccounts.length > 0 && (
            <LegendChip color={CRYPTO_COLOR} label="Crypto cash-out" />
          )}
          {externalTotal > 0 && (
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-3 h-3 rounded-full"
                    style={{ background: '#fff', boxShadow: `0 0 0 2px ${COLOR_MULE}` }} />
              ringed = pays a mule outside this FIR
            </span>
          )}
          {flows.some((f) => f.cross_fir) && (
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-4 h-0.5"
                    style={{ background: FLOW_CROSS_FIR }} />
              arrow crossing two FIRs
            </span>
          )}
        </div>
      </div>

      {/* Cursor-following floating tooltip -- position:fixed escapes
           any overflow-x-auto ancestor. pointer-events:none so it
           doesn't intercept mouseleave on the underlying node. */}
      {hovered && <FloatingTooltip content={hovered.content} x={hovered.x} y={hovered.y} />}
    </div>
    </div>
  );
}

function FlowNode({ color, content, onHover, onLeave, nodeRef, badge, ring, hollow }: {
  color: string;
  content: ReactNode;
  onHover: (content: ReactNode, x: number, y: number) => void;
  onLeave: () => void;
  /** Registers the DOM node so edges can be measured against it. Edges
   *  are drawn from real laid-out positions rather than a parallel
   *  coordinate model, so they cannot drift out of step with the
   *  columns when the layout reflows. */
  nodeRef?: (el: HTMLDivElement | null) => void;
  /** Small corner marker — used for the crypto flag. */
  badge?: ReactNode;
  /** Outline colour, for accounts with links leading out of this FIR. */
  ring?: string;
  /** Drawn as an outline rather than a filled disc: this account is NOT
   *  recorded under this FIR — it was reached from one that is.
   *
   *  Hollow rather than a different colour, because colour on this
   *  canvas already means the money-trail layer and a second meaning on
   *  the same channel would destroy the first. An officer can then read
   *  two things at once: how deep the account sits, and whether anybody
   *  has filed it. */
  hollow?: boolean;
}) {
  // Small solid circle. onMouseEnter + onMouseMove both report the
  // current cursor position so the floating tooltip tracks the mouse
  // (not just anchors on entry). Focus events fall back to the node's
  // bounding rect for keyboard users.
  const report = (e: React.MouseEvent) => onHover(content, e.clientX, e.clientY);
  const reportFromFocus = (e: React.FocusEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    onHover(content, r.right, r.top);
  };
  return (
    <div className="relative" ref={nodeRef}>
      <div
        className={`w-11 h-11 rounded-full cursor-help transition-transform hover:scale-110${
          hollow ? '' : ' shadow-md ring-2'}`}
        style={{
          background: hollow ? '#fff' : color,
          ...(hollow ? { border: `2.5px dashed ${color}` } : {}),
          ...(ring ? { boxShadow: `0 0 0 3px ${ring}` } : {}),
        }}
        tabIndex={0}
        onMouseEnter={report}
        onMouseMove={report}
        onMouseLeave={onLeave}
        onFocus={reportFromFocus}
        onBlur={onLeave}
      />
      {badge}
    </div>
  );
}

/** Fixed-position hover card that follows the mouse cursor. Anchors
 *  bottom-right by default; flips to the LEFT of the cursor if the
 *  card would overflow the viewport's right edge, and clamps to the
 *  visible area vertically. pointer-events:none so the card can't
 *  swallow the mouseleave that would dismiss it. */
function FloatingTooltip({ content, x, y }: {
  content: ReactNode; x: number; y: number;
}) {
  const width = 260;
  const gap = 14;
  const viewportW = typeof window === 'undefined' ? 1200 : window.innerWidth;
  const viewportH = typeof window === 'undefined' ? 800 : window.innerHeight;
  const flipLeft = x + gap + width > viewportW;
  const left = flipLeft ? Math.max(8, x - gap - width) : x + gap;
  // Rough tooltip height; keep it from clipping the bottom edge.
  const top = Math.min(y + gap, viewportH - 220);
  return (
    <div
      style={{
        position: 'fixed',
        left,
        top,
        width,
        zIndex: 100,
        pointerEvents: 'none',
        background: '#fff',
        border: '1px solid rgba(11,44,74,0.2)',
        borderRadius: 10,
        boxShadow: '0 10px 30px rgba(0,0,0,0.18)',
        padding: 12,
        fontSize: 12,
        color: '#0f172a',
        lineHeight: 1.35,
      }}
    >
      {content}
    </div>
  );
}

function LegendChip({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="inline-block w-3 h-3 rounded-full" style={{ background: color }} />
      {label}
    </span>
  );
}


/** Money that left the case and cannot be drawn.
 *
 *  A link needs the recipient's ACCOUNT NUMBER so it can be matched
 *  against the mule register. Whether the bank writes one down is
 *  entirely a matter of channel — measured across the corpus:
 *
 *      RTGS 99%    NEFT 83%    UPI 69%    IMPS 13%
 *
 *  IMPS is not a parser failure. Inbound narrations read
 *  "FT IMPS/IFI/<ref>/<NAME>/…" — a person and no account. Outbound
 *  read "MB IMPS/IFO/<ref>/<IFSC>/…" — a branch code shared by
 *  thousands of accounts. Matching on either would fabricate links.
 *
 *  So this money is listed rather than drawn. Without it the screen
 *  shows a parsed statement, hundreds of rows, no arrows and nothing
 *  explaining why — which reads as a broken diagram instead of as the
 *  limit of what the bank disclosed. */
function UnlinkedOutflows({ rows }: { rows: FirTraceUnlinked[] }) {
  if (!rows.length) return null;
  const total = rows.reduce((s, r) => s + r.amount, 0);
  const unverified = rows.reduce((s, r) => s + r.unverified_txns, 0);

  return (
    <div className="rounded-2xl overflow-hidden" style={cardStyle}>
      <div className="px-5 py-3" style={{ borderTop: '4px solid #b45309' }}>
        <h3 className="text-sm font-bold" style={{ color: 'var(--ksp-navy)' }}>
          Named recipients with no account number — {formatINR(total)}
        </h3>
        <div className="mt-1">
          <CaveatNote summary="Why these have no arrow on the diagram above">
            The bank named who received this money but did not record their
            account number, so it cannot be matched against the mule
            register and <b>cannot be drawn as a link</b>. This is the
            bank's narration format, not a gap in parsing: RTGS carries an
            account number 99% of the time and NEFT 83%, but IMPS only 13%
            — it identifies the other party by name inbound, and by IFSC
            (a branch, shared by thousands of accounts) outbound.
            <b> These are leads, not evidence</b>: a truncated name is not
            an identity, and the same person may appear more than once
            spelled differently.
          </CaveatNote>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr style={{ background: 'rgba(11,44,74,0.04)' }}>
              <th className="text-left px-4 py-2 font-bold">Recipient (as the bank wrote it)</th>
              <th className="text-left px-4 py-2 font-bold">Channel</th>
              <th className="text-right px-4 py-2 font-bold">Transfers</th>
              <th className="text-right px-4 py-2 font-bold">Amount</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.counterparty_name}-${r.channel}-${i}`}
                  style={{ borderTop: '1px solid rgba(11,44,74,0.08)' }}>
                <td className="px-4 py-2 font-semibold">{r.counterparty_name}</td>
                <td className="px-4 py-2 opacity-70">{r.channel ?? '—'}</td>
                <td className="px-4 py-2 text-right tabular-nums">{formatNumber(r.txns)}</td>
                <td className="px-4 py-2 text-right tabular-nums font-semibold">
                  {formatINR(r.amount)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {unverified > 0 && (
        <div className="px-5 py-2 text-xs" style={{ color: 'var(--ksp-red)' }}>
          {formatNumber(unverified)} further transfer{unverified === 1 ? '' : 's'} are
          excluded from these totals because the statement's running balance
          could not be verified. Untested money is never added to a figure
          presented as fact.
        </div>
      )}
    </div>
  );
}

/** KA-vs-Rest state-split panel shared by the Mule and Non-Mule
 *  breakdowns on the Deep Analysis tab. Three tiles: Total /
 *  Karnataka / Out of State. `typeLabel` goes into the label text
 *  and the empty-state copy so both variants read naturally. */
function StateSplitCard({ title, typeLabel, totalAccent, outOfStateAccent, stats }: {
  title: string;
  typeLabel: 'mule' | 'non-mule';
  totalAccent: string;
  outOfStateAccent: string;
  stats: { total: number; ka: number; rest: number };
}) {
  const totalLabel = typeLabel === 'mule' ? 'Total Mule Accounts' : 'Total Non-Mule Accounts';
  const emptyText = typeLabel === 'mule'
    ? 'No mule accounts recorded against this FIR at the selected PS.'
    : 'No non-mule accounts recorded against this FIR at the selected PS.';
  const pctSuffix = typeLabel === 'mule' ? 'of mule accounts' : 'of non-mule accounts';
  return (
    <div className="rounded-2xl overflow-hidden" style={cardStyle}>
      <div className="px-5 py-3" style={{ borderTop: '4px solid #0b2c4a' }}>
        <h3 className="text-sm font-bold" style={{ color: 'var(--ksp-navy)' }}>
          {title}
        </h3>
        <p className="text-xs opacity-60 mt-0.5">
          Counted from the All Accounts register where account_type = '{typeLabel === 'mule' ? 'Mule' : 'Non-Mule'}'. Unknown branch_state counts as Out-of-State.
        </p>
      </div>
      <div className="px-5 pb-5 pt-2">
        {stats.total === 0 ? (
          <div className="py-6 text-center italic opacity-60 text-sm">{emptyText}</div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="rounded-xl p-4 flex flex-col"
                 style={{ ...cardStyle, borderLeft: `6px solid ${totalAccent}` }}>
              <p className="text-[11px] uppercase tracking-wide font-bold"
                 style={{ color: totalAccent }}>{totalLabel}</p>
              <p className="text-3xl font-bold tabular-nums leading-none mt-1"
                 style={{ color: 'var(--ksp-navy)' }}>{formatNumber(stats.total)}</p>
            </div>
            <div className="rounded-xl p-4 flex flex-col"
                 style={{ ...cardStyle, borderLeft: `6px solid ${COLOR_TEAL}` }}>
              <p className="text-[11px] uppercase tracking-wide font-bold"
                 style={{ color: COLOR_TEAL }}>Karnataka</p>
              <p className="text-3xl font-bold tabular-nums leading-none mt-1"
                 style={{ color: 'var(--ksp-navy)' }}>{formatNumber(stats.ka)}</p>
              <p className="text-xs opacity-60 mt-1">
                {stats.total > 0 ? `${Math.round((stats.ka / stats.total) * 100)}% ${pctSuffix}` : ' '}
              </p>
            </div>
            <div className="rounded-xl p-4 flex flex-col"
                 style={{ ...cardStyle, borderLeft: `6px solid ${outOfStateAccent}` }}>
              <p className="text-[11px] uppercase tracking-wide font-bold"
                 style={{ color: outOfStateAccent }}>Out of State</p>
              <p className="text-3xl font-bold tabular-nums leading-none mt-1"
                 style={{ color: 'var(--ksp-navy)' }}>{formatNumber(stats.rest)}</p>
              <p className="text-xs opacity-60 mt-1">
                {stats.total > 0 ? `${Math.round((stats.rest / stats.total) * 100)}% ${pctSuffix}` : ' '}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


// ── Repeat Accounts tab (super_admin only) ───────────────────────
// Cross-PS view of accounts appearing in >= min_firs distinct FIRs.
// Mule and Non-Mule shown as two separate stacked tables so the
// operator can compare at a glance. Threshold defaults to 2 but is
// dial-able via a small stepper in the header. Not FIR-scoped;
// pulls the top N rows sorted by FIR count desc.

/** Map View tab — geographic concentration of accounts (2026-07-31).
 *
 *  Fetches once per (date, scope) with account_type='All' and shades
 *  from a client-side metric toggle, so switching Mule / Victim /
 *  Non-Mule is instant and every tooltip keeps the full breakdown.
 */
function GeoMapTab({ date }: { date: string }) {
  const [scope, setScope] = useState<AccountsGeoScope>('state');
  const [metric, setMetric] = useState<'total' | 'victims' | 'mules' | 'non_mules'>('mules');
  const [rows, setRows] = useState<AccountsGeoRegion[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    getAccountsByGeography(date, scope, 'All')
      .then((r) => { if (alive) { setRows(r); setLoading(false); } })
      .catch((e: unknown) => {
        if (!alive) return;
        setRows([]);
        setLoading(false);
        toast.error(e instanceof Error ? e.message : 'Failed to load map data');
      });
    return () => { alive = false; };
  }, [date, scope]);

  // scope='state' spans the country; the other two are Karnataka-only
  // and share the same 36-name police geography, so one layout serves
  // both.
  const layout = scope === 'state' ? INDIA_LAYOUT : KARNATAKA_LAYOUT;

  const ranked = useMemo(() => {
    const list = (rows ?? []).filter((r) => r.region.trim() !== '' && r[metric] > 0);
    return [...list].sort((a, b) => b[metric] - a[metric]);
  }, [rows, metric]);

  const grandTotal = useMemo(
    () => (rows ?? []).reduce((s, r) => s + r[metric], 0),
    [rows, metric],
  );

  /** Clicking Karnataka on the national map is almost always a request
   *  to see inside it, so drill straight through to the district view
   *  instead of just highlighting a tile. */
  const handleSelect = (regionName: string) => {
    if (scope === 'state' && regionName === 'Karnataka') {
      setScope('district');
      setSelected(null);
      toast.success('Showing Karnataka districts — switch scope to go back');
      return;
    }
    setSelected((prev) => (prev === regionName ? null : regionName));
  };

  const METRIC_LABEL: Record<typeof metric, string> = {
    mules: 'Mule accounts',
    victims: 'Victim accounts',
    non_mules: 'Non-Mule accounts',
    total: 'All accounts',
  };

  return (
    <div className="space-y-6">
      {/* Controls */}
      <div className="rounded-2xl p-4 flex flex-wrap items-center gap-4" style={cardStyle}>
        <div className="text-sm">
          <p className="font-bold" style={{ color: 'var(--ksp-navy)' }}>
            Geographic concentration — {METRIC_LABEL[metric]}
          </p>
          <p className="text-xs opacity-70 mt-0.5">
            Cumulative as of the selected date. Click a region to highlight it in
            the table below; click Karnataka on the national view to drill into districts.
          </p>
        </div>

        <label className="ml-auto text-sm flex items-center gap-2">
          <span className="font-semibold" style={{ color: 'var(--ksp-navy)' }}>Scope:</span>
          <select value={scope}
            onChange={(e) => { setScope(e.target.value as AccountsGeoScope); setSelected(null); }}
            className="px-3 py-1.5 rounded-lg text-sm bg-white"
            style={{ border: '2px solid var(--ksp-navy)' }}>
            <option value="state">Branch State (all India)</option>
            <option value="district">Branch District (Karnataka)</option>
            <option value="reporting">Reporting PS District</option>
          </select>
        </label>

        <label className="text-sm flex items-center gap-2">
          <span className="font-semibold" style={{ color: 'var(--ksp-navy)' }}>Show:</span>
          <select value={metric}
            onChange={(e) => setMetric(e.target.value as typeof metric)}
            className="px-3 py-1.5 rounded-lg text-sm bg-white"
            style={{ border: '2px solid var(--ksp-navy)' }}>
            <option value="mules">Mule accounts</option>
            <option value="victims">Victim accounts</option>
            <option value="non_mules">Non-Mule accounts</option>
            <option value="total">All accounts</option>
          </select>
        </label>
      </div>

      {/* Scope caveat — the three scopes answer genuinely different
          questions and conflating them would mislead. */}
      <div className="rounded-xl px-4 py-2.5 text-xs"
        style={{ background: 'rgba(11,44,74,0.04)', border: '1px solid rgba(11,44,74,0.12)',
          color: 'var(--ksp-navy)' }}>
        {scope === 'state' && (
          <>Plotted by <b>bank branch state</b> — where the account is held, not where the case is registered.</>
        )}
        {scope === 'district' && (
          <>Plotted by <b>bank branch district</b>. This column only accepts Karnataka
            districts, so accounts held outside the state never appear here — use the
            Branch State scope for the national picture.</>
        )}
        {scope === 'reporting' && (
          <>Plotted by the <b>district of the police station that recorded the account</b> —
            investigation workload, not where the money sits. This field is always
            populated, unlike the branch columns.</>
        )}
      </div>

      {loading ? (
        <div className="text-center py-16 font-semibold" style={{ color: 'var(--ksp-navy)' }}>
          Loading map...
        </div>
      ) : (
        <>
          <div className="rounded-2xl p-4" style={cardStyle}>
            <AccountsGeoMap
              layout={layout}
              // Only meaningful for the Karnataka layouts; the India
              // layout has no merged shapes, so an empty map is right.
              aliases={scope === 'state' ? undefined : KARNATAKA_REGION_ALIASES}
              data={rows ?? []}
              metric={metric}
              selected={selected}
              onSelect={handleSelect}
            />
          </div>

          {/* Ranked table — the map answers "where", this answers "how
              many", and it stays readable when several regions shade
              into the same bucket. */}
          <div className="rounded-2xl overflow-hidden" style={cardStyle}>
            <div className="px-4 py-3 flex items-center gap-2"
              style={{ background: 'var(--ksp-navy)' }}>
              <Trophy className="w-4 h-4" style={{ color: 'var(--ksp-yellow)' }} />
              <h3 className="text-sm font-bold" style={{ color: 'var(--ksp-yellow)' }}>
                Ranked by {METRIC_LABEL[metric]}
              </h3>
            </div>
            {ranked.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm opacity-70">
                No {METRIC_LABEL[metric].toLowerCase()} recorded with a location for this date.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr style={{ background: 'rgba(11,44,74,0.06)' }}>
                      <th className="px-4 py-2 text-left font-bold">#</th>
                      <th className="px-4 py-2 text-left font-bold">Region</th>
                      <th className="px-4 py-2 text-right font-bold">{METRIC_LABEL[metric]}</th>
                      <th className="px-4 py-2 text-right font-bold">Share</th>
                      <th className="px-4 py-2 text-right font-bold">All types</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ranked.map((r, i) => {
                      const isSel = selected === r.region;
                      return (
                        <tr key={r.region}
                          onClick={() => setSelected(isSel ? null : r.region)}
                          className="border-t cursor-pointer transition"
                          style={{
                            borderColor: 'rgba(11,44,74,0.08)',
                            background: isSel ? 'rgba(198,124,29,0.12)' : undefined,
                          }}>
                          <td className="px-4 py-2 opacity-60">{i + 1}</td>
                          <td className="px-4 py-2 font-semibold" style={{ color: 'var(--ksp-navy)' }}>
                            {r.region}
                          </td>
                          <td className="px-4 py-2 text-right font-bold">{formatNumber(r[metric])}</td>
                          <td className="px-4 py-2 text-right opacity-70">
                            {grandTotal > 0 ? `${Math.round((r[metric] / grandTotal) * 100)}%` : '—'}
                          </td>
                          <td className="px-4 py-2 text-right opacity-70">{formatNumber(r.total)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

/** Rows requested per account type.
 *
 *  Was 100, which at the default min_firs=2 returned 112 of 711 real
 *  repeat accounts and said nothing — 599 accounts registered against
 *  multiple FIRs were simply absent from a screen whose entire purpose
 *  is to list them.
 *
 *  RAISED 1,000 -> 5,000 on 2026-08-19. 1,000 did NOT cover the data:
 *  measured that day, 1,519 mule accounts appear in 2+ FIRs, so 519 of
 *  them -- exactly the accounts this screen exists to surface -- were
 *  behind the banner. The banner fired correctly; nobody read it.
 *
 *  5,000 is the endpoint's own ceiling (see repeat-accounts, le=5000),
 *  so this asks for everything the server will give. It is also in
 *  proportion with the neighbouring tabs, which already ship 20,000
 *  (Mule Network) and 30,000 (All Mule Accounts) rows -- this was the
 *  smallest dataset of the three and the only one being truncated.
 *
 *  A cap still earns its place: this endpoint has no server-side
 *  pagination, so the browser holds every row. Without a ceiling an
 *  unexpected result set stalls the tab with no warning. Server-side
 *  paging is the real answer and is planned; All Mule Accounts at
 *  19,903 rows is the better place to start it. */
const ROW_CAP = 5000;

function RepeatAccountsTab() {
  const [minFirs, setMinFirs] = useState(2);
  const [muleRows, setMuleRows] = useState<RepeatAccount[] | null>(null);
  const [nonMuleRows, setNonMuleRows] = useState<RepeatAccount[] | null>(null);
  const [loading, setLoading] = useState(true);
  // Drill-down modal: clicking a blue account_no hyperlink sets
  // this; the modal fetches /account-fir-history and renders the
  // per-FIR + per-layer breakdown.
  const [selectedAccount, setSelectedAccount] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    Promise.allSettled([
      getRepeatAccounts('Mule', minFirs, ROW_CAP),
      getRepeatAccounts('Non-Mule', minFirs, ROW_CAP),
    ]).then(([m, n]) => {
      if (!alive) return;
      if (m.status === 'fulfilled') setMuleRows(m.value);
      else { setMuleRows([]); toast.error(`Mule: ${(m as any).reason?.message ?? 'failed'}`); }
      if (n.status === 'fulfilled') setNonMuleRows(n.value);
      else { setNonMuleRows([]); toast.error(`Non-Mule: ${(n as any).reason?.message ?? 'failed'}`); }
      setLoading(false);
    });
    return () => { alive = false; };
  }, [minFirs]);

  // A full page means the cap was hit, so there are probably more rows
  // than are shown. The endpoint returns a bare list with no total, so
  // this is inferred rather than reported — imperfect, but far better
  // than a table that silently stops.
  const truncated = (muleRows?.length ?? 0) >= ROW_CAP
                 || (nonMuleRows?.length ?? 0) >= ROW_CAP;

  return (
    <div className="space-y-6">
      {truncated && (
        <div className="rounded-xl px-4 py-3 text-xs font-semibold"
          style={{ background: 'rgba(198,124,29,0.10)',
                   border: '1px solid rgba(198,124,29,0.35)', color: '#8b1919' }}>
          ⚠ Showing the first {ROW_CAP.toLocaleString('en-IN')} accounts per type —
          there are more. Raise the minimum-FIR threshold to narrow the list.
        </div>
      )}
      {/* Threshold picker */}
      <div className="rounded-2xl p-4 flex flex-wrap items-center gap-4" style={cardStyle}>
        <div className="text-sm">
          <p className="font-bold" style={{ color: 'var(--ksp-navy)' }}>
            Repeat Accounts — cross-PS aggregation
          </p>
          <p className="text-xs opacity-70 mt-0.5">
            Accounts registered against multiple FIRs anywhere in the state.
            Click an account number to see every FIR + the layer it appeared at.
          </p>
        </div>
        <label className="ml-auto text-sm flex items-center gap-2">
          <span className="font-semibold" style={{ color: 'var(--ksp-navy)' }}>Min FIRs:</span>
          <input type="number" min={2} max={50} value={minFirs}
            onChange={(e) => setMinFirs(Math.max(2, Math.min(50, Number(e.target.value) || 2)))}
            className="w-20 px-3 py-1.5 rounded-lg text-sm bg-white text-right"
            style={{ border: '2px solid var(--ksp-navy)' }} />
        </label>
      </div>

      {loading && (
        <div className="text-center py-10 italic opacity-60 text-sm">Loading repeat accounts…</div>
      )}

      {!loading && muleRows && (
        <RepeatAccountsTable
          title="Mule Accounts appearing in multiple FIRs"
          typeLabel="Mule"
          accent={COLOR_MULE}
          rows={muleRows}
          onAccountClick={setSelectedAccount}
        />
      )}
      {!loading && nonMuleRows && (
        <RepeatAccountsTable
          title="Non-Mule Accounts appearing in multiple FIRs"
          typeLabel="Non-Mule"
          accent={NON_MULE_COLOR}
          rows={nonMuleRows}
          onAccountClick={setSelectedAccount}
        />
      )}

      {selectedAccount && (
        <AccountHistoryModal
          accountNo={selectedAccount}
          onClose={() => setSelectedAccount(null)}
        />
      )}
    </div>
  );
}

function RepeatAccountsTable({ title, typeLabel, accent, rows, onAccountClick }: {
  title: string;
  typeLabel: string;
  accent: string;
  rows: RepeatAccount[];
  onAccountClick: (accountNo: string) => void;
}) {
  // Page state lives HERE, not in the parent, so the Mule and Non-Mule
  // tables page independently — 699 rows in one and 12 in the other,
  // and moving through one has no business resetting the other.
  const [page, setPage] = useState(0);
  // Reset to the first page when the underlying rows change, i.e. when
  // the Min-FIRs threshold moves. Page 12 of the old list is a blank
  // screen against the new one (docs/UX.md §3.1).
  useEffect(() => { setPage(0); }, [rows]);
  const pg = paginate(rows.length, page);
  const pageRows = pg.slice(rows);

  // Export columns in ONE place so Excel and PDF cannot disagree about
  // what the table contained. sample_firs / sample_ps_labels are joined
  // rather than dropped: they are the whole reason a row is here, and a
  // spreadsheet with "7 FIRs" but no FIR numbers is unusable.
  const EXPORT_COLS: { header: string; get: (r: RepeatAccount) => string | number }[] = [
    { header: 'Account No', get: (r) => r.account_no },
    { header: 'Holder', get: (r) => r.account_holder_name || '' },
    { header: 'Bank', get: (r) => r.bank_name || '' },
    { header: 'Branch State', get: (r) => r.branch_state || '' },
    { header: 'Type', get: (r) => r.account_type },
    { header: 'FIR Count', get: (r) => r.fir_count },
    { header: 'PS Count', get: (r) => r.ps_count },
    { header: 'FIRs', get: (r) => (r.sample_firs || []).join(', ') },
    { header: 'Police Stations', get: (r) => (r.sample_ps_labels || []).join(', ') },
  ];

  function exportMatrix() {
    return {
      header: EXPORT_COLS.map((c) => c.header),
      // EVERY row, not the page on screen — the same rule the other
      // tabs follow. An export that silently gave you 25 of 699 rows
      // would be worse than no export.
      body: rows.map((r) => EXPORT_COLS.map((c) => c.get(r))),
    };
  }

  const slug = `repeat-accounts_${typeLabel.toLowerCase().replace(/[^a-z]+/g, '-')}`
    + `_${new Date().toISOString().slice(0, 10)}`;

  function downloadExcel() {
    if (!rows.length) { toast.error('Nothing to export.'); return; }
    const { header, body } = exportMatrix();
    const ws = XLSX.utils.aoa_to_sheet([header, ...body]);
    ws['!cols'] = header.map((_, i) => {
      const longest = Math.max(
        String(header[i] ?? '').length,
        ...body.map((r) => String(r[i] ?? '').length),
      );
      return { wch: Math.min(50, Math.max(10, longest + 2)) };
    });
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, typeLabel.slice(0, 28));
    XLSX.writeFile(wb, `${slug}.xlsx`);
  }

  function downloadPdf() {
    if (!rows.length) { toast.error('Nothing to export.'); return; }
    const { header, body } = exportMatrix();
    // Landscape A3: the FIRs and Police Stations columns are long and
    // wrapping them onto A4 makes the table unreadable.
    const doc = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'a3' });
    doc.setFontSize(14);
    doc.text(title, 40, 40);
    doc.setFontSize(10);
    doc.text(
      `${rows.length.toLocaleString('en-IN')} account${rows.length === 1 ? '' : 's'}`
      + ` · ${typeLabel} · generated ${new Date().toLocaleDateString('en-IN')}`, 40, 58);
    // The caveat goes on the page, not just the screen — a printed
    // report is circulated long after anyone remembers how it was
    // filtered.
    doc.setFontSize(8);
    doc.text(
      'An account appears here when the SAME account number is recorded against more than one FIR, '
      + 'anywhere in the state. That is a data observation, not a finding: the same number can be '
      + 'legitimately recorded by two stations investigating one fraud chain.',
      40, 74);
    autoTable(doc, {
      startY: 90,
      head: [header],
      body: body.map((r) => r.map((v) => String(v))),
      styles: { fontSize: 7, cellPadding: 3, overflow: 'linebreak' },
      headStyles: { fillColor: [11, 44, 74], textColor: [255, 212, 0] },
    });
    doc.save(`${slug}.pdf`);
  }

  return (
    <div className="rounded-2xl overflow-hidden" style={cardStyle}>
      <div className="px-5 py-3 flex items-start justify-between gap-4 flex-wrap"
        style={{ borderTop: `4px solid ${accent}` }}>
        <div className="min-w-0">
          <h3 className="text-sm font-bold" style={{ color: 'var(--ksp-navy)' }}>{title}</h3>
          <p className="text-xs opacity-60 mt-0.5">
            {rows.length === 0
              ? 'no accounts'
              : `showing ${(pg.firstIdx + 1).toLocaleString('en-IN')}–`
                + `${pg.lastIdx.toLocaleString('en-IN')} of `
                + `${rows.length.toLocaleString('en-IN')} account`
                + `${rows.length === 1 ? '' : 's'}`}
            {' '}· sorted by FIR count. Click an account number to open the FIR + layer history.
          </p>
        </div>
        {/* ml-auto, not just justify-end: this is a flex ITEM whose box
            is content-sized, so justify-end alone would right-align the
            buttons inside a box that itself floats left of the edge. */}
        <div className="flex gap-2 ml-auto shrink-0">
          <button type="button" onClick={downloadExcel} disabled={rows.length === 0}
            title={`Download all ${rows.length} ${typeLabel} rows as Excel`}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-bold disabled:opacity-40"
            style={{ background: '#0a5c2a', color: '#fff' }}>
            <FileSpreadsheet className="w-3.5 h-3.5" /> Excel
          </button>
          <button type="button" onClick={downloadPdf} disabled={rows.length === 0}
            title={`Download all ${rows.length} ${typeLabel} rows as PDF`}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-bold disabled:opacity-40"
            style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}>
            <FileDown className="w-3.5 h-3.5" /> PDF
          </button>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm" style={{ tableLayout: 'fixed' }}>
          <colgroup>
            <col style={{ width: '22%' }} />
            <col style={{ width: '24%' }} />
            <col style={{ width: '22%' }} />
            <col style={{ width: '16%' }} />
            <col style={{ width: '8%' }} />
            <col style={{ width: '8%' }} />
          </colgroup>
          <thead style={{ background: '#f5f5f7' }}>
            <tr>
              <th className="px-3 py-2 text-left">Account No</th>
              <th className="px-3 py-2 text-left">Holder</th>
              <th className="px-3 py-2 text-left">Bank</th>
              <th className="px-3 py-2 text-left">State</th>
              <th className="px-3 py-2 text-right">FIRs</th>
              <th className="px-3 py-2 text-right">PSes</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center italic opacity-60">
                  No {typeLabel} accounts meet the threshold.
                </td>
              </tr>
            )}
            {pageRows.map((r) => (
              <tr key={r.account_no} className="border-t border-slate-100 hover:bg-slate-50">
                <td className="px-3 py-2 font-mono truncate" title={r.account_no}>
                  <button type="button" onClick={() => onAccountClick(r.account_no)}
                    className="text-left underline hover:no-underline"
                    style={{ color: '#1d4ed8' }}
                    title="Open FIR + layer history">
                    {r.account_no}
                  </button>
                </td>
                <td className="px-3 py-2 truncate" title={r.account_holder_name ?? ''}>{r.account_holder_name ?? '—'}</td>
                <td className="px-3 py-2 truncate" title={r.bank_name ?? ''}>{r.bank_name ?? '—'}</td>
                <td className="px-3 py-2 truncate text-xs" title={r.branch_state ?? ''}>{r.branch_state ?? '—'}</td>
                <td className="px-3 py-2 text-right font-mono tabular-nums font-bold"
                    style={{ color: 'var(--ksp-navy)' }}>{r.fir_count}</td>
                <td className="px-3 py-2 text-right font-mono tabular-nums">{r.ps_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pager total={rows.length} page={pg.safePage} pageCount={pg.pageCount}
        onPage={setPage} noun="accounts" size={PAGE_SIZE} />
    </div>
  );
}

/** Modal that fetches /account-fir-history for the clicked account
 *  and lists every FIR + the layer the account sat at in each. Same
 *  account often lands at different layers across FIRs -- that's
 *  the whole reason this drill-down exists. */
function AccountHistoryModal({ accountNo, onClose }: {
  accountNo: string; onClose: () => void;
}) {
  const [rows, setRows] = useState<AccountFirOccurrence[] | null>(null);
  const [busy, setBusy] = useState(true);

  useEffect(() => {
    let alive = true;
    setBusy(true);
    getAccountFirHistory(accountNo)
      .then((r) => { if (alive) setRows(r); })
      .catch((e) => {
        if (alive) setRows([]);
        toast.error(e instanceof Error ? e.message : 'Failed to load account history');
      })
      .finally(() => { if (alive) setBusy(false); });
    return () => { alive = false; };
  }, [accountNo]);

  // ESC key closes.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const first = rows && rows.length > 0 ? rows[0] : null;
  // Distinct layer count -- if the account appears at more than one
  // layer, that's a headline signal ("mule laundered at layers 2 and 4").
  const distinctLayers = rows
    ? Array.from(new Set(rows.map((r) => r.layer).filter((l): l is number => l != null))).sort((a, b) => a - b)
    : [];

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 50,
        background: 'rgba(0,0,0,0.45)',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
        padding: '48px 16px', overflowY: 'auto',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="rounded-2xl bg-white shadow-2xl w-full max-w-3xl"
        style={{ border: '1px solid rgba(11,44,74,0.15)' }}
      >
        {/* Header */}
        <div className="px-5 py-4 flex items-start justify-between gap-4"
             style={{ borderBottom: '1px solid rgba(11,44,74,0.1)' }}>
          <div>
            <h3 className="text-base font-bold" style={{ color: 'var(--ksp-navy)' }}>
              Account {accountNo}
            </h3>
            <p className="text-xs opacity-70 mt-0.5">
              {first?.account_holder_name ?? '—'} · {first?.bank_name ?? '—'}
              {first?.branch_state ? ` · ${first.branch_state}` : ''}
            </p>
            {distinctLayers.length > 1 && (
              <p className="text-xs mt-1 font-semibold" style={{ color: COLOR_MULE }}>
                Appears at {distinctLayers.length} different layers: {distinctLayers.map((l) => `L${l}`).join(', ')}
              </p>
            )}
          </div>
          <button type="button" onClick={onClose}
            className="text-xs font-bold px-3 py-1.5 rounded-lg hover:bg-slate-100"
            style={{ color: 'var(--ksp-navy)', border: '1px solid rgba(11,44,74,0.2)' }}>
            Close (Esc)
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4">
          {busy ? (
            <div className="py-8 text-center italic opacity-60 text-sm">Loading…</div>
          ) : rows && rows.length === 0 ? (
            <div className="py-8 text-center italic opacity-60 text-sm">
              No All Accounts rows found for this account number.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" style={{ tableLayout: 'fixed' }}>
                <colgroup>
                  <col style={{ width: '20%' }} />
                  <col style={{ width: '30%' }} />
                  <col style={{ width: '25%' }} />
                  <col style={{ width: '12%' }} />
                  <col style={{ width: '13%' }} />
                </colgroup>
                <thead style={{ background: '#f5f5f7' }}>
                  <tr>
                    <th className="px-3 py-2 text-left">FIR No</th>
                    <th className="px-3 py-2 text-left">Police Station</th>
                    <th className="px-3 py-2 text-left">District</th>
                    <th className="px-3 py-2 text-left">Layer</th>
                    <th className="px-3 py-2 text-left">Type</th>
                  </tr>
                </thead>
                <tbody>
                  {rows!.map((r, i) => (
                    <tr key={`${r.fir_no}-${r.ps_name}-${i}`}
                        className="border-t border-slate-100">
                      <td className="px-3 py-2 font-mono truncate" title={r.fir_no}>{r.fir_no}</td>
                      <td className="px-3 py-2 truncate" title={r.ps_name}>{r.ps_name}</td>
                      <td className="px-3 py-2 truncate text-xs" title={r.district}>{r.district}</td>
                      <td className="px-3 py-2">
                        <span className="inline-block px-2 py-0.5 rounded text-xs font-semibold text-white"
                              style={{ background: layerColor(r.layer) }}>
                          {r.layer == null ? '—' : `L${r.layer}`}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <span className="inline-block px-2 py-0.5 rounded text-xs font-semibold text-white"
                              style={{
                                background: r.account_type === 'Non-Mule' ? NON_MULE_COLOR : layerColor(r.layer),
                              }}>
                          {r.account_type === 'Non-Mule' ? 'NM' : r.account_type}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
