import { useState, useEffect, useMemo, type ReactNode } from 'react';
import {
  getSummary, getUnitComparison, getTrends, getSubmissionStatus,
  getCasesByPs,
  getQuietUnits, getTimeToArrest, getBankActionSla,
  getRecurringAccounts, getAccountCases, getCaseDetail,
  getBankConcentration, getDestinationBankConcentration,
  getAtmHotspots, getLayerDistribution, getAccountsAtLayer,
  getDisposalSummary, getTrialSummary, getPendingByYear,
} from '../lib/api/dashboard';
import { formatINR, formatNumber, todayISO } from '../lib/utils/format';
import type {
  KpiSummary, UnitComparison, PsComparison, TrendPoint, SubmissionStatus,
  QuietUnit, TimeToArrestRow, BankSlaRow,
  RecurringAccount, BankConcentration, AtmHotspot, LayerBucket, LienAccountAtLayer,
  AccountCaseDetail, CaseDetailFull,
  DisposalSummary, TrialSummary, PendingByYearRow,
} from '../types';
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { BarChart3, Search, Activity, Gavel, AlertTriangle, Clock, Landmark, Repeat, MapPin, Layers, FileDown } from 'lucide-react';
import { toast } from 'sonner';
import { downloadSubmissionStatusPdf } from '../lib/api/reports';

type TabKey = 'overview' | 'investigation' | 'operations' | 'disposal';

const TABS: { key: TabKey; label: string; icon: typeof BarChart3; hint: string }[] = [
  { key: 'overview',      label: 'Overview',         icon: BarChart3, hint: 'KPIs · recovery · trends' },
  { key: 'investigation', label: 'Investigation',    icon: Search,    hint: 'Mule patterns · banks · ATM hotspots' },
  { key: 'operations',    label: 'Operations',       icon: Activity,  hint: 'Submissions · SLA · quiet units' },
  { key: 'disposal',      label: 'Disposal & Trial', icon: Gavel,     hint: 'DSR disposal · trial · pending years' },
];

const cardStyle = { background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' };

function KpiCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-2xl p-5" style={{ ...cardStyle, borderLeft: '4px solid var(--ksp-yellow)' }}>
      <p className="text-xs uppercase tracking-wide font-bold mb-1" style={{ color: 'var(--ksp-red)' }}>{label}</p>
      <p className="text-2xl font-bold" style={{ color: 'var(--ksp-navy)' }}>{value}</p>
      {sub && <p className="text-xs mt-1 opacity-60">{sub}</p>}
    </div>
  );
}

function getHashTab(): TabKey {
  const h = window.location.hash.replace('#', '').toLowerCase();
  return (TABS.find(t => t.key === h)?.key) ?? 'overview';
}

export function DashboardPage() {
  const [date, setDate] = useState(todayISO());
  const [tab, setTab] = useState<TabKey>(getHashTab());

  useEffect(() => {
    const onHash = () => setTab(getHashTab());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const setTabAndHash = (k: TabKey) => {
    setTab(k);
    if (window.location.hash !== `#${k}`) window.location.hash = k;
  };

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between mb-4">
        <div>
          <h1 className="text-[22px] font-bold flex items-center gap-2" style={{ color: 'var(--ksp-navy)' }}>
            <BarChart3 className="w-6 h-6" /> Dashboard
          </h1>
          <p className="text-sm font-medium" style={{ color: 'var(--ksp-red)' }}>District cyber fraud overview</p>
        </div>
        <div>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="px-3 py-2 rounded-xl text-sm outline-none"
            style={{ border: '2px solid var(--ksp-navy)' }}
          />
        </div>
      </div>

      <div className="flex flex-wrap gap-2 mb-6" role="tablist" aria-label="Dashboard sections">
        {TABS.map(t => {
          const Icon = t.icon;
          const active = tab === t.key;
          return (
            <button
              key={t.key}
              role="tab"
              aria-selected={active}
              onClick={() => setTabAndHash(t.key)}
              title={t.hint}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold transition"
              style={{
                background: active ? 'var(--ksp-navy)' : '#fff',
                color: active ? 'var(--ksp-yellow)' : 'var(--ksp-navy)',
                border: active ? '2px solid var(--ksp-navy)' : '2px solid rgba(11,44,74,0.18)',
                boxShadow: active ? '0 4px 10px rgba(11,44,74,0.25)' : 'none',
              }}
            >
              <Icon className="w-4 h-4" />
              {t.label}
            </button>
          );
        })}
      </div>

      {tab === 'overview'      && <OverviewTab date={date} />}
      {tab === 'investigation' && <InvestigationTab date={date} />}
      {tab === 'operations'    && <OperationsTab date={date} />}
      {tab === 'disposal'      && <DisposalTab date={date} />}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// Overview tab — existing KPIs + Recovery Funnel + Recovery Rate gauge
// ──────────────────────────────────────────────────────────────────────────

function OverviewTab({ date }: { date: string }) {
  const [summary, setSummary] = useState<KpiSummary | null>(null);
  const [units, setUnits] = useState<UnitComparison[]>([]);
  const [trends, setTrends] = useState<TrendPoint[]>([]);
  const [statuses, setStatuses] = useState<SubmissionStatus[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const d = new Date(date);
    const from = new Date(d);
    from.setDate(from.getDate() - 30);
    const fromStr = from.toISOString().split('T')[0];

    Promise.allSettled([
      getSummary(date),
      getUnitComparison(date),
      getTrends(fromStr, date),
      getSubmissionStatus(date),
    ]).then(([s, u, t, st]) => {
      setSummary(s.status === 'fulfilled' ? s.value : null);
      setUnits(u.status === 'fulfilled' ? u.value : []);
      setTrends(t.status === 'fulfilled' ? t.value : []);
      setStatuses(st.status === 'fulfilled' ? st.value : []);
    }).finally(() => setLoading(false));
  }, [date]);

  const top15 = units.slice(0, 15);

  // Recovery funnel — three of the four totals come straight from /summary;
  // "outstanding" is what's still held by banks: lien − refunded − defreezed.
  // Clamp at 0 so a partially-entered batch (refunds entered before liens)
  // never draws a negative bar.
  const lien = summary?.total_amount_lien_marked ?? 0;
  const refunded = summary?.total_amount_refunded ?? 0;
  const defreezed = summary?.total_amount_defreezed ?? 0;
  const outstanding = Math.max(0, lien - refunded - defreezed);
  const recoveryRate = lien > 0 ? (refunded / lien) * 100 : 0;

  const funnelData = useMemo(() => ([
    { name: 'Lien Marked',      value: lien,        fill: '#0b2c4a' },
    { name: 'Refunded',         value: refunded,    fill: '#0a5c2a' },
    { name: 'Released',         value: defreezed,   fill: '#b10000' },
    { name: 'Outstanding',      value: outstanding, fill: '#ffd400' },
  ]), [lien, refunded, defreezed, outstanding]);

  if (loading) {
    return <div className="text-center py-16 font-semibold" style={{ color: 'var(--ksp-navy)' }}>Loading dashboard...</div>;
  }

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        <KpiCard label="Total Cases" value={formatNumber(summary?.total_cases ?? 0)} />
        <KpiCard label="Total Arrests" value={formatNumber(summary?.total_arrests ?? 0)} />
        <KpiCard label="Amount Lien Marked" value={formatINR(lien)} />
        <KpiCard label="Accounts Lien Marked" value={formatNumber(summary?.total_accounts_lien_marked ?? 0)} />
        <KpiCard label="Accounts De-Freezed" value={formatNumber(summary?.total_accounts_defreezed ?? 0)} />
      </div>

      {/* NEW — Recovery Funnel + Recovery Rate */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="rounded-2xl p-5 lg:col-span-2" style={cardStyle}>
          <h3 className="text-sm font-bold mb-1" style={{ color: 'var(--ksp-navy)' }}>Money Recovery Funnel</h3>
          <p className="text-xs mb-3 opacity-60">Where the lien-marked money sits today — refunded to victims, released back to accounts, or still held.</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            {funnelData.map((d) => (
              <div key={d.name} className="rounded-lg px-3 py-2" style={{ background: '#fafafa', borderLeft: `4px solid ${d.fill}` }}>
                <p className="text-[10px] uppercase tracking-wide font-bold opacity-70">{d.name}</p>
                <p className="text-sm font-bold" style={{ color: 'var(--ksp-navy)' }}>{formatINR(d.value)}</p>
              </div>
            ))}
          </div>
          {funnelData.every(d => d.value === 0) ? (
            <div className="py-8 text-center text-sm opacity-60">No money-flow data yet — lien accounts, refunds, and unfreeze entries are all at zero.</div>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={funnelData} layout="vertical" margin={{ left: 0, right: 60 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" domain={[0, 'dataMax']} tick={{ fontSize: 11 }} tickFormatter={(v) => formatINR(Number(v))} />
                <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 12 }} />
                <Tooltip formatter={(val) => formatINR(Number(val) || 0)} />
                <Bar dataKey="value" name="Amount" label={{ position: 'right', formatter: (v: string | number | boolean | null | undefined) => (v == null || typeof v === 'boolean' ? '' : formatINR(Number(v))), fontSize: 10, fill: '#0b2c4a' }}>
                  {funnelData.map((d, i) => <Cell key={i} fill={d.fill} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <RecoveryRateGauge rate={recoveryRate} refunded={refunded} lien={lien} />
      </div>

      {/* Trend + Comparison */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-2xl p-5" style={cardStyle}>
          <h3 className="text-sm font-bold mb-4" style={{ color: 'var(--ksp-navy)' }}>Cases Trend (Last 30 Days)</h3>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={trends}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="report_date" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="total_cases" stroke="#0b2c4a" name="Cases" strokeWidth={2} />
              <Line type="monotone" dataKey="total_arrests" stroke="#b10000" name="Arrests" strokeWidth={2} />
              <Line type="monotone" dataKey="total_petitions" stroke="#0a5c2a" name="Petitions" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <CasesByUnitCard date={date} units={top15} />
      </div>

      <SubmissionStatusTable statuses={statuses} refDate={date} />
    </div>
  );
}

function RecoveryRateGauge({ rate, refunded, lien }: { rate: number; refunded: number; lien: number }) {
  const clamped = Math.min(100, Math.max(0, rate));
  // Color crosses from red (0%) to yellow (50%) to navy (100%) — KSP palette.
  const color = clamped < 25 ? '#b10000' : clamped < 60 ? '#ffd400' : '#0a5c2a';
  return (
    <div className="rounded-2xl p-5 flex flex-col items-center justify-center" style={cardStyle}>
      <p className="text-xs uppercase tracking-wide font-bold mb-2" style={{ color: 'var(--ksp-red)' }}>Recovery Rate</p>
      <div
        className="relative rounded-full flex items-center justify-center"
        style={{
          width: 160, height: 160,
          background: `conic-gradient(${color} ${clamped * 3.6}deg, rgba(11,44,74,0.08) 0deg)`,
        }}
      >
        <div className="absolute rounded-full bg-white flex flex-col items-center justify-center" style={{ width: 124, height: 124 }}>
          <p className="text-3xl font-bold" style={{ color: 'var(--ksp-navy)' }}>{clamped.toFixed(1)}%</p>
          <p className="text-[10px] opacity-60">refunded / lien</p>
        </div>
      </div>
      <div className="text-center mt-4">
        <p className="text-xs opacity-70">{formatINR(refunded)} of {formatINR(lien)}</p>
      </div>
    </div>
  );
}

// Relative date helper for the Last Entry column.
// refDate / iso are ISO YYYY-MM-DD strings. Returns ("label", color) tuple.
function relativeDate(iso: string | null, refDate: string): { label: string; color: string } {
  if (!iso) return { label: 'Never', color: 'var(--ksp-red)' };
  const ref = new Date(refDate + 'T00:00:00');
  const d = new Date(iso + 'T00:00:00');
  const days = Math.round((ref.getTime() - d.getTime()) / 86_400_000);
  if (days <= 0) return { label: 'Today',     color: '#0a5c2a' };
  if (days === 1) return { label: 'Yesterday', color: '#0a5c2a' };
  if (days <= 7)  return { label: `${days}d ago`, color: 'var(--ksp-navy)' };
  if (days <= 30) return { label: `${days}d ago`, color: '#b45309' };
  return { label: `${days}d ago`, color: 'var(--ksp-red)' };
}

type SubmissionSortKey = 'district' | 'cases' | 'total' | 'last_entry';
type SortDir = 'asc' | 'desc';

function SubmissionStatusTable({ statuses, refDate }: { statuses: SubmissionStatus[]; refDate: string }) {
  const [sortBy, setSortBy] = useState<SubmissionSortKey>('total');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  const onSort = (key: SubmissionSortKey, defaultDir: SortDir) => {
    if (sortBy === key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(key);
      setSortDir(defaultDir);
    }
  };

  const compare = (a: SubmissionStatus, b: SubmissionStatus): number => {
    let r = 0;
    if (sortBy === 'district') {
      r = a.unit_name.localeCompare(b.unit_name);
    } else if (sortBy === 'cases') {
      r = a.cases_count - b.cases_count;
    } else if (sortBy === 'last_entry') {
      // Nulls (never entered) always sink to the bottom regardless of direction.
      if (a.last_entry_date == null && b.last_entry_date == null) r = 0;
      else if (a.last_entry_date == null) return 1;
      else if (b.last_entry_date == null) return -1;
      else r = a.last_entry_date.localeCompare(b.last_entry_date);
    } else { // total
      r = a.entry_count - b.entry_count;
    }
    if (sortDir === 'desc') r = -r;
    // Tiebreaker so the order is stable across renders.
    return r || a.unit_name.localeCompare(b.unit_name) || a.ps_name.localeCompare(b.ps_name);
  };

  const sorted = [...statuses].sort(compare);
  const arrow = (key: SubmissionSortKey) =>
    sortBy === key ? <span className="ml-1 opacity-80">{sortDir === 'asc' ? '▲' : '▼'}</span> : null;

  const [pdfBusy, setPdfBusy] = useState(false);
  const onDownloadPdf = async () => {
    setPdfBusy(true);
    try {
      await downloadSubmissionStatusPdf(refDate);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to download PDF');
    } finally {
      setPdfBusy(false);
    }
  };

  return (
    <div className="rounded-2xl overflow-x-auto" style={cardStyle}>
      <div className="px-5 py-4 flex items-start justify-between gap-4" style={{ borderBottom: '3px solid var(--ksp-yellow)' }}>
        <div className="min-w-0">
          <h3 className="text-sm font-bold" style={{ color: 'var(--ksp-navy)' }}>Submission Status for {refDate}</h3>
          <p className="text-xs mt-1 opacity-60">One row per Police Station. Total = Cases + Petitions + Mule. Click District / Cases / Total / Last Entry to sort — click again to reverse direction. Last-entry colour: green = today/yesterday, navy ≤ 7d, amber ≤ 30d, red &gt; 30d or never. NIL declarations count as a valid entry, so a PS that only ever declares NIL never shows "Never". DSR is district-level so all PSes in the same district show the same flag.</p>
        </div>
        <button
          type="button"
          onClick={onDownloadPdf}
          disabled={pdfBusy || statuses.length === 0}
          className="flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-bold transition disabled:opacity-50 shrink-0"
          style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}
          title="Download this table as a PDF report"
        >
          <FileDown className="w-3.5 h-3.5" />
          {pdfBusy ? 'Generating…' : 'Download PDF'}
        </button>
      </div>
      <table className="w-full text-sm text-left">
        <thead style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}>
          <tr>
            <th className="px-4 py-3 text-xs uppercase font-bold">#</th>
            <th className="px-4 py-3 text-xs uppercase font-bold"
                style={{ cursor: 'pointer', userSelect: 'none' }}
                onClick={() => onSort('district', 'asc')}
                title="Sort by District">
              District{arrow('district')}
            </th>
            <th className="px-4 py-3 text-xs uppercase font-bold">Police Station</th>
            <th className="px-4 py-3 text-xs uppercase font-bold text-right"
                style={{ cursor: 'pointer', userSelect: 'none' }}
                onClick={() => onSort('cases', 'desc')}
                title="Sort by Cases">
              Cases{arrow('cases')}
            </th>
            <th className="px-4 py-3 text-xs uppercase font-bold text-right">Petitions</th>
            <th className="px-4 py-3 text-xs uppercase font-bold text-right">Mule</th>
            <th className="px-4 py-3 text-xs uppercase font-bold text-right"
                style={{ cursor: 'pointer', userSelect: 'none' }}
                onClick={() => onSort('total', 'desc')}
                title="Sort by Total (Cases + Petitions + Mule)">
              Total{arrow('total')}
            </th>
            <th className="px-4 py-3 text-xs uppercase font-bold text-right" title="Cumulative NIL declarations up to the selected date">NIL</th>
            <th className="px-4 py-3 text-xs uppercase font-bold"
                style={{ cursor: 'pointer', userSelect: 'none' }}
                onClick={() => onSort('last_entry', 'desc')}
                title="Sort by Last Entry">
              Last Entry{arrow('last_entry')}
            </th>
            <th className="px-4 py-3 text-xs uppercase font-bold text-center">DSR</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((s, i) => {
            const last = relativeDate(s.last_entry_date, refDate);
            return (
              <tr key={`${s.unit_id}-${s.ps_id}`} className="border-t hover:bg-[#fff3b0]/30" style={{ borderColor: 'rgba(0,0,0,0.06)' }}>
                <td className="px-4 py-2 opacity-50">{i + 1}</td>
                <td className="px-4 py-2 font-semibold" style={{ color: 'var(--ksp-navy)' }}>{s.unit_name}</td>
                <td className="px-4 py-2" style={{ color: 'var(--ksp-navy)' }}>{s.ps_name || '—'}</td>
                <td className="px-4 py-2 text-right" style={{ color: 'var(--ksp-navy)' }}>
                  {formatNumber(s.cases_count)}
                </td>
                <td className="px-4 py-2 text-right" style={{ color: 'var(--ksp-navy)' }}>
                  {formatNumber(s.petitions_count)}
                </td>
                <td className="px-4 py-2 text-right" style={{ color: 'var(--ksp-navy)' }}>
                  {formatNumber(s.mule_count)}
                </td>
                <td className="px-4 py-2 text-right font-bold">
                  {s.entry_count === 0 && s.nil_declared ? (
                    <span
                      className="text-xs font-bold px-2 py-0.5 rounded"
                      title={s.nil_declared_by_name ? `NIL declared by ${s.nil_declared_by_name}` : 'NIL declared for this date'}
                      style={{ background: 'rgba(10,92,42,0.12)', color: '#0a5c2a', border: '1px solid rgba(10,92,42,0.30)' }}
                    >
                      NIL ✓
                    </span>
                  ) : (
                    <span style={{ color: s.entry_count === 0 ? 'var(--ksp-red)' : 'var(--ksp-navy)' }}>
                      {formatNumber(s.entry_count)}
                    </span>
                  )}
                </td>
                <td className="px-4 py-2 text-right" style={{ color: s.nil_count > 0 ? '#0a5c2a' : 'rgba(0,0,0,0.35)' }}>
                  {s.nil_count > 0 ? formatNumber(s.nil_count) : '—'}
                </td>
                <td className="px-4 py-2">
                  <span className="text-xs font-bold px-2 py-0.5 rounded" style={{ color: last.color, background: 'rgba(0,0,0,0.04)' }}>
                    {last.label}
                  </span>
                </td>
                <td className="px-4 py-2 text-center">
                  {s.dsr_filed ? (
                    <span className="text-sm font-bold" style={{ color: '#0a5c2a' }}>✓</span>
                  ) : (
                    <span className="text-sm font-bold" style={{ color: 'var(--ksp-red)' }}>✗</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function CasesByUnitCard({ date, units }: { date: string; units: UnitComparison[] }) {
  const [drill, setDrill] = useState<{ unit_id: number; unit_name: string } | null>(null);
  const [psData, setPsData] = useState<PsComparison[]>([]);
  const [drillLoading, setDrillLoading] = useState(false);
  const [drillError, setDrillError] = useState<string | null>(null);

  useEffect(() => {
    // Reset drill when date changes — the parent re-fetches the unit list,
    // so the existing drill could now be pointing at a stale snapshot.
    setDrill(null);
    setPsData([]);
    setDrillError(null);
  }, [date]);

  useEffect(() => {
    if (!drill) return;
    setDrillLoading(true);
    setDrillError(null);
    getCasesByPs(date, drill.unit_id)
      .then(setPsData)
      .catch((e: Error) => setDrillError(e?.message ?? 'Failed to load PS breakdown'))
      .finally(() => setDrillLoading(false));
  }, [date, drill]);

  // Each chart row needs a label + cases. We also keep ps_count and unit_id
  // for district rows so the click handler can gate drill-down per row.
  const chartData = drill
    ? psData.map(r => ({ label: r.ps_name, cases: r.cases, drillable: false }))
    : units.map(r => ({
        label: r.unit_name,
        cases: r.cases,
        unit_id: r.unit_id,
        ps_count: r.ps_count,
        drillable: r.ps_count > 1,
      }));

  const handleBarClick = (data: { unit_id?: number; label: string; drillable?: boolean }) => {
    // Drill-in only fires from the district view, and only for districts
    // with more than one PS — there's nothing to break down otherwise.
    if (drill || data.unit_id === undefined || !data.drillable) return;
    setDrill({ unit_id: data.unit_id, unit_name: data.label });
  };

  const title = drill ? `Cases by PS — ${drill.unit_name}` : 'Cases by Unit';
  const hint = drill
    ? 'Click "← Back" to return to the district view.'
    : 'Districts with more than one PS are highlighted in navy — click to drill down. Single-PS districts are shown muted.';
  const DRILL_COLOR = '#0b2c4a';   // navy — clickable
  const FLAT_COLOR  = '#94a3b8';   // muted slate — non-drillable
  const PS_COLOR    = '#0a5c2a';   // green — PS view

  return (
    <div className="rounded-2xl p-5" style={cardStyle}>
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-sm font-bold" style={{ color: 'var(--ksp-navy)' }}>{title}</h3>
        {drill && (
          <button
            onClick={() => { setDrill(null); setPsData([]); }}
            className="text-xs font-bold px-3 py-1 rounded-lg"
            style={{ background: 'var(--ksp-yellow)', color: 'var(--ksp-navy)' }}
          >
            ← Back to Districts
          </button>
        )}
      </div>
      <p className="text-xs mb-3 opacity-60">{hint}</p>

      {drillLoading ? (
        <div className="py-12 text-center text-sm" style={{ color: 'var(--ksp-navy)' }}>Loading PS breakdown…</div>
      ) : drillError ? (
        <div className="py-8 text-center text-sm" style={{ color: 'var(--ksp-red)' }}>{drillError}</div>
      ) : chartData.length === 0 ? (
        <div className="py-12 text-center text-sm opacity-60">
          {drill ? `No cases recorded for ${drill.unit_name} yet.` : 'No cases recorded yet.'}
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={Math.max(280, chartData.length * 22)}>
          <BarChart data={chartData} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
            <YAxis dataKey="label" type="category" width={150} tick={{ fontSize: 9 }} />
            <Tooltip />
            <Bar
              dataKey="cases"
              name="Cases"
              cursor="default"
              onClick={(p: unknown) => {
                // Recharts wraps the row in `.payload` for some chart types
                // and passes it bare for others. Tolerate both shapes.
                const r = p as {
                  payload?: { unit_id?: number; label?: string; drillable?: boolean };
                  unit_id?: number; label?: string; drillable?: boolean;
                };
                const row = r?.payload ?? r;
                if (row && typeof row.label === 'string') {
                  handleBarClick({
                    unit_id: row.unit_id,
                    label: row.label,
                    drillable: row.drillable,
                  });
                }
              }}
            >
              {chartData.map((d, i) => (
                <Cell
                  key={i}
                  fill={drill ? PS_COLOR : (d.drillable ? DRILL_COLOR : FLAT_COLOR)}
                  cursor={!drill && d.drillable ? 'pointer' : 'default'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// Operations tab — quiet-unit alerts, time-to-arrest, bank-action SLA
// ──────────────────────────────────────────────────────────────────────────

function OperationsTab({ date }: { date: string }) {
  const [threshold, setThreshold] = useState(7);
  const [quiet, setQuiet] = useState<QuietUnit[]>([]);
  const [tta, setTta] = useState<TimeToArrestRow[]>([]);
  const [sla, setSla] = useState<BankSlaRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      getQuietUnits(date, threshold),
      getTimeToArrest(date, 90),
      getBankActionSla(date, 180),
    ]).then(([q, t, b]) => {
      setQuiet(q.status === 'fulfilled' ? q.value : []);
      setTta(t.status === 'fulfilled' ? t.value : []);
      setSla(b.status === 'fulfilled' ? b.value : []);
    }).finally(() => setLoading(false));
  }, [date, threshold]);

  if (loading) {
    return <div className="text-center py-16 font-semibold" style={{ color: 'var(--ksp-navy)' }}>Loading operations data...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <QuietUnitsCard rows={quiet} threshold={threshold} onThresholdChange={setThreshold} />
        <TimeToArrestCard rows={tta} />
      </div>
      <BankSlaCard rows={sla} />
    </div>
  );
}

function QuietUnitsCard({
  rows, threshold, onThresholdChange,
}: { rows: QuietUnit[]; threshold: number; onThresholdChange: (n: number) => void }) {
  return (
    <div className="rounded-2xl" style={cardStyle}>
      <div className="px-5 py-4 flex items-center justify-between" style={{ borderBottom: '3px solid var(--ksp-yellow)' }}>
        <h3 className="text-sm font-bold flex items-center gap-2" style={{ color: 'var(--ksp-navy)' }}>
          <AlertTriangle className="w-4 h-4" /> Quiet Units
        </h3>
        <label className="text-xs flex items-center gap-2">
          Silent for ≥
          <select
            value={threshold}
            onChange={(e) => onThresholdChange(Number(e.target.value))}
            className="px-2 py-1 rounded text-xs"
            style={{ border: '1px solid var(--ksp-navy)' }}
          >
            <option value={3}>3 days</option>
            <option value={7}>7 days</option>
            <option value={14}>14 days</option>
            <option value={30}>30 days</option>
          </select>
        </label>
      </div>
      {rows.length === 0 ? (
        <div className="p-8 text-center text-sm" style={{ color: 'var(--ksp-navy)' }}>
          All units active in the last {threshold} days.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}>
              <tr>
                <th className="px-4 py-2 text-xs uppercase font-bold">District</th>
                <th className="px-4 py-2 text-xs uppercase font-bold text-right">Days Silent</th>
                <th className="px-4 py-2 text-xs uppercase font-bold">Last Entry</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.unit_id} className="border-t" style={{ borderColor: 'rgba(0,0,0,0.06)' }}>
                  <td className="px-4 py-2 font-semibold" style={{ color: 'var(--ksp-navy)' }}>{r.unit_name}</td>
                  <td className="px-4 py-2 text-right font-bold" style={{ color: 'var(--ksp-red)' }}>
                    {r.days_silent === null ? 'Never' : r.days_silent}
                  </td>
                  <td className="px-4 py-2 opacity-70">{r.last_entry_date ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function TimeToArrestCard({ rows }: { rows: TimeToArrestRow[] }) {
  return (
    <div className="rounded-2xl p-5" style={cardStyle}>
      <h3 className="text-sm font-bold mb-1 flex items-center gap-2" style={{ color: 'var(--ksp-navy)' }}>
        <Clock className="w-4 h-4" /> Time to Arrest
      </h3>
      <p className="text-xs mb-4 opacity-60">Avg days from case registration to first arrest, per district (last 90 days). Lower is faster.</p>
      {rows.length === 0 ? (
        <div className="py-10 text-center text-sm opacity-60">No arrest data in the last 90 days.</div>
      ) : (
        <ResponsiveContainer width="100%" height={Math.max(220, rows.length * 24)}>
          <BarChart data={rows} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" tick={{ fontSize: 11 }} label={{ value: 'days', position: 'insideBottom', fontSize: 10 }} />
            <YAxis type="category" dataKey="unit_name" width={140} tick={{ fontSize: 9 }} />
            <Tooltip formatter={(val, _name, p) => [`${val} days (n=${p?.payload?.sample_size})`, 'Avg time']} />
            <Bar dataKey="avg_days" fill="#0a5c2a" name="Avg days" />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// Investigation tab — patterns and leads
// ──────────────────────────────────────────────────────────────────────────

function InvestigationTab({ date }: { date: string }) {
  const [accounts, setAccounts] = useState<RecurringAccount[]>([]);
  const [muleBanks, setMuleBanks] = useState<BankConcentration[]>([]);
  const [destBanks, setDestBanks] = useState<BankConcentration[]>([]);
  const [atms, setAtms] = useState<AtmHotspot[]>([]);
  const [layers, setLayers] = useState<LayerBucket[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      getRecurringAccounts(date, 2, 50),
      getBankConcentration(date, 15),
      getDestinationBankConcentration(date, 15),
      getAtmHotspots(date, 15),
      getLayerDistribution(date),
    ]).then(([a, mb, db, m, l]) => {
      setAccounts(a.status === 'fulfilled' ? a.value : []);
      setMuleBanks(mb.status === 'fulfilled' ? mb.value : []);
      setDestBanks(db.status === 'fulfilled' ? db.value : []);
      setAtms(m.status === 'fulfilled' ? m.value : []);
      setLayers(l.status === 'fulfilled' ? l.value : []);
    }).finally(() => setLoading(false));
  }, [date]);

  if (loading) {
    return <div className="text-center py-16 font-semibold" style={{ color: 'var(--ksp-navy)' }}>Loading investigation data...</div>;
  }

  return (
    <div className="space-y-6">
      <RecurringAccountsCard rows={accounts} date={date} />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <MuleAccountBanksCard rows={muleBanks} />
        <DestinationBanksCard rows={destBanks} />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <AtmHotspotsCard rows={atms} />
        <LayerDistributionCard rows={layers} date={date} />
      </div>
    </div>
  );
}

function RecurringAccountsCard({ rows, date }: { rows: RecurringAccount[]; date: string }) {
  const [selectedAccount, setSelectedAccount] = useState<{ account_no: string; bank: string | null } | null>(null);
  const [cases, setCases] = useState<AccountCaseDetail[]>([]);
  const [casesLoading, setCasesLoading] = useState(false);
  const [casesError, setCasesError] = useState<string | null>(null);

  const [selectedCase, setSelectedCase] = useState<{ case_id: string; label: string } | null>(null);
  const [caseDetail, setCaseDetail] = useState<CaseDetailFull | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Reset everything when the parent date changes (underlying account list
  // could be different).
  useEffect(() => {
    setSelectedAccount(null); setCases([]); setCasesError(null);
    setSelectedCase(null); setCaseDetail(null); setDetailError(null);
  }, [date]);

  useEffect(() => {
    if (!selectedAccount) return;
    setCasesLoading(true); setCasesError(null);
    getAccountCases(date, selectedAccount.account_no)
      .then(setCases)
      .catch((e: Error) => setCasesError(e?.message ?? 'Failed to load case list'))
      .finally(() => setCasesLoading(false));
  }, [date, selectedAccount]);

  useEffect(() => {
    if (!selectedCase) return;
    setDetailLoading(true); setDetailError(null);
    getCaseDetail(selectedCase.case_id)
      .then(setCaseDetail)
      .catch((e: Error) => setDetailError(e?.message ?? 'Failed to load case detail'))
      .finally(() => setDetailLoading(false));
  }, [selectedCase]);

  // Header changes per drill level
  const level = selectedCase ? 3 : selectedAccount ? 2 : 1;
  const title = level === 3
    ? <>Case Detail — <span className="font-mono">{selectedCase!.label}</span></>
    : level === 2
      ? <>Cases for Account <span className="font-mono">{selectedAccount!.account_no}</span></>
      : 'Recurring Mule Accounts';
  const hint = level === 3
    ? 'Key fields from this case. Click "← Back" to return to the case list for this account.'
    : level === 2
      ? `Bank: ${selectedAccount!.bank ?? '—'}. Click any FIR / Petition number to view case details.`
      : 'Account numbers appearing in 2 or more distinct cases. Click an account number to see the cases it appears in.';
  const backLabel = level === 3 ? '← Back to Cases' : '← Back to Accounts';
  const handleBack = () => {
    if (level === 3) { setSelectedCase(null); setCaseDetail(null); setDetailError(null); }
    else if (level === 2) { setSelectedAccount(null); setCases([]); setCasesError(null); }
  };

  return (
    <div className="rounded-2xl" style={cardStyle}>
      <div className="px-5 py-4 flex items-start justify-between gap-3" style={{ borderBottom: '3px solid var(--ksp-yellow)' }}>
        <div>
          <h3 className="text-sm font-bold flex items-center gap-2" style={{ color: 'var(--ksp-navy)' }}>
            <Repeat className="w-4 h-4" />
            {title}
          </h3>
          <p className="text-xs mt-1 opacity-60">{hint}</p>
        </div>
        {level > 1 && (
          <button
            onClick={handleBack}
            className="text-xs font-bold px-3 py-1 rounded-lg whitespace-nowrap"
            style={{ background: 'var(--ksp-yellow)', color: 'var(--ksp-navy)' }}
          >
            {backLabel}
          </button>
        )}
      </div>

      {/* Level 3 — case detail */}
      {level === 3 && (
        detailLoading ? (
          <div className="p-8 text-center text-sm" style={{ color: 'var(--ksp-navy)' }}>Loading case detail…</div>
        ) : detailError ? (
          <div className="p-8 text-center text-sm" style={{ color: 'var(--ksp-red)' }}>{detailError}</div>
        ) : caseDetail ? (
          <CaseDetailView c={caseDetail} focusAccountNo={selectedAccount?.account_no ?? null} />
        ) : null
      )}

      {/* Level 2 — cases for selected account */}
      {level === 2 && (
        casesLoading ? (
          <div className="p-8 text-center text-sm" style={{ color: 'var(--ksp-navy)' }}>Loading cases…</div>
        ) : casesError ? (
          <div className="p-8 text-center text-sm" style={{ color: 'var(--ksp-red)' }}>{casesError}</div>
        ) : cases.length === 0 ? (
          <div className="p-8 text-center text-sm opacity-60">No cases visible for this account in your scope.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}>
                <tr>
                  <th className="px-4 py-2 text-xs uppercase font-bold">FIR / Petition</th>
                  <th className="px-4 py-2 text-xs uppercase font-bold">Reg. Date</th>
                  <th className="px-4 py-2 text-xs uppercase font-bold">District</th>
                  <th className="px-4 py-2 text-xs uppercase font-bold">PS</th>
                  <th className="px-4 py-2 text-xs uppercase font-bold">Crime Type</th>
                  <th className="px-4 py-2 text-xs uppercase font-bold text-right">Amount</th>
                  <th className="px-4 py-2 text-xs uppercase font-bold text-right">Layer</th>
                  <th className="px-4 py-2 text-xs uppercase font-bold">Status</th>
                </tr>
              </thead>
              <tbody>
                {cases.map((c) => {
                  const label = c.fir_no ?? c.petition_no ?? '(no number)';
                  return (
                    <tr key={c.case_id} className="border-t hover:bg-[#fff3b0]/30" style={{ borderColor: 'rgba(0,0,0,0.06)' }}>
                      <td className="px-4 py-2 font-semibold">
                        <button
                          onClick={() => setSelectedCase({ case_id: c.case_id, label })}
                          style={{ color: 'var(--ksp-navy)', textDecoration: 'underline', background: 'none', border: 'none', padding: 0, cursor: 'pointer', font: 'inherit' }}
                          title="View key fields for this case"
                        >
                          {label}
                        </button>
                      </td>
                      <td className="px-4 py-2 opacity-80">{c.registration_date ?? '—'}</td>
                      <td className="px-4 py-2 font-semibold" style={{ color: 'var(--ksp-navy)' }}>{c.district || '—'}</td>
                      <td className="px-4 py-2 opacity-80">{c.ps_name ?? '—'}</td>
                      <td className="px-4 py-2 opacity-80">{c.crime_type ?? '—'}</td>
                      <td className="px-4 py-2 text-right font-bold" style={{ color: 'var(--ksp-navy)' }}>{formatINR(c.amount)}</td>
                      <td className="px-4 py-2 text-right">{c.layer ?? '—'}</td>
                      <td className="px-4 py-2">
                        <span
                          className="text-xs font-bold px-2 py-0.5 rounded"
                          style={{
                            background: c.status === 'submitted' ? '#dcfce7' : '#fef3c7',
                            color: c.status === 'submitted' ? '#0a5c2a' : '#92400e',
                          }}
                        >
                          {c.status ?? 'draft'}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* Level 1 — recurring accounts list */}
      {level === 1 && (
        rows.length === 0 ? (
          <div className="p-8 text-center text-sm opacity-60">No accounts have been seen across multiple cases yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}>
                <tr>
                  <th className="px-4 py-2 text-xs uppercase font-bold">Account No</th>
                  <th className="px-4 py-2 text-xs uppercase font-bold">Bank</th>
                  <th className="px-4 py-2 text-xs uppercase font-bold text-right">Cases</th>
                  <th className="px-4 py-2 text-xs uppercase font-bold text-right">Districts</th>
                  <th className="px-4 py-2 text-xs uppercase font-bold text-right">Lien Total</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.account_no} className="border-t hover:bg-[#fff3b0]/30" style={{ borderColor: 'rgba(0,0,0,0.06)' }}>
                    <td
                      className="px-4 py-2 font-mono text-xs"
                      style={{ color: 'var(--ksp-navy)', cursor: 'pointer', textDecoration: 'underline' }}
                      onClick={() => setSelectedAccount({ account_no: r.account_no, bank: r.bank })}
                      title="Click to see all cases for this account"
                    >
                      {r.account_no}
                    </td>
                    <td className="px-4 py-2 opacity-80">{r.bank ?? '—'}</td>
                    <td className="px-4 py-2 text-right font-bold" style={{ color: 'var(--ksp-red)' }}>{r.case_count}</td>
                    <td className="px-4 py-2 text-right">{r.units_count}</td>
                    <td className="px-4 py-2 text-right font-bold" style={{ color: 'var(--ksp-navy)' }}>{formatINR(r.total_amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  );
}

// Reusable little label/value row for the case header grid.
function KV({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wide font-bold opacity-60">{label}</p>
      <p className="text-sm font-semibold" style={{ color: 'var(--ksp-navy)' }}>{value}</p>
    </div>
  );
}

function CaseDetailView({ c, focusAccountNo }: { c: CaseDetailFull; focusAccountNo: string | null }) {
  const label = c.fir_no ?? c.petition_no ?? '(no number)';
  return (
    <div className="p-5 space-y-5">
      {/* Header grid — key:value layout */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
        <KV label="FIR / Petition" value={<span className="font-mono">{label}</span>} />
        <KV label="Registration Date" value={c.registration_date ?? '—'} />
        <KV label="Case Type" value={c.case_type ?? '—'} />
        <KV label="Crime Type" value={c.crime_type ?? '—'} />
        <KV label="District" value={c.district || '—'} />
        <KV label="Police Station" value={c.ps_name ?? '—'} />
        <KV label="Status" value={
          <span className="text-xs font-bold px-2 py-0.5 rounded inline-block"
                style={{
                  background: c.status === 'submitted' ? '#dcfce7' : '#fef3c7',
                  color: c.status === 'submitted' ? '#0a5c2a' : '#92400e',
                }}>
            {c.status ?? 'draft'}
          </span>
        } />
      </div>

      {c.facts && (
        <div>
          <p className="text-[10px] uppercase tracking-wide font-bold opacity-60 mb-1">Facts</p>
          <p className="text-sm opacity-90 whitespace-pre-wrap" style={{ color: 'var(--ksp-navy)' }}>{c.facts}</p>
        </div>
      )}

      <CaseSubTable
        title={`Arrests (${c.arrests.length})`}
        empty="No arrests recorded."
        rows={c.arrests}
        columns={[
          { header: 'Name',          render: (r) => r.name || '—' },
          { header: 'Date of Arrest',render: (r) => r.date_of_arrest ?? '—' },
          { header: 'Aadhar',        render: (r) => r.aadhar ?? '—' },
          { header: 'PAN',           render: (r) => r.pan ?? '—' },
        ]}
      />
      <CaseSubTable
        title={`Lien Accounts (${c.lien_accounts.length})`}
        empty="No lien accounts recorded."
        rows={c.lien_accounts}
        highlightRow={focusAccountNo ? (r) => r.account_no === focusAccountNo : undefined}
        columns={[
          { header: 'Account No', render: (r) => (
            <span className="font-mono text-xs">
              {r.account_no || '—'}
              {focusAccountNo && r.account_no === focusAccountNo && (
                <span
                  className="ml-2 text-[10px] font-bold px-1.5 py-0.5 rounded"
                  style={{ background: 'var(--ksp-yellow)', color: 'var(--ksp-navy)' }}
                >
                  UNDER INVESTIGATION
                </span>
              )}
            </span>
          )},
          { header: 'Bank',       render: (r) => r.bank_name ?? '—' },
          { header: 'Amount',     render: (r) => formatINR(r.amount_lien_marked), align: 'right' },
          { header: 'Layer',      render: (r) => r.layer ?? '—', align: 'right' },
        ]}
      />
      <CaseSubTable
        title={`Petitions (${c.petitions.length})`}
        empty="No petitions recorded."
        rows={c.petitions}
        columns={[
          { header: 'Petition No', render: (r) => r.petition_no ?? '—' },
          { header: 'Nature',      render: (r) => r.nature ?? '—' },
          { header: 'Type',        render: (r) => r.petition_type ?? '—' },
          { header: 'Amount',      render: (r) => formatINR(r.amount), align: 'right' },
        ]}
      />
      <CaseSubTable
        title={`Refunds (${c.refunds.length})`}
        empty="No refunds recorded."
        rows={c.refunds}
        columns={[
          { header: 'Victim', render: (r) => r.victim_name ?? '—' },
          { header: 'Amount', render: (r) => formatINR(r.amount), align: 'right' },
          { header: 'Refunded?', render: (r) => r.refunded ?? '—' },
        ]}
      />
    </div>
  );
}

function CaseSubTable<R>({ title, empty, rows, columns, highlightRow }: {
  title: string;
  empty: string;
  rows: R[];
  columns: { header: string; render: (r: R) => ReactNode; align?: 'left' | 'right' }[];
  /** When provided, rows matching the predicate get a yellow background +
   *  left border. Used to mark the account currently under investigation
   *  in the case-detail view. */
  highlightRow?: (r: R) => boolean;
}) {
  return (
    <div className="rounded-xl border" style={{ borderColor: 'rgba(0,0,0,0.06)' }}>
      <div className="px-4 py-2 text-xs uppercase font-bold" style={{ background: '#fafafa', color: 'var(--ksp-navy)' }}>
        {title}
      </div>
      {rows.length === 0 ? (
        <div className="px-4 py-3 text-sm opacity-60">{empty}</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead style={{ background: '#fff7d6', color: 'var(--ksp-navy)' }}>
              <tr>
                {columns.map((c, i) => (
                  <th key={i} className={`px-3 py-2 text-xs uppercase font-bold ${c.align === 'right' ? 'text-right' : ''}`}>
                    {c.header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => {
                const hi = highlightRow?.(r) ?? false;
                return (
                  <tr
                    key={ri}
                    className="border-t"
                    style={{
                      borderColor: 'rgba(0,0,0,0.06)',
                      background: hi ? '#fff3b0' : undefined,
                      boxShadow: hi ? 'inset 4px 0 0 var(--ksp-red)' : undefined,
                    }}
                  >
                    {columns.map((c, ci) => (
                      <td key={ci} className={`px-3 py-2 ${c.align === 'right' ? 'text-right' : ''}`} style={{ color: 'var(--ksp-navy)', fontWeight: hi ? 700 : undefined }}>
                        {c.render(r)}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function MuleAccountBanksCard({ rows }: { rows: BankConcentration[] }) {
  return (
    <div className="rounded-2xl p-5" style={cardStyle}>
      <h3 className="text-sm font-bold mb-1 flex items-center gap-2" style={{ color: 'var(--ksp-navy)' }}>
        <Landmark className="w-4 h-4" /> Mule Account Banks (Source)
      </h3>
      <p className="text-xs mb-4 opacity-60">Banks where the mule accounts are HELD — top of the list = banks hosting the most frozen accounts. Priority for freeze-coordination liaison. Bar = number of frozen accounts at that bank; tooltip shows total lien-marked amount.</p>
      {rows.length === 0 ? (
        <div className="py-10 text-center text-sm opacity-60">No frozen-account data indexed yet.</div>
      ) : (
        <ResponsiveContainer width="100%" height={Math.max(220, rows.length * 24)}>
          <BarChart data={rows} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
            <YAxis type="category" dataKey="bank" width={140} tick={{ fontSize: 9 }} />
            <Tooltip formatter={(val, _name, p) => [`${val} frozen accounts · ${formatINR(p?.payload?.total_amount ?? 0)}`, 'Volume']} />
            <Bar dataKey="transaction_count" fill="#0b2c4a" name="Frozen Accounts" />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

function DestinationBanksCard({ rows }: { rows: BankConcentration[] }) {
  return (
    <div className="rounded-2xl p-5" style={cardStyle}>
      <h3 className="text-sm font-bold mb-1 flex items-center gap-2" style={{ color: 'var(--ksp-navy)' }}>
        <Landmark className="w-4 h-4" /> Destination Banks (Downstream / Layer&nbsp;&gt;&nbsp;1)
      </h3>
      <p className="text-xs mb-4 opacity-60">Banks holding frozen accounts that sit DOWNSTREAM in the laundering chain — i.e. where money was moved AFTER the first mule receiver. Priority for follow-on freezes. Bar = number of layer-2+ frozen accounts at that bank; tooltip shows total lien-marked amount.</p>
      {rows.length === 0 ? (
        <div className="py-10 text-center text-sm opacity-60">No downstream (layer&nbsp;&gt;&nbsp;1) accounts recorded yet. Either money trails haven't progressed past layer 1, or the layer field isn't being set on lien entries.</div>
      ) : (
        <ResponsiveContainer width="100%" height={Math.max(220, rows.length * 24)}>
          <BarChart data={rows} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
            <YAxis type="category" dataKey="bank" width={160} tick={{ fontSize: 9 }} />
            <Tooltip formatter={(val, _name, p) => [`${val} downstream accounts · ${formatINR(p?.payload?.total_amount ?? 0)}`, 'Volume']} />
            <Bar dataKey="transaction_count" fill="#b45309" name="Downstream Accounts" />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

function AtmHotspotsCard({ rows }: { rows: AtmHotspot[] }) {
  return (
    <div className="rounded-2xl p-5" style={cardStyle}>
      <h3 className="text-sm font-bold mb-1 flex items-center gap-2" style={{ color: 'var(--ksp-navy)' }}>
        <MapPin className="w-4 h-4" /> ATM Cash-Out Hotspots
      </h3>
      <p className="text-xs mb-4 opacity-60">Locations that appear most often in ATM withdrawals — surveillance candidates.</p>
      {rows.length === 0 ? (
        <div className="py-10 text-center text-sm opacity-60">No ATM withdrawal data indexed yet.</div>
      ) : (
        <ResponsiveContainer width="100%" height={Math.max(220, rows.length * 24)}>
          <BarChart data={rows} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" tick={{ fontSize: 11 }} />
            <YAxis type="category" dataKey="location" width={160} tick={{ fontSize: 9 }} />
            <Tooltip formatter={(val, _name, p) => [`${val} withdrawals · ${formatINR(p?.payload?.total_amount ?? 0)}`, 'Volume']} />
            <Bar dataKey="withdrawal_count" fill="#b10000" name="Withdrawals" />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

function LayerDistributionCard({ rows, date }: { rows: LayerBucket[]; date: string }) {
  const [selectedLayer, setSelectedLayer] = useState<number | null>(null);
  const [accounts, setAccounts] = useState<LienAccountAtLayer[]>([]);
  const [accountsLoading, setAccountsLoading] = useState(false);
  const [accountsError, setAccountsError] = useState<string | null>(null);

  const [selectedAccount, setSelectedAccount] = useState<{ case_id: string; account_no: string; fir_label: string } | null>(null);
  const [caseDetail, setCaseDetail] = useState<CaseDetailFull | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Reset every drill state when the parent date changes (counts may have shifted).
  useEffect(() => {
    setSelectedLayer(null); setAccounts([]); setAccountsError(null);
    setSelectedAccount(null); setCaseDetail(null); setDetailError(null);
  }, [date]);

  useEffect(() => {
    if (selectedLayer == null) return;
    setAccountsLoading(true); setAccountsError(null);
    getAccountsAtLayer(date, selectedLayer)
      .then(setAccounts)
      .catch((e: Error) => setAccountsError(e?.message ?? 'Failed to load accounts at this layer'))
      .finally(() => setAccountsLoading(false));
  }, [date, selectedLayer]);

  useEffect(() => {
    if (!selectedAccount) return;
    setDetailLoading(true); setDetailError(null);
    getCaseDetail(selectedAccount.case_id)
      .then(setCaseDetail)
      .catch((e: Error) => setDetailError(e?.message ?? 'Failed to load case money trail'))
      .finally(() => setDetailLoading(false));
  }, [selectedAccount]);

  const data = rows.map(r => ({ layer: `L${r.layer}`, layerNum: r.layer, count: r.count }));

  const level = selectedAccount ? 3 : selectedLayer != null ? 2 : 1;
  const title = level === 3
    ? <>Money Trail — <span className="font-mono">{selectedAccount!.fir_label}</span></>
    : level === 2
      ? <>Frozen Accounts at Layer {selectedLayer}</>
      : 'Money-Trail Layer Distribution';
  const hint = level === 3
    ? 'All frozen accounts on this case, ordered by layer. The account you came from is highlighted.'
    : level === 2
      ? 'Click any account number to see its case\'s full money trail across all layers.'
      : 'Count of frozen accounts by layer (depth in the money trail). Click any bar to drill in.';
  const backLabel = level === 3 ? '← Back to Layer Accounts' : '← Back to Distribution';
  const handleBack = () => {
    if (level === 3) { setSelectedAccount(null); setCaseDetail(null); setDetailError(null); }
    else if (level === 2) { setSelectedLayer(null); setAccounts([]); setAccountsError(null); }
  };

  return (
    <div className="rounded-2xl p-5" style={cardStyle}>
      <div className="flex items-start justify-between gap-3 mb-1">
        <div>
          <h3 className="text-sm font-bold flex items-center gap-2" style={{ color: 'var(--ksp-navy)' }}>
            <Layers className="w-4 h-4" /> {title}
          </h3>
          <p className="text-xs mt-1 opacity-60">{hint}</p>
        </div>
        {level > 1 && (
          <button
            onClick={handleBack}
            className="text-xs font-bold px-3 py-1 rounded-lg whitespace-nowrap"
            style={{ background: 'var(--ksp-yellow)', color: 'var(--ksp-navy)' }}
          >
            {backLabel}
          </button>
        )}
      </div>

      {/* Level 3 — money trail (all lien accounts for the case) */}
      {level === 3 && (
        detailLoading ? (
          <div className="py-8 text-center text-sm" style={{ color: 'var(--ksp-navy)' }}>Loading money trail…</div>
        ) : detailError ? (
          <div className="py-8 text-center text-sm" style={{ color: 'var(--ksp-red)' }}>{detailError}</div>
        ) : caseDetail ? (
          <MoneyTrailView c={caseDetail} focusAccountNo={selectedAccount!.account_no} />
        ) : null
      )}

      {/* Level 2 — accounts at the selected layer */}
      {level === 2 && (
        accountsLoading ? (
          <div className="py-8 text-center text-sm" style={{ color: 'var(--ksp-navy)' }}>Loading accounts…</div>
        ) : accountsError ? (
          <div className="py-8 text-center text-sm" style={{ color: 'var(--ksp-red)' }}>{accountsError}</div>
        ) : accounts.length === 0 ? (
          <div className="py-8 text-center text-sm opacity-60">No accounts at this layer in your scope.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}>
                <tr>
                  <th className="px-4 py-2 text-xs uppercase font-bold">Account No</th>
                  <th className="px-4 py-2 text-xs uppercase font-bold">Bank</th>
                  <th className="px-4 py-2 text-xs uppercase font-bold text-right">Amount</th>
                  <th className="px-4 py-2 text-xs uppercase font-bold">FIR / Petition</th>
                  <th className="px-4 py-2 text-xs uppercase font-bold">District</th>
                  <th className="px-4 py-2 text-xs uppercase font-bold">PS</th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((a) => {
                  const firLabel = a.fir_no ?? a.petition_no ?? '(no number)';
                  return (
                    <tr key={a.lien_id} className="border-t hover:bg-[#fff3b0]/30" style={{ borderColor: 'rgba(0,0,0,0.06)' }}>
                      <td className="px-4 py-2 font-mono text-xs">
                        <button
                          onClick={() => setSelectedAccount({ case_id: a.case_id, account_no: a.account_no, fir_label: firLabel })}
                          style={{ color: 'var(--ksp-navy)', textDecoration: 'underline', background: 'none', border: 'none', padding: 0, cursor: 'pointer', font: 'inherit' }}
                          title="View this case's full money trail"
                        >
                          {a.account_no || '—'}
                        </button>
                      </td>
                      <td className="px-4 py-2 opacity-80">{a.bank_name ?? '—'}</td>
                      <td className="px-4 py-2 text-right font-bold" style={{ color: 'var(--ksp-navy)' }}>{formatINR(a.amount_lien_marked)}</td>
                      <td className="px-4 py-2 font-semibold" style={{ color: 'var(--ksp-navy)' }}>{firLabel}</td>
                      <td className="px-4 py-2 opacity-80">{a.district || '—'}</td>
                      <td className="px-4 py-2 opacity-80">{a.ps_name ?? '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* Level 1 — histogram */}
      {level === 1 && (
        data.length === 0 ? (
          <div className="py-10 text-center text-sm opacity-60">No layer data yet.</div>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="layer" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Bar
                dataKey="count"
                fill="#0a5c2a"
                name="Accounts"
                cursor="pointer"
                onClick={(p: unknown) => {
                  // Recharts may wrap row in `.payload`, may not — handle both.
                  const r = p as { payload?: { layerNum?: number }; layerNum?: number };
                  const row = r?.payload ?? r;
                  if (row && typeof row.layerNum === 'number') setSelectedLayer(row.layerNum);
                }}
              />
            </BarChart>
          </ResponsiveContainer>
        )
      )}
    </div>
  );
}

// Lightweight money-trail view — reuses the case detail fetch but only
// renders the lien-accounts table, sorted by layer, with the entry-point
// account highlighted.
function MoneyTrailView({ c, focusAccountNo }: { c: CaseDetailFull; focusAccountNo: string }) {
  const sorted = [...c.lien_accounts].sort((a, b) => (a.layer ?? 999) - (b.layer ?? 999));
  const totalAmount = sorted.reduce((s, r) => s + (r.amount_lien_marked ?? 0), 0);
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <KV label="District" value={c.district || '—'} />
        <KV label="Police Station" value={c.ps_name ?? '—'} />
        <KV label="Registration Date" value={c.registration_date ?? '—'} />
        <KV label="Total Lien Across Layers" value={<span style={{ color: 'var(--ksp-navy)' }}>{formatINR(totalAmount)}</span>} />
      </div>
      <CaseSubTable
        title={`Lien Accounts (${sorted.length})`}
        empty="No lien accounts on this case."
        rows={sorted}
        highlightRow={(r) => r.account_no === focusAccountNo}
        columns={[
          { header: 'Layer',      render: (r) => <span className="font-bold">L{r.layer ?? '?'}</span> },
          { header: 'Account No', render: (r) => (
            <span className="font-mono text-xs">
              {r.account_no || '—'}
              {r.account_no === focusAccountNo && (
                <span
                  className="ml-2 text-[10px] font-bold px-1.5 py-0.5 rounded"
                  style={{ background: 'var(--ksp-yellow)', color: 'var(--ksp-navy)' }}
                >
                  ENTRY POINT
                </span>
              )}
            </span>
          ) },
          { header: 'Bank',       render: (r) => r.bank_name ?? '—' },
          { header: 'Amount',     render: (r) => formatINR(r.amount_lien_marked), align: 'right' },
        ]}
      />
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// Disposal & Trial tab — DSR-driven long-range performance
// ──────────────────────────────────────────────────────────────────────────

function DisposalTab({ date }: { date: string }) {
  const [disposal, setDisposal] = useState<DisposalSummary | null>(null);
  const [trial, setTrial] = useState<TrialSummary | null>(null);
  const [pending, setPending] = useState<PendingByYearRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      getDisposalSummary(date),
      getTrialSummary(date),
      getPendingByYear(date),
    ]).then(([d, t, p]) => {
      setDisposal(d.status === 'fulfilled' ? d.value : null);
      setTrial(t.status === 'fulfilled' ? t.value : null);
      setPending(p.status === 'fulfilled' ? p.value : []);
    }).finally(() => setLoading(false));
  }, [date]);

  if (loading) {
    return <div className="text-center py-16 font-semibold" style={{ color: 'var(--ksp-navy)' }}>Loading disposal data...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <DisposalCard data={disposal} />
        <TrialCard data={trial} />
      </div>
      <PendingByYearCard rows={pending} />
    </div>
  );
}

const DISPOSAL_COLORS = ['#0a5c2a', '#0b2c4a', '#b10000', '#ffd400'];
const TRIAL_COLORS = ['#0a5c2a', '#6b7280', '#b10000', '#9ca3af', '#ffd400', '#0b2c4a'];

function DisposalCard({ data }: { data: DisposalSummary | null }) {
  const slices = [
    { name: 'Detected / Chargesheeted', value: data?.detected ?? 0 },
    { name: 'Transferred',              value: data?.transferred ?? 0 },
    { name: 'False',                    value: data?.false_cases ?? 0 },
    { name: 'Undetected',               value: data?.undetected ?? 0 },
  ];
  const total = slices.reduce((s, x) => s + x.value, 0);
  const detectionRate = total > 0 ? ((data?.detected ?? 0) / total) * 100 : 0;

  return (
    <div className="rounded-2xl p-5" style={cardStyle}>
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-sm font-bold flex items-center gap-2" style={{ color: 'var(--ksp-navy)' }}>
          <Gavel className="w-4 h-4" /> Case Disposal
        </h3>
        <span className="text-xs font-bold px-2 py-1 rounded" style={{ background: 'var(--ksp-yellow)', color: 'var(--ksp-navy)' }}>
          Detection {detectionRate.toFixed(1)}%
        </span>
      </div>
      <p className="text-xs mb-4 opacity-60">Aggregated from each PS's latest DSR (cases disposed since 1 Jan 2026).</p>
      {total === 0 ? (
        <div className="py-10 text-center text-sm opacity-60">No DSR entries with disposal data yet.</div>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <PieChart>
            <Pie data={slices} cx="50%" cy="50%" outerRadius={80} dataKey="value"
                 label={({ name, value }) => `${name}: ${formatNumber(value)}`}>
              {slices.map((_, i) => <Cell key={i} fill={DISPOSAL_COLORS[i]} />)}
            </Pie>
            <Tooltip formatter={(val) => formatNumber(Number(val) || 0)} />
          </PieChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

function TrialCard({ data }: { data: TrialSummary | null }) {
  const rows = [
    { name: 'Convicted',   value: data?.convicted   ?? 0 },
    { name: 'Discharged',  value: data?.discharged  ?? 0 },
    { name: 'Acquitted',   value: data?.acquitted   ?? 0 },
    { name: 'Abated',      value: data?.abated      ?? 0 },
    { name: 'Compounded',  value: data?.compounded  ?? 0 },
    { name: 'Under Trial', value: data?.under_trial ?? 0 },
  ];
  const total = rows.reduce((s, x) => s + x.value, 0);
  const closed = (data?.convicted ?? 0) + (data?.acquitted ?? 0) + (data?.compounded ?? 0) + (data?.abated ?? 0) + (data?.discharged ?? 0);
  const convictionRate = closed > 0 ? ((data?.convicted ?? 0) / closed) * 100 : 0;

  return (
    <div className="rounded-2xl p-5" style={cardStyle}>
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-sm font-bold flex items-center gap-2" style={{ color: 'var(--ksp-navy)' }}>
          <Gavel className="w-4 h-4" /> Trial Outcomes
        </h3>
        <span className="text-xs font-bold px-2 py-1 rounded" style={{ background: 'var(--ksp-yellow)', color: 'var(--ksp-navy)' }}>
          Conviction {convictionRate.toFixed(1)}%
        </span>
      </div>
      <p className="text-xs mb-4 opacity-60">From each PS's latest DSR (trials concluded since 1 Jan 2026). Conviction rate is convicted ÷ all closed trials (excluding Under Trial).</p>
      {total === 0 ? (
        <div className="py-10 text-center text-sm opacity-60">No DSR entries with trial data yet.</div>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={rows}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" tick={{ fontSize: 9 }} interval={0} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip formatter={(val) => formatNumber(Number(val) || 0)} />
            <Bar dataKey="value" name="Cases">
              {rows.map((_, i) => <Cell key={i} fill={TRIAL_COLORS[i]} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

const YEAR_KEYS: (keyof PendingByYearRow)[] = ['y2021', 'y2022', 'y2023', 'y2024', 'y2025', 'y2026'];
const YEAR_LABELS = ['2021', '2022', '2023', '2024', '2025', '2026'];
const YEAR_COLORS = ['#b10000', '#d97706', '#ffd400', '#0a5c2a', '#0b2c4a', '#6b21a8'];

function PendingByYearCard({ rows }: { rows: PendingByYearRow[] }) {
  // Slice to top 20 to keep the chart readable on a 44-PS dataset.
  const top = rows.slice(0, 20);
  const totalAcrossAll = rows.reduce((s, r) =>
    s + r.y2021 + r.y2022 + r.y2023 + r.y2024 + r.y2025 + r.y2026, 0);

  return (
    <div className="rounded-2xl p-5" style={cardStyle}>
      <h3 className="text-sm font-bold mb-1" style={{ color: 'var(--ksp-navy)' }}>Pending UI Cases by Year</h3>
      <p className="text-xs mb-4 opacity-60">
        Per-PS backlog from the latest DSR, stacked by registration year. Heaviest backlog first.
        State total: <b>{formatNumber(totalAcrossAll)}</b> pending cases.
      </p>
      {top.length === 0 ? (
        <div className="py-10 text-center text-sm opacity-60">No DSR entries with pending-case data yet.</div>
      ) : (
        <ResponsiveContainer width="100%" height={Math.max(280, top.length * 24)}>
          <BarChart data={top} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" tick={{ fontSize: 11 }} />
            <YAxis type="category" dataKey="unit_name" width={150} tick={{ fontSize: 9 }} />
            <Tooltip formatter={(val) => formatNumber(Number(val) || 0)} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            {YEAR_KEYS.map((k, i) => (
              <Bar key={k} dataKey={k} stackId="pending" fill={YEAR_COLORS[i]} name={YEAR_LABELS[i]} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

function BankSlaCard({ rows }: { rows: BankSlaRow[] }) {
  return (
    <div className="rounded-2xl p-5" style={cardStyle}>
      <h3 className="text-sm font-bold mb-1 flex items-center gap-2" style={{ color: 'var(--ksp-navy)' }}>
        <Landmark className="w-4 h-4" /> Bank Action SLA
      </h3>
      <p className="text-xs mb-4 opacity-60">
        Avg days from transaction date to bank action, per bank (last 180 days).
        Slowest first. Banks with fewer than 5 parseable transactions are excluded.
        Date fields are bank-supplied strings; rows in unrecognised date formats are dropped.
      </p>
      {rows.length === 0 ? (
        <div className="py-10 text-center text-sm opacity-60">
          No parseable bank-action data yet. Verify Excel date formats in <code>money_transfers</code>.
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={Math.max(240, rows.length * 28)}>
          <BarChart data={rows} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" tick={{ fontSize: 11 }} label={{ value: 'days', position: 'insideBottom', fontSize: 10 }} />
            <YAxis type="category" dataKey="bank" width={160} tick={{ fontSize: 9 }} />
            <Tooltip formatter={(val, _name, p) => [`${val} days (n=${p?.payload?.count})`, 'Avg SLA']} />
            <Bar dataKey="avg_days" fill="#b10000" name="Avg days" />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
