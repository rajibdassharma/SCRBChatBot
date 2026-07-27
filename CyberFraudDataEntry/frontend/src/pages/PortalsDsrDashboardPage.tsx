import { useEffect, useMemo, useState } from 'react';
import { BarChart3, Trophy } from 'lucide-react';
import { toast } from 'sonner';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { getPortalsSummary, getPortalsComparison } from '../lib/api/dashboard';
import { formatNumber, todayISO } from '../lib/utils/format';
import { PORTAL_TABS } from '../lib/utils/portals-tabs';
import type {
  PortalsDsrKpiSummary, PortalsDsrPsComparison, PortalsDsrMetrics,
} from '../types';

/** Portals DSR admin dashboard — one day at a time (2026-07-27
 *  reshape). Every metric is a Daily Status Report counter:
 *
 *    * Pending fields are point-in-time snapshots — the LATEST
 *      shift-batch on the date wins (SUM would double-count).
 *    * Everything else is summed across the day's batches.
 *
 *  The per-PS comparison table is filtered to a single portal at a
 *  time via a dropdown, and every active PS appears whether or not
 *  it submitted (zeros surface silent stations). */

function yesterdayISO(): string {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return d.toISOString().slice(0, 10);
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
    <div className="rounded-2xl p-4 flex flex-col"
      style={{ ...cardStyle, borderLeft: `6px solid ${accent}` }}>
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
  // Single DSR date; defaults to yesterday so the morning-after
  // review lands on the previous day's numbers without fiddling.
  const [date, setDate] = useState(yesterdayISO());
  const [portalKey, setPortalKey] = useState<string>(PORTAL_TABS[0].key);
  const [summary, setSummary] = useState<PortalsDsrKpiSummary | null>(null);
  const [rows, setRows] = useState<PortalsDsrPsComparison[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      getPortalsSummary(date),
      getPortalsComparison(date),
    ]).then(([s, u]) => {
      if (s.status === 'fulfilled') setSummary(s.value);
      else { setSummary(null); toast.error(`Summary: ${(s as any).reason?.message ?? 'failed'}`); }
      if (u.status === 'fulfilled') setRows(u.value);
      else { setRows([]); toast.error(`Per-PS: ${(u as any).reason?.message ?? 'failed'}`); }
    }).finally(() => setLoading(false));
  }, [date]);

  const selectedPortal = useMemo(
    () => PORTAL_TABS.find((t) => t.key === portalKey) ?? PORTAL_TABS[0],
    [portalKey],
  );

  // Per-portal top-10 — same portal dropdown drives both the chart
  // and the table. A PS's portal activity = sum of every metric in
  // that portal (pending included; matches how the tile total works
  // and keeps the chart intuitive next to the numeric tiles).
  const top10 = useMemo(() => {
    const withPortalTotal = rows.map((r) => {
      const portalTotal = selectedPortal.metrics.reduce(
        (s, m) => s + ((r[m.key as keyof PortalsDsrMetrics] as number) || 0),
        0,
      );
      return { ...r, portal_total: portalTotal };
    });
    return withPortalTotal
      .filter((r) => r.portal_total > 0)
      .sort((a, b) => b.portal_total - a.portal_total || a.ps_name.localeCompare(b.ps_name))
      .slice(0, 10);
  }, [rows, selectedPortal]);

  return (
    <div>
      {/* Header + single-date picker */}
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div>
          <h1 className="text-[22px] font-bold mb-1 flex items-center gap-2" style={{ color: 'var(--ksp-navy)' }}>
            <BarChart3 className="w-5 h-5" /> Portals DSR Dashboard
          </h1>
          <p className="text-sm font-medium" style={{ color: 'var(--ksp-red)' }}>
            Daily Status Report — one date at a time. Pending values are the LATEST snapshot on the day; other counters are summed across shift-batches. Drafts excluded.
          </p>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <label className="flex items-center gap-2">
            <span className="font-semibold" style={{ color: 'var(--ksp-navy)' }}>Date:</span>
            <input type="date" value={date} max={todayISO()}
              onChange={(e) => setDate(e.target.value)}
              className="px-3 py-1.5 rounded-lg bg-white"
              style={{ border: '2px solid var(--ksp-navy)' }} />
          </label>
          <button type="button" onClick={() => setDate(yesterdayISO())}
            className="px-3 py-1.5 text-xs font-semibold rounded-lg"
            style={{ background: 'rgba(11,44,74,0.06)', color: 'var(--ksp-navy)' }}>
            Yesterday
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-16 font-semibold" style={{ color: 'var(--ksp-navy)' }}>Loading dashboard...</div>
      ) : (
        <div className="space-y-6">
          {/* Two KPI cards — Submitted Entries + Total Counters
               Logged were removed on the 2026-07-27 reshape. */}
          <div className="grid grid-cols-2 gap-4 max-w-xl">
            <KpiCard label="PSes Reporting"
              value={`${summary?.units_submitted ?? 0} / ${summary?.units_total ?? 0}`}
              accent="#0a6b28" sub="submitted at least one entry" />
            <KpiCard label="DSR Date"
              value={date}
              accent="#c67c1d" sub="single-day snapshot" />
          </div>

          {/* Per-portal tiles — 8 coloured cards showing that portal's own metrics + total.
               Pending values inside these tiles are latest-snapshot; others are summed. */}
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

          {/* Top-10 PS — ranked by the SELECTED portal's activity
               (same dropdown as the table below drives this too). */}
          <div className="rounded-2xl overflow-hidden" style={cardStyle}>
            <div className="px-5 py-3 flex flex-wrap items-center justify-between gap-3"
                 style={{ borderTop: '4px solid #0b2c4a' }}>
              <div>
                <h3 className="text-sm font-bold flex items-center gap-2" style={{ color: 'var(--ksp-navy)' }}>
                  <Trophy className="w-4 h-4" style={{ color: '#c67c1d' }} />
                  Top {Math.min(10, top10.length)} Police Stations — {selectedPortal.label}
                </h3>
                <p className="text-xs opacity-60 mt-0.5">
                  Ranked by total {selectedPortal.label} activity for the date. PSes with zero {selectedPortal.label} counters excluded.
                </p>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <span className="font-semibold" style={{ color: 'var(--ksp-navy)' }}>Portal:</span>
                <select value={portalKey}
                  onChange={(e) => setPortalKey(e.target.value)}
                  className="px-3 py-1.5 rounded-lg text-sm font-semibold"
                  style={{
                    border: '2px solid var(--ksp-navy)',
                    background: selectedPortal.accent,
                    color: '#fff',
                  }}>
                  {PORTAL_TABS.map((t) => (
                    <option key={t.key} value={t.key} style={{ background: '#fff', color: '#000' }}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="px-5 pb-5">
              {top10.length === 0 ? (
                <div className="py-10 text-center italic opacity-60 text-sm">
                  No {selectedPortal.label} activity on this date.
                </div>
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
                      <Bar dataKey="portal_total" name={`${selectedPortal.label} total`} fill={selectedPortal.accent} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </div>

          {/* Per-PS comparison table — filtered to ONE portal at a time
               via the dropdown. Shows every active PS (zeros for
               silent stations). */}
          <div className="rounded-2xl overflow-hidden" style={cardStyle}>
            <div className="px-5 py-3 flex flex-wrap items-center justify-between gap-3"
                 style={{ borderTop: '4px solid #0b2c4a' }}>
              <div>
                <h3 className="text-sm font-bold" style={{ color: 'var(--ksp-navy)' }}>
                  Per-PS Comparison — {selectedPortal.label}
                </h3>
                <p className="text-xs opacity-60 mt-0.5">
                  Every active Police Station shown; zero rows = no submission on this date.
                  Pending column reflects the latest snapshot on the day.
                </p>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <span className="font-semibold" style={{ color: 'var(--ksp-navy)' }}>Portal:</span>
                <select value={portalKey}
                  onChange={(e) => setPortalKey(e.target.value)}
                  className="px-3 py-1.5 rounded-lg text-sm font-semibold"
                  style={{
                    border: '2px solid var(--ksp-navy)',
                    background: selectedPortal.accent,
                    color: '#fff',
                  }}>
                  {PORTAL_TABS.map((t) => (
                    <option key={t.key} value={t.key} style={{ background: '#fff', color: '#000' }}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead style={{ background: '#f5f5f7' }}>
                  <tr>
                    <th className="px-3 py-2 text-left">#</th>
                    <th className="px-3 py-2 text-left">District</th>
                    <th className="px-3 py-2 text-left">Police Station</th>
                    <th className="px-3 py-2 text-right">Entries</th>
                    {selectedPortal.metrics.map((m) => (
                      <th key={m.key as string} className="px-3 py-2 text-right whitespace-nowrap"
                          title={m.label}>
                        {m.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 && (
                    <tr>
                      <td colSpan={4 + selectedPortal.metrics.length} className="px-3 py-8 text-center italic opacity-60">
                        No PSes active.
                      </td>
                    </tr>
                  )}
                  {rows.map((r, i) => {
                    const silent = r.entries === 0;
                    return (
                      <tr key={`${r.unit_id}-${r.ps_id}`}
                          className="border-t border-slate-100"
                          style={{ background: silent ? 'rgba(0,0,0,0.02)' : undefined }}>
                        <td className="px-3 py-2 text-xs font-mono opacity-70">{i + 1}</td>
                        <td className="px-3 py-2">{r.unit_name}</td>
                        <td className="px-3 py-2 font-semibold"
                            style={{ color: silent ? 'rgba(0,0,0,0.5)' : 'var(--ksp-navy)' }}>
                          {r.ps_name}
                        </td>
                        <td className="px-3 py-2 text-right font-mono"
                            style={{ color: silent ? 'rgba(0,0,0,0.35)' : 'var(--ksp-navy)' }}>
                          {r.entries}
                        </td>
                        {selectedPortal.metrics.map((m) => {
                          const v = r[m.key as keyof PortalsDsrMetrics] as number;
                          return (
                            <td key={m.key as string}
                                className="px-3 py-2 text-right font-mono"
                                style={{
                                  color: v > 0 ? 'var(--ksp-navy)' : 'rgba(0,0,0,0.3)',
                                  fontWeight: v > 0 ? 700 : 400,
                                }}>
                              {v > 0 ? formatNumber(v) : '—'}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
