import { useEffect, useMemo, useState } from 'react';
import { BarChart3, Trophy } from 'lucide-react';
import { toast } from 'sonner';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { getPortalsSummary, getPortalsComparison } from '../lib/api/dashboard';
import { formatNumber, todayISO } from '../lib/utils/format';
import { PORTAL_TABS } from '../lib/utils/portals-tabs';
import type { PortalsDsrKpiSummary, PortalsDsrPsComparison } from '../types';

/** Portals DSR admin dashboard — grand totals per portal + Top-10 PS
 *  chart + per-PS table. Multiple entries per (unit, ps, date) are
 *  aggregated by the backend (SUM). Drafts excluded. */

// "24 Jul" — short header label for the Yesterday column. Server
// computes yesterday_count as today−1 using its own clock; the label
// tracks the user's local date. Same tz in production (IST), so the
// label matches the data.
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

function KpiCard({
  label, value, accent, sub,
}: { label: string; value: string; accent: string; sub?: string }) {
  return (
    <div className="rounded-2xl p-4"
      style={{ ...cardStyle, borderLeft: `6px solid ${accent}` }}>
      <p className="text-[11px] uppercase tracking-wide font-bold mb-1" style={{ color: accent }}>
        {label}
      </p>
      <p className="text-2xl font-bold" style={{ color: 'var(--ksp-navy)' }}>{value}</p>
      {sub && <p className="text-xs mt-1 opacity-60">{sub}</p>}
    </div>
  );
}

function PortalTile({
  label, accent, total, metrics,
}: {
  label: string; accent: string; total: number;
  metrics: Array<{ label: string; value: number }>;
}) {
  return (
    <div className="rounded-2xl overflow-hidden" style={cardStyle}>
      <div className="px-4 py-2 flex items-center justify-between"
        style={{ background: accent, color: '#fff' }}>
        <span className="text-sm font-bold">{label}</span>
        <span className="text-sm font-mono">{formatNumber(total)}</span>
      </div>
      <div className="px-4 py-3 space-y-1.5">
        {metrics.map((m) => (
          <div key={m.label} className="flex justify-between text-xs">
            <span className="opacity-70">{m.label}</span>
            <span className="font-mono font-semibold">{formatNumber(m.value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function PortalsDsrDashboardPage() {
  // Default to last 30 days.
  const [toDate, setToDate] = useState(todayISO());
  const [fromDate, setFromDate] = useState(() => {
    const d = new Date(todayISO());
    d.setDate(d.getDate() - 29);
    return d.toISOString().split('T')[0];
  });
  const [summary, setSummary] = useState<PortalsDsrKpiSummary | null>(null);
  const [rows, setRows] = useState<PortalsDsrPsComparison[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      getPortalsSummary(fromDate, toDate),
      getPortalsComparison(fromDate, toDate),
    ]).then(([s, u]) => {
      if (s.status === 'fulfilled') setSummary(s.value);
      else { setSummary(null); toast.error(`Summary: ${(s as any).reason?.message ?? 'failed'}`); }
      if (u.status === 'fulfilled') setRows(u.value);
      else { setRows([]); toast.error(`Per-PS: ${(u as any).reason?.message ?? 'failed'}`); }
    }).finally(() => setLoading(false));
  }, [fromDate, toDate]);

  const top10 = useMemo(() => rows.slice(0, 10), [rows]);
  const yestLabel = yesterdayShortLabel();

  return (
    <div>
      {/* Header + date-range picker */}
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div>
          <h1 className="text-[22px] font-bold mb-1 flex items-center gap-2" style={{ color: 'var(--ksp-navy)' }}>
            <BarChart3 className="w-5 h-5" /> Portals DSR Dashboard
          </h1>
          <p className="text-sm font-medium" style={{ color: 'var(--ksp-red)' }}>
            Submitted-entry totals across all 8 portals for the selected window. Drafts excluded.
          </p>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <label className="flex items-center gap-2">
            <span className="font-semibold" style={{ color: 'var(--ksp-navy)' }}>From:</span>
            <input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)}
              className="px-3 py-1.5 rounded-lg bg-white"
              style={{ border: '2px solid var(--ksp-navy)' }} />
          </label>
          <label className="flex items-center gap-2">
            <span className="font-semibold" style={{ color: 'var(--ksp-navy)' }}>To:</span>
            <input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)}
              className="px-3 py-1.5 rounded-lg bg-white"
              style={{ border: '2px solid var(--ksp-navy)' }} />
          </label>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-16 font-semibold" style={{ color: 'var(--ksp-navy)' }}>Loading dashboard...</div>
      ) : (
        <div className="space-y-6">
          {/* Top-line KPIs */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <KpiCard label="Submitted Entries"    value={formatNumber(summary?.total_entries ?? 0)}
              accent="#0b2c4a" sub="draft entries excluded" />
            <KpiCard label="PSes Reporting"       value={`${summary?.units_submitted ?? 0} / ${summary?.units_total ?? 0}`}
              accent="#0a6b28" sub="reporting coverage" />
            <KpiCard label="Total Counters Logged" value={formatNumber(
              PORTAL_TABS.reduce((s, t) =>
                s + t.metrics.reduce((ms, m) => ms + (summary?.[m.key] ?? 0), 0), 0)
            )} accent="#6a1b9a" sub="sum across all 25 metrics" />
            <KpiCard label="Date Range" value={`${fromDate} → ${toDate}`}
              accent="#c67c1d" sub="inclusive" />
          </div>

          {/* Per-portal tiles — 8 coloured cards showing that portal's own metrics + total. */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {PORTAL_TABS.map((t) => {
              const metrics = t.metrics.map((m) => ({
                label: m.label,
                value: summary?.[m.key] ?? 0,
              }));
              const total = metrics.reduce((s, m) => s + m.value, 0);
              return (
                <PortalTile key={t.key} label={t.label} accent={t.accent}
                  total={total} metrics={metrics} />
              );
            })}
          </div>

          {/* Top-10 PS by entries */}
          <div className="rounded-2xl overflow-hidden" style={cardStyle}>
            <div className="px-5 py-3" style={{ borderTop: '4px solid #0b2c4a' }}>
              <h3 className="text-sm font-bold flex items-center gap-2" style={{ color: 'var(--ksp-navy)' }}>
                <Trophy className="w-4 h-4" style={{ color: '#c67c1d' }} />
                Top {Math.min(10, top10.length)} Police Stations by Submissions
              </h3>
              <p className="text-xs opacity-60 mt-0.5">Bars show entry count; hover for grand total.</p>
            </div>
            <div className="px-5 pb-5">
              {top10.length === 0 ? (
                <div className="py-10 text-center italic opacity-60 text-sm">No submitted entries in this window.</div>
              ) : (
                <div style={{ width: '100%', height: 40 + top10.length * 34 }}>
                  <ResponsiveContainer>
                    <BarChart data={top10} layout="vertical"
                              margin={{ top: 6, right: 30, left: 10, bottom: 6 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#eee" horizontal={false} />
                      <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
                      <YAxis type="category" dataKey="ps_name" tick={{ fontSize: 11 }} width={150} />
                      <Tooltip formatter={(v, key) => [formatNumber(Number(v ?? 0)), String(key)]} />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <Bar dataKey="entries" name="Submissions" fill="#0b2c4a" />
                      <Bar dataKey="total"   name="Grand Total" fill="#c67c1d" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </div>

          {/* Per-PS table — all rows */}
          <div className="rounded-2xl overflow-hidden" style={cardStyle}>
            <div className="px-5 py-3" style={{ borderTop: '4px solid #0b2c4a' }}>
              <h3 className="text-sm font-bold" style={{ color: 'var(--ksp-navy)' }}>Per-PS Portals DSR Comparison</h3>
              <p className="text-xs opacity-60 mt-0.5">Descending by submission count.</p>
            </div>
            <table className="w-full text-sm">
              <thead style={{ background: '#f5f5f7' }}>
                <tr>
                  <th className="px-3 py-2 text-left">#</th>
                  <th className="px-3 py-2 text-left">District</th>
                  <th className="px-3 py-2 text-left">Police Station</th>
                  <th className="px-3 py-2 text-right"
                    title={`Submissions with report_date = ${yestLabel}`}>
                    Yesterday ({yestLabel})
                  </th>
                  <th className="px-3 py-2 text-right">Entries</th>
                  <th className="px-3 py-2 text-right">Grand Total</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-3 py-8 text-center italic opacity-60">
                      No submitted entries in this date range.
                    </td>
                  </tr>
                )}
                {rows.map((r, i) => (
                  <tr key={`${r.unit_id}-${r.ps_id}`} className="border-t border-slate-100">
                    <td className="px-3 py-2 text-xs font-mono opacity-70">{i + 1}</td>
                    <td className="px-3 py-2">{r.unit_name}</td>
                    <td className="px-3 py-2 font-semibold" style={{ color: 'var(--ksp-navy)' }}>
                      {r.ps_name}
                    </td>
                    <td className="px-3 py-2 text-right font-mono font-bold"
                      style={{ color: r.yesterday_count === 0 ? 'rgba(0,0,0,0.35)' : '#0a6b28' }}>
                      {formatNumber(r.yesterday_count)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono">{formatNumber(r.entries)}</td>
                    <td className="px-3 py-2 text-right font-mono font-bold">{formatNumber(r.total)}</td>
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
