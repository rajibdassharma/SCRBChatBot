import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import {
  BarChart3, FileDown, FileSpreadsheet, FileText, Building2, MapPin, Clock, EyeOff,
  // Aliased: an unqualified `Map` would shadow the global Map
  // constructor used by the per-district rollup below.
  Map as MapIcon, ShieldAlert, Trophy,
} from 'lucide-react';
import { AccountsGeoMap } from '../components/dashboard/AccountsGeoMap';
import { KARNATAKA_LAYOUT, KARNATAKA_REGION_ALIASES } from '../lib/utils/geo-tile-grid';
import { getFirPsPerformance, getFirDailyGrowth, getFirCrimeTypes } from '../lib/api/dashboard';
import type { FirFinancialFilter } from '../lib/api/dashboard';
import {
  downloadFirPsPerformanceExcel, downloadFirPsPerformancePdf,
} from '../lib/api/reports';
import { todayISO, isoDaysAgo } from '../lib/utils/format';
import type { FirPsPerformanceRow, FirDailyPoint, FirCrimeTypeReport } from '../types';
import { FirCrimeTypeTab } from '../components/dashboard/FirCrimeTypeTab';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, Legend, PieChart, Pie, Cell,
} from 'recharts';

/** DSR → FIR Dashboard.
 *
 *  Single table for now (2026-07-22 spec): District, PS Name, Total
 *  FIRs registered in the selected date range. Purpose is to measure
 *  PS performance — hence the sort defaulting to fir_count DESC so
 *  the busiest PSes surface at the top.
 *
 *  Data sourced entirely from the `cases` table (Case Detail entry
 *  fields — no derived arrest/petition/lien metrics). Registration
 *  date drives the window, not created_at, so back-dated entries
 *  count on the day the FIR was actually registered.
 *
 *  Scoping (same VAPT 7.7/7.8 rule as every other admin dashboard):
 *   - admin       → one row for own (district, PS)
 *   - super_admin → all active (district, PS) pairs, zero counts
 *                    included so under-performers show up.
 */

// todayISO + isoDaysAgo imported from lib/utils/format -- the local
// copies used .toISOString() which drops back a day at IST midnight.
const isoNDaysAgo = isoDaysAgo;

function fmtInt(n: number): string { return n.toLocaleString('en-IN'); }

// "24 Jul" — short header label for the Yesterday column. Client-side
// so the label tracks the user's local date, matching the server's
// today-1 window (both machines are on the same IST tz in production).
function yesterdayShortLabel(): string {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
}

const cardStyle = {
  background: '#fff',
  border: '1px solid rgba(0,0,0,0.06)',
  boxShadow: '0 6px 16px rgba(0,0,0,0.08)',
};

/** KPI tile — same shape as the Account Details dashboard's so the two
 *  read as one product rather than two dashboards built months apart. */
function KpiCard({ label, value, sub, accent, Icon }: {
  label: string; value: string; sub?: string; accent: string; Icon: typeof BarChart3;
}) {
  return (
    <div className="rounded-2xl p-4" style={{ ...cardStyle, borderTop: `4px solid ${accent}` }}>
      <div className="flex items-center gap-2 mb-1">
        <Icon className="w-4 h-4" style={{ color: accent }} />
        <p className="text-[11px] uppercase tracking-wide font-bold" style={{ color: accent }}>
          {label}
        </p>
      </div>
      <p className="text-2xl font-bold" style={{ color: 'var(--ksp-navy)' }}>{value}</p>
      {sub && <p className="text-[11px] mt-0.5 opacity-60">{sub}</p>}
    </div>
  );
}

const C_NAVY = '#0b2c4a';
const C_GREEN = '#0a6b28';
const C_PURPLE = '#6a1b9a';
const C_ORANGE = '#c67c1d';
const C_RED = '#8b1919';

/** Categorical slice colours, fixed order. This is the documented
 *  default palette, NOT the app's accents: validated at light surface
 *  it passes lightness band, chroma floor, adjacent CVD (worst 9.1
 *  protan) and the normal-vision floor. The app's own accents fail —
 *  navy, purple and dark red sit outside the lightness band, and navy
 *  and teal fall under the chroma floor, i.e. they read as grey. */
const PIE_COLORS = [
  '#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7',
];

// Sort control — click a header once to sort by that column in its
// default direction, click again to reverse. Default direction:
// count DESC (bigger performers first), district/PS ASC (A→Z).
type SortKey = 'district' | 'ps_name' | 'fir_count' | 'yesterday_count';
type SortDir = 'asc' | 'desc';
const DEFAULT_DIR: Record<SortKey, SortDir> = {
  district: 'asc',
  ps_name: 'asc',
  fir_count: 'desc',
  yesterday_count: 'desc',
};

export function DsrFirDashboardPage() {
  const [from, setFrom] = useState(isoNDaysAgo(29));
  const [to, setTo] = useState(todayISO());
  const [rows, setRows] = useState<FirPsPerformanceRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [sortBy, setSortBy] = useState<SortKey>('fir_count');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [dl, setDl] = useState<'pdf' | 'xlsx' | null>(null);
  // Overview / Map View split, matching the Account Details dashboard.
  // Both tabs read the SAME fetched rows and the same date window, so
  // switching never re-requests and the two can never disagree.
  const [tab, setTab] = useState<'overview' | 'ranking' | 'map' | 'crime'>('overview');
  const [growth, setGrowth] = useState<FirDailyPoint[]>([]);
  const [crime, setCrime] = useState<FirCrimeTypeReport | null>(null);
  // Financial / Non-Financial / All. Applied server-side to the table,
  // and therefore to the KPI cards, Top/Bottom charts, map and exports,
  // which all derive from those rows. The growth endpoint returns both
  // splits regardless, so the line chart just chooses what to draw.
  const [financial, setFinancial] = useState<FirFinancialFilter>('all');

  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    // Two independent requests. allSettled rather than all: a failing
    // growth series must not blank the table that already loaded.
    Promise.allSettled([
      getFirPsPerformance(from, to, financial),
      getFirDailyGrowth(from, to),
      getFirCrimeTypes(from, to, financial),
    ])
      .then(([perf, series, crimes]) => {
        if (cancelled) return;
        if (perf.status === 'fulfilled') setRows(perf.value);
        else toast.error(perf.reason instanceof Error ? perf.reason.message : 'Dashboard load failed');
        if (series.status === 'fulfilled') setGrowth(series.value);
        else { setGrowth([]); toast.error('Growth series failed to load'); }
        if (crimes.status === 'fulfilled') setCrime(crimes.value);
        else { setCrime(null); toast.error('Crime-type analysis failed to load'); }
      })
      .finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
  }, [from, to, financial]);

  const onSort = (k: SortKey) => {
    if (sortBy === k) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortBy(k);
      setSortDir(DEFAULT_DIR[k]);
    }
  };

  // Sorted rows — the backend already returns fir_count DESC; we
  // re-sort locally so header clicks re-order without a round-trip.
  // Tiebreaker keeps stable ordering across renders.
  const sortedRows = useMemo(() => {
    const copy = [...rows];
    copy.sort((a, b) => {
      let cmp = 0;
      if (sortBy === 'district') cmp = a.district.localeCompare(b.district);
      else if (sortBy === 'ps_name') cmp = a.ps_name.localeCompare(b.ps_name);
      else if (sortBy === 'yesterday_count') cmp = a.yesterday_count - b.yesterday_count;
      else cmp = a.fir_count - b.fir_count;
      if (sortDir === 'desc') cmp = -cmp;
      // Stable tiebreak: district, then ps_name — so identical fir_counts
      // keep a deterministic A→Z order rather than jumping between renders.
      return cmp
        || a.district.localeCompare(b.district)
        || a.ps_name.localeCompare(b.ps_name);
    });
    return copy;
  }, [rows, sortBy, sortDir]);

  const grandTotal = useMemo(
    () => rows.reduce((s, r) => s + r.fir_count, 0),
    [rows]);
  const grandYesterday = useMemo(
    () => rows.reduce((s, r) => s + r.yesterday_count, 0),
    [rows]);
  const yestLabel = yesterdayShortLabel();

  /** Per-district rollup for the map. The endpoint returns one row per
   *  PS with its district attached, so this is a client-side sum — no
   *  extra request, and it can never disagree with the table below
   *  because both read the same array. */
  const byDistrict = useMemo(() => {
    const m = new Map<string, { region: string; firs: number; yesterday: number; stations: number }>();
    for (const r of rows) {
      const key = (r.district ?? '').trim();
      if (!key) continue;
      const cur = m.get(key) ?? { region: key, firs: 0, yesterday: 0, stations: 0 };
      cur.firs += r.fir_count;
      cur.yesterday += r.yesterday_count;
      cur.stations += 1;
      m.set(key, cur);
    }
    return [...m.values()];
  }, [rows]);

  /** Chart series for the growth line. `day` is trimmed to DD/MM so a
   *  90-day window's axis stays readable. */
  const growthSeries = useMemo(
    () => growth.map((p) => ({
      day: p.day,
      label: p.day.slice(8, 10) + '/' + p.day.slice(5, 7),
      count: p.count,
      financial: p.financial,
      non_financial: p.non_financial,
    })),
    [growth]);

  /** Top / Bottom 10 stations by FIR count.
   *
   *  Bottom 10 deliberately INCLUDES zero-count stations — they are the
   *  under-performers this dashboard exists to surface, and dropping
   *  them would make the chart flatter and less useful. When more than
   *  ten sit on zero the ten shown are an alphabetical slice of a
   *  larger set, so the caption states how many are actually at zero
   *  rather than implying these are the only ones. */
  const topBottom = useMemo(() => {
    const sorted = [...rows].sort(
      (a, b) => b.fir_count - a.fir_count
        || a.district.localeCompare(b.district)
        || a.ps_name.localeCompare(b.ps_name),
    );
    const shape = (r: FirPsPerformanceRow) => ({
      name: r.ps_name,
      district: r.district,
      count: r.fir_count,
      crimes: r.crime_types ?? [],
    });
    return {
      top: sorted.slice(0, 10).map(shape),
      // Reversed so the chart reads worst-first, matching how the eye
      // scans a "bottom N" list.
      bottom: sorted.slice(-10).reverse().map(shape),
      zeroCount: rows.filter((r) => r.fir_count === 0).length,
    };
  }, [rows]);

  /** Crime-type mix for the pie. Top 7 by volume plus an aggregated
   *  "Other" — 31 slices would be unreadable and the tail is
   *  individually negligible, but rolling it up keeps the percentages
   *  honest (they still sum to 100, rather than quietly dropping the
   *  remainder). Reuses the crime-type response the Crime-Type View
   *  already fetches, so the pie costs no extra request and can never
   *  disagree with that tab. */
  const crimeMix = useMemo(() => {
    const rows = (crime?.types ?? []).filter((t) => t.count > 0);
    const total = rows.reduce((a, t) => a + t.count, 0);
    if (total === 0) return { slices: [] as { name: string; value: number; pct: number }[], total: 0 };
    const sorted = [...rows].sort((a, b) => b.count - a.count);
    const top = sorted.slice(0, 7);
    const tail = sorted.slice(7);
    const pct = (n: number) => Math.round((n / total) * 1000) / 10;
    const slices = top.map((t) => ({ name: t.crime_type, value: t.count, pct: pct(t.count) }));
    if (tail.length) {
      const n = tail.reduce((a, t) => a + t.count, 0);
      slices.push({ name: `Other (${tail.length} types)`, value: n, pct: pct(n) });
    }
    return { slices, total };
  }, [crime]);

  /** Station activity in the window. "Silent" is the number worth
   *  watching — the endpoint deliberately returns zero-count PSes so
   *  stations that reported nothing stay visible instead of vanishing
   *  from the denominator. */
  const stationStats = useMemo(() => {
    const reporting = rows.filter((r) => r.fir_count > 0).length;
    return { reporting, silent: rows.length - reporting, total: rows.length };
  }, [rows]);

  const handleDownload = async (kind: 'pdf' | 'xlsx') => {
    setDl(kind);
    try {
      if (kind === 'pdf') await downloadFirPsPerformancePdf(from, to, financial);
      else await downloadFirPsPerformanceExcel(from, to, financial);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : `Failed to download ${kind.toUpperCase()}`);
    } finally {
      setDl(null);
    }
  };

  const arrow = (k: SortKey) =>
    sortBy === k ? <span className="ml-1 opacity-80">{sortDir === 'asc' ? '▲' : '▼'}</span> : null;

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-4 mb-4">
        <div>
          <h1 className="text-[22px] font-bold flex items-center gap-2"
            style={{ color: 'var(--ksp-navy)', letterSpacing: '-0.02em' }}>
            <BarChart3 className="w-6 h-6" /> FIR Dashboard
          </h1>
          <p className="text-sm font-medium" style={{ color: 'var(--ksp-red)' }}>
            PS performance — FIRs registered in the selected date range.
          </p>
        </div>
      </div>

      {/* Tab bar — same treatment as the Account Details dashboard so
           the two dashboards read as one product. No role gate here:
           the whole page is already admin-only. */}
      <div className="flex gap-1 mb-5 border-b" style={{ borderColor: 'rgba(11,44,74,0.15)' }}>
        <button type="button"
          onClick={() => setTab('overview')}
          className="px-4 py-2 text-sm font-bold rounded-t-lg transition flex items-center gap-1.5"
          style={{
            background: tab === 'overview' ? 'var(--ksp-navy)' : 'transparent',
            color: tab === 'overview' ? 'var(--ksp-yellow)' : 'var(--ksp-navy)',
            borderBottom: tab === 'overview' ? '3px solid var(--ksp-yellow)' : '3px solid transparent',
          }}>
          <BarChart3 className="w-4 h-4" /> Overview
        </button>
        <button type="button"
          onClick={() => setTab('ranking')}
          className="px-4 py-2 text-sm font-bold rounded-t-lg transition flex items-center gap-1.5"
          style={{
            background: tab === 'ranking' ? 'var(--ksp-navy)' : 'transparent',
            color: tab === 'ranking' ? 'var(--ksp-yellow)' : 'var(--ksp-navy)',
            borderBottom: tab === 'ranking' ? '3px solid var(--ksp-yellow)' : '3px solid transparent',
          }}>
          <Trophy className="w-4 h-4" /> PS Ranking View
        </button>
        <button type="button"
          onClick={() => setTab('map')}
          className="px-4 py-2 text-sm font-bold rounded-t-lg transition flex items-center gap-1.5"
          style={{
            background: tab === 'map' ? 'var(--ksp-navy)' : 'transparent',
            color: tab === 'map' ? 'var(--ksp-yellow)' : 'var(--ksp-navy)',
            borderBottom: tab === 'map' ? '3px solid var(--ksp-yellow)' : '3px solid transparent',
          }}>
          <MapIcon className="w-4 h-4" /> Map View
        </button>
        <button type="button"
          onClick={() => setTab('crime')}
          className="px-4 py-2 text-sm font-bold rounded-t-lg transition flex items-center gap-1.5"
          style={{
            background: tab === 'crime' ? 'var(--ksp-navy)' : 'transparent',
            color: tab === 'crime' ? 'var(--ksp-yellow)' : 'var(--ksp-navy)',
            borderBottom: tab === 'crime' ? '3px solid var(--ksp-yellow)' : '3px solid transparent',
          }}>
          <ShieldAlert className="w-4 h-4" /> Crime-Type View
        </button>
      </div>

      {/* Date window controls */}
      <div className="rounded-2xl p-4 mb-5 flex flex-wrap gap-3 items-end"
        style={cardStyle}>
        <div>
          <label className="block text-xs font-semibold mb-1"
            style={{ color: 'var(--ksp-navy)' }}>From</label>
          <input type="date" value={from} max={to}
            onChange={(e) => setFrom(e.target.value)}
            className="px-3 py-2 rounded-xl text-sm outline-none"
            style={{ border: '2px solid var(--ksp-navy)', background: '#fff' }} />
        </div>
        <div>
          <label className="block text-xs font-semibold mb-1"
            style={{ color: 'var(--ksp-navy)' }}>To</label>
          <input type="date" value={to} min={from} max={todayISO()}
            onChange={(e) => setTo(e.target.value)}
            className="px-3 py-2 rounded-xl text-sm outline-none"
            style={{ border: '2px solid var(--ksp-navy)', background: '#fff' }} />
        </div>
        <div>
          <label className="block text-xs font-semibold mb-1"
            style={{ color: 'var(--ksp-navy)' }}>Case type</label>
          <select value={financial}
            onChange={(e) => setFinancial(e.target.value as FirFinancialFilter)}
            className="px-3 py-2 rounded-xl text-sm outline-none bg-white"
            style={{ border: '2px solid var(--ksp-navy)' }}>
            <option value="all">All</option>
            <option value="yes">Financial</option>
            <option value="no">Non-Financial</option>
          </select>
        </div>

        <div className="flex gap-2 ml-auto flex-wrap">
          {[1, 7, 30, 90].map((n) => (
            <button key={n} type="button"
              onClick={() => { setFrom(isoNDaysAgo(n - 1)); setTo(todayISO()); }}
              className="px-3 py-2 text-xs font-semibold rounded-lg"
              style={{ background: 'rgba(11,44,74,0.06)', color: 'var(--ksp-navy)' }}>
              {n === 1 ? 'Today' : `Last ${n} days`}
            </button>
          ))}
        </div>
      </div>

      {/* KPI row — all five derived from the rows already fetched, so
           there is no second request and nothing here can drift out of
           step with the table below. */}
      {tab === 'overview' && (
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 mb-5">
        <KpiCard label="FIRs in window" value={fmtInt(grandTotal)}
          sub={`${from} → ${to}`} accent={C_NAVY} Icon={FileText} />
        <KpiCard label={`Yesterday (${yestLabel})`} value={fmtInt(grandYesterday)}
          sub="Independent of the window" accent={C_GREEN} Icon={Clock} />
        <KpiCard label="PS reporting" value={fmtInt(stationStats.reporting)}
          sub={`of ${fmtInt(stationStats.total)} stations`} accent={C_PURPLE} Icon={Building2} />
        <KpiCard label="Silent PS" value={fmtInt(stationStats.silent)}
          sub="No FIR in this window" accent={C_ORANGE} Icon={EyeOff} />
        <KpiCard label="Districts covered" value={fmtInt(byDistrict.filter((d) => d.firs > 0).length)}
          sub={`of ${fmtInt(byDistrict.length)} with stations`} accent={C_RED} Icon={MapPin} />
      </div>
      )}


      {/* District heat map — same renderer as the Account Details map.
           Plotted by the REPORTING district (the PS that registered the
           FIR), which is derived from ps_id and therefore never blank,
           unlike the branch_* columns on all_accounts. */}
      {tab === 'map' && (
      <div className="rounded-2xl p-4 mb-5" style={cardStyle}>
        <AccountsGeoMap
          layout={KARNATAKA_LAYOUT}
          aliases={KARNATAKA_REGION_ALIASES}
          data={byDistrict}
          metric="firs"
          noun="FIRs"
          detailRows={[
            { label: 'FIRs in window', key: 'firs' },
            { label: `Yesterday (${yestLabel})`, key: 'yesterday' },
            { label: 'Police stations', key: 'stations' },
          ]}
        />
      </div>
      )}

      {/* Growth line — per-day FIRs across the window. Same filters as
           the table, so summing this series reproduces the grand total. */}
      {tab === 'overview' && (
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-5">
      {/* Line gets two thirds — a time series needs horizontal room to
           be readable. A pie does not, so it takes the remaining third.
           flex-col + a flex-1 body: grid items stretch to the tallest
           card in the row (the donut's), and without this the chart
           sat pinned to the top with the leftover height dumped
           underneath it as blank space. */}
      <div className="lg:col-span-2 rounded-2xl p-4 flex flex-col" style={cardStyle}>
        <h3 className="text-sm font-bold mb-1" style={{ color: 'var(--ksp-navy)' }}>
          FIR registration growth
        </h3>
        <p className="text-xs opacity-60 mb-3">
          FIRs per day by registration date, {from} → {to}.
          {financial === 'all'
            ? ' Financial and Non-Financial shown separately.'
            : financial === 'yes' ? ' Financial cases only.' : ' Non-Financial cases only.'}
          {' '}Days with none are plotted as zero so a gap reads as inactivity rather than missing data.
        </p>
        <div className="flex-1 flex items-center min-h-0">
        {growthSeries.length === 0 ? (
          <p className="w-full py-10 text-center text-sm opacity-60">No FIRs registered in this window.</p>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={growthSeries} margin={{ top: 5, right: 16, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(11,44,74,0.10)" />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: C_NAVY }}
                interval="preserveStartEnd" minTickGap={24} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: C_NAVY }} />
              <Tooltip
                formatter={(v, key) => [fmtInt(Number(v ?? 0)), String(key)]}
                labelFormatter={(_l, p) => (p?.[0]?.payload?.day ?? '')} />
              {financial === 'all' ? (
                // Two lines rather than one merged total: the split is
                // the point of the All view, and a combined line would
                // hide which of the two is actually moving.
                <>
                  <Legend />
                  <Line type="monotone" dataKey="financial" stroke={C_NAVY} strokeWidth={2}
                    dot={{ r: 2 }} activeDot={{ r: 5 }} name="Financial" />
                  <Line type="monotone" dataKey="non_financial" stroke={C_ORANGE} strokeWidth={2}
                    dot={{ r: 2 }} activeDot={{ r: 5 }} name="Non-Financial" />
                </>
              ) : (
                <Line type="monotone"
                  dataKey={financial === 'yes' ? 'financial' : 'non_financial'}
                  stroke={financial === 'yes' ? C_NAVY : C_ORANGE} strokeWidth={2}
                  dot={{ r: 2 }} activeDot={{ r: 5 }}
                  name={financial === 'yes' ? 'Financial' : 'Non-Financial'} />
              )}
            </LineChart>
          </ResponsiveContainer>
        )}
        </div>
      </div>

      {/* Crime-type mix. Top 7 plus an aggregated "Other": a pie of 31
           slices is unreadable, and the tail is individually tiny.
           Slice colours are the documented categorical palette in its
           fixed order — the app's own accents FAIL the lightness-band
           and chroma checks (navy and teal read as grey), so they are
           not usable as a categorical set. The list beneath doubles as
           the legend and supplies the visible labels the palette's
           sub-3:1 contrast slots require. */}
      <div className="rounded-2xl p-4" style={cardStyle}>
        <h3 className="text-sm font-bold" style={{ color: 'var(--ksp-navy)' }}>
          Crime-type mix
        </h3>
        <p className="text-xs opacity-60 mt-0.5 mb-2">
          Share of FIRs by crime type in this range.
        </p>
        {crimeMix.slices.length === 0 ? (
          <p className="py-12 text-center text-sm opacity-60">No FIRs in this window.</p>
        ) : (
          <>
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie data={crimeMix.slices} dataKey="value" nameKey="name"
                  cx="50%" cy="50%" outerRadius={108} innerRadius={58}
                  isAnimationActive={false} stroke="#fff" strokeWidth={2}>
                  {crimeMix.slices.map((sl, i) => (
                    <Cell key={sl.name} fill={sl.name.startsWith('Other') ? '#9a9a94' : PIE_COLORS[i % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(v, n) => [`${fmtInt(Number(v ?? 0))} FIRs`, String(n)]} />
                {/* The hole is dead space otherwise — the grand total
                    is the one number every reader wants alongside a
                    share breakdown. */}
                <text x="50%" y="50%" dy={-2} textAnchor="middle"
                  fontSize={22} fontWeight={800} fill="var(--ksp-navy)">
                  {fmtInt(crimeMix.total)}
                </text>
                <text x="50%" y="50%" dy={16} textAnchor="middle"
                  fontSize={10} fontWeight={600} fill="rgba(11,44,74,0.6)">
                  FIRs
                </text>
              </PieChart>
            </ResponsiveContainer>
            <div className="space-y-1 mt-1">
              {crimeMix.slices.map((sl, i) => (
                <div key={sl.name} className="flex items-center gap-2 text-[11px]">
                  <span style={{
                    width: 10, height: 10, borderRadius: 2, flexShrink: 0,
                    background: sl.name.startsWith('Other') ? '#9a9a94' : PIE_COLORS[i % PIE_COLORS.length],
                  }} />
                  <span className="truncate flex-1" title={sl.name}
                    style={{ color: 'var(--ksp-navy)' }}>{sl.name}</span>
                  <b style={{ color: 'var(--ksp-navy)' }}>{sl.pct}%</b>
                  <span className="opacity-55 w-10 text-right">{fmtInt(sl.value)}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
      </div>
      )}

      {/* Top 10 / Bottom 10 stations */}
      {tab === 'overview' && (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-5">
        <div className="rounded-2xl p-4" style={cardStyle}>
          <h3 className="text-sm font-bold mb-1" style={{ color: C_GREEN }}>
            Top 10 Police Stations
          </h3>
          <p className="text-xs opacity-60 mb-3">Most FIRs registered in this window.</p>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={topBottom.top} layout="vertical"
              margin={{ top: 4, right: 24, left: 8, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(11,44,74,0.10)" horizontal={false} />
              <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11, fill: C_NAVY }} />
              <YAxis type="category" dataKey="name" width={130}
                tick={{ fontSize: 11, fill: C_NAVY }} />
              <Tooltip
                cursor={{ fill: 'rgba(11,44,74,0.05)' }}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const p = payload[0].payload as {
                    name: string; district: string; count: number;
                    crimes: { crime_type: string; count: number }[];
                  };
                  // Already non-zero and biggest-first from the server;
                  // capped here so one busy station can't produce a
                  // tooltip taller than the chart.
                  const shown = p.crimes.slice(0, 8);
                  const rest = p.crimes.length - shown.length;
                  return (
                    <div className="px-3 py-2 rounded-lg text-xs"
                      style={{ background: '#fff', border: `2px solid ${C_NAVY}`,
                               boxShadow: '0 6px 16px rgba(0,0,0,0.15)', maxWidth: 300 }}>
                      <div className="font-bold" style={{ color: C_NAVY }}>{p.name}</div>
                      <div className="opacity-70">{p.district}</div>
                      <div className="mt-1"><b>{fmtInt(p.count)}</b> FIRs in this range</div>
                      {shown.length > 0 && (
                        <div className="mt-1.5 pt-1.5"
                          style={{ borderTop: '1px solid rgba(11,44,74,0.15)' }}>
                          {shown.map((c) => (
                            <div key={c.crime_type} className="flex justify-between gap-3">
                              <span className="truncate">{c.crime_type}</span>
                              <b>{fmtInt(c.count)}</b>
                            </div>
                          ))}
                          {rest > 0 && (
                            <div className="opacity-60 mt-0.5">+{rest} more crime type{rest === 1 ? '' : 's'}</div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                }} />
              <Bar dataKey="count" fill={C_GREEN} radius={[0, 4, 4, 0]} name="FIRs" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="rounded-2xl p-4" style={cardStyle}>
          <h3 className="text-sm font-bold mb-1" style={{ color: C_RED }}>
            Bottom 10 Police Stations
          </h3>
          <p className="text-xs opacity-60 mb-3">
            Fewest FIRs registered in this window.
            {topBottom.zeroCount > 10 && (
              <> {fmtInt(topBottom.zeroCount)} stations are on zero — these ten are a slice of that set.</>
            )}
          </p>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={topBottom.bottom} layout="vertical"
              margin={{ top: 4, right: 24, left: 8, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(11,44,74,0.10)" horizontal={false} />
              <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11, fill: C_NAVY }} />
              <YAxis type="category" dataKey="name" width={130}
                tick={{ fontSize: 11, fill: C_NAVY }} />
              <Tooltip formatter={(v) => [fmtInt(Number(v ?? 0)), 'FIRs']}
                labelFormatter={(l, p) => `${l} — ${p?.[0]?.payload?.district ?? ''}`} />
              <Bar dataKey="count" fill={C_RED} radius={[0, 4, 4, 0]} name="FIRs" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      )}

      {tab === 'crime' && (
        <FirCrimeTypeTab report={crime} from={from} to={to} />
      )}


      {/* PS-performance table */}
      {tab === 'ranking' && (
      <div className="rounded-2xl overflow-x-auto" style={cardStyle}>
        <div className="px-5 py-4 flex items-start justify-between gap-4 flex-wrap"
          style={{ borderBottom: '3px solid var(--ksp-yellow)' }}>
          <div className="min-w-0">
            <h3 className="text-sm font-bold" style={{ color: 'var(--ksp-navy)' }}>
              FIRs registered per PS
            </h3>
            <p className="text-xs mt-1 opacity-60">
              Window: {from} → {to}. Click a column header to sort — click again to reverse.
              Zero-count PSes are shown so silent stations stay visible.
            </p>
          </div>

          <div className="flex gap-6 text-right">
            <div>
              <p className="text-[11px] uppercase tracking-wide font-bold"
                style={{ color: '#0a6b28' }}>Yesterday ({yestLabel})</p>
              <p className="text-xl font-bold" style={{ color: '#0a6b28' }}>
                {fmtInt(grandYesterday)}
              </p>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-wide font-bold"
                style={{ color: 'var(--ksp-red)' }}>Grand Total</p>
              <p className="text-xl font-bold" style={{ color: 'var(--ksp-navy)' }}>
                {fmtInt(grandTotal)}
              </p>
            </div>
          </div>
        </div>

        {/* Export buttons sit inside the table card, directly above the
             column headers — the action next to the thing it exports.
             They travel with the table: it now lives on PS Ranking
             View, and no other tab renders it. */}
        <div className="flex gap-2 justify-end px-5 py-2"
          style={{ borderBottom: '1px solid rgba(11,44,74,0.10)' }}>
          <button type="button"
            onClick={() => handleDownload('xlsx')}
            disabled={dl !== null || busy || rows.length === 0}
            title="Download this table as an Excel (.xlsx) file"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition disabled:opacity-50"
            style={{ background: '#0a5c2a', color: '#fff' }}>
            <FileSpreadsheet className="w-3.5 h-3.5" />
            {dl === 'xlsx' ? 'Generating…' : 'Excel'}
          </button>
          <button type="button"
            onClick={() => handleDownload('pdf')}
            disabled={dl !== null || busy || rows.length === 0}
            title="Download this table as a PDF file"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition disabled:opacity-50"
            style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}>
            <FileDown className="w-3.5 h-3.5" />
            {dl === 'pdf' ? 'Generating…' : 'PDF'}
          </button>
        </div>

        <table className="w-full text-sm text-left">
          <thead style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}>
            <tr>
              <th className="px-4 py-3 text-xs uppercase font-bold">#</th>
              <th className="px-4 py-3 text-xs uppercase font-bold"
                style={{ cursor: 'pointer', userSelect: 'none' }}
                onClick={() => onSort('district')}
                title="Sort by District">
                District{arrow('district')}
              </th>
              <th className="px-4 py-3 text-xs uppercase font-bold"
                style={{ cursor: 'pointer', userSelect: 'none' }}
                onClick={() => onSort('ps_name')}
                title="Sort by Police Station">
                Police Station{arrow('ps_name')}
              </th>
              <th className="px-4 py-3 text-xs uppercase font-bold text-right"
                style={{ cursor: 'pointer', userSelect: 'none' }}
                onClick={() => onSort('yesterday_count')}
                title={`FIRs registered yesterday (${yestLabel})`}>
                Yesterday ({yestLabel}){arrow('yesterday_count')}
              </th>
              <th className="px-4 py-3 text-xs uppercase font-bold text-right"
                style={{ cursor: 'pointer', userSelect: 'none' }}
                onClick={() => onSort('fir_count')}
                title="Sort by Total FIRs">
                Total FIRs{arrow('fir_count')}
              </th>
            </tr>
          </thead>
          <tbody>
            {busy && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center italic opacity-60">Loading…</td>
              </tr>
            )}
            {!busy && sortedRows.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center italic opacity-60">
                  No active PSes in scope.
                </td>
              </tr>
            )}
            {!busy && sortedRows.map((r, i) => (
              <tr key={`${r.unit_id}-${r.ps_id}`}
                className="border-t hover:bg-[#fff3b0]/30"
                style={{ borderColor: 'rgba(0,0,0,0.06)' }}>
                <td className="px-4 py-2 opacity-50">{i + 1}</td>
                <td className="px-4 py-2 font-semibold" style={{ color: 'var(--ksp-navy)' }}>
                  {r.district}
                </td>
                <td className="px-4 py-2" style={{ color: 'var(--ksp-navy)' }}>
                  {r.ps_name || '—'}
                </td>
                <td className="px-4 py-2 text-right font-bold"
                  style={{ color: r.yesterday_count === 0 ? 'rgba(0,0,0,0.35)' : '#0a6b28' }}>
                  {fmtInt(r.yesterday_count)}
                </td>
                <td className="px-4 py-2 text-right font-bold"
                  style={{ color: r.fir_count === 0 ? 'var(--ksp-red)' : 'var(--ksp-navy)' }}>
                  {fmtInt(r.fir_count)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      )}
    </div>
  );
}
