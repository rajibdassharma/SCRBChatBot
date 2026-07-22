import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, PieChart, Pie,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { getDailyWorkDashboard } from '../lib/api/daily-work';
import type { DailyWorkDashboard } from '../types';

/** Admin dashboard for Daily Work Done.
 *
 *  Scope: caller's own (unit_id, ps_id) — same rule as every other
 *  admin dashboard on this app (VAPT 7.7 / 7.8). Cross-PS visibility
 *  for super-admin is a follow-up when needed.
 *
 *  Panels: date-window picker → KPI tile row → daily trend bar chart
 *  → final-report split pie. Empty windows show zeros with a hint
 *  rather than blanks.
 */

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function isoNDaysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

function fmtInt(n: number): string { return n.toLocaleString('en-IN'); }
function fmtInr(n: number): string {
  return n.toLocaleString('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 });
}

function Kpi({
  label, value, sub, accent,
}: { label: string; value: string; sub?: string; accent: string }) {
  return (
    <div className="rounded-2xl p-4 flex flex-col gap-1"
      style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
      <div className="text-[11px] font-bold uppercase tracking-wide"
        style={{ color: accent }}>{label}</div>
      <div className="text-2xl font-bold" style={{ color: 'var(--ksp-navy)' }}>{value}</div>
      {sub && <div className="text-xs opacity-60">{sub}</div>}
    </div>
  );
}

export function DailyWorkDashboardPage() {
  // Trailing-30-day default. Users can widen or narrow.
  const [from, setFrom] = useState(isoNDaysAgo(29));
  const [to, setTo] = useState(todayISO());
  const [data, setData] = useState<DailyWorkDashboard | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    getDailyWorkDashboard(from, to)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => toast.error(e instanceof Error ? e.message : 'Dashboard load failed'))
      .finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
  }, [from, to]);

  const finalReportChartData = useMemo(() => {
    if (!data) return [];
    const s = data.final_report_split;
    return [
      { name: 'A · Chargesheeted', value: s.a, fill: '#0a6b28' },
      { name: 'B · False',         value: s.b, fill: '#c49500' },
      { name: 'C · Undetected',    value: s.c, fill: '#8b1919' },
      { name: 'Open (unclosed)',   value: s.open, fill: '#5b6b7a' },
    ].filter((d) => d.value > 0);
  }, [data]);

  return (
    <div>
      <h1 className="text-[22px] font-bold mb-1"
        style={{ color: 'var(--ksp-navy)', letterSpacing: '-0.02em' }}>
        Daily Work Done — Dashboard
      </h1>
      <p className="text-sm font-medium mb-6" style={{ color: 'var(--ksp-red)' }}>
        Aggregated activity for this PS across the selected date range.
      </p>

      {/* Date window controls */}
      <div className="rounded-2xl p-4 mb-5 flex flex-wrap gap-3 items-end"
        style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
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
        <div className="flex gap-2 ml-auto">
          {[7, 30, 90].map((n) => (
            <button key={n} type="button"
              onClick={() => { setFrom(isoNDaysAgo(n - 1)); setTo(todayISO()); }}
              className="px-3 py-2 text-xs font-semibold rounded-lg"
              style={{ background: 'rgba(11,44,74,0.06)', color: 'var(--ksp-navy)' }}>
              Last {n} days
            </button>
          ))}
        </div>
      </div>

      {busy && <div className="text-center py-10 italic">Loading…</div>}

      {!busy && data && (
        <>
          {/* KPI tile row — the numbers that matter at a glance. */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 mb-5">
            <Kpi label="Entries logged" value={fmtInt(data.totals.entries)}
              sub={`${fmtInt(data.totals.unique_firs)} unique FIRs`}
              accent="var(--ksp-navy)" />
            <Kpi label="35(3) / 41A Notices" value={fmtInt(data.totals.notices_35_41a)}
              accent="#b10000" />
            <Kpi label="91/92/94 Notices" value={fmtInt(data.totals.notices_91_92_94_total)}
              sub={`Banks ${fmtInt(data.totals.notices_91_92_94_banks)} · Interm ${fmtInt(data.totals.notices_91_92_94_intermediary)} · Acc-Hldr ${fmtInt(data.totals.notices_91_92_94_account_holder)} · CDR/IPDR ${fmtInt(data.totals.notices_91_92_94_cdr_ipdr)}`}
              accent="#b10000" />
            <Kpi label="Arrests" value={fmtInt(data.totals.arrests)}
              accent="#0a6b28" />
            <Kpi label="Lien Requests" value={fmtInt(data.totals.lien_requests_total + data.totals.freeze_requests_total)}
              sub={`${fmtInr(data.totals.total_lien_amount)} total`}
              accent="#c49500" />
            <Kpi label="Unlien Requests" value={fmtInt(data.totals.unlien_requests_total + data.totals.defreeze_requests_total)}
              sub={`${fmtInr(data.totals.total_unlien_amount)} total`}
              accent="#c49500" />
            <Kpi label="Statements" value={fmtInt(data.totals.statements)}
              accent="#0a6b28" />
            <Kpi label="Cases closed"
              value={fmtInt(data.final_report_split.a + data.final_report_split.b + data.final_report_split.c)}
              sub={`${fmtInt(data.final_report_split.open)} still open`}
              accent="#0a6b28" />
          </div>

          {/* Daily trend + final-report split, side by side on wide screens. */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="rounded-2xl p-4 lg:col-span-2"
              style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
              <h3 className="text-sm font-bold uppercase tracking-wide mb-3"
                style={{ color: 'var(--ksp-red)' }}>Daily activity</h3>
              {data.daily.length === 0 ? (
                <div className="text-center italic opacity-60 py-10">
                  No entries logged in this window.
                </div>
              ) : (
                <div style={{ width: '100%', height: 300 }}>
                  <ResponsiveContainer>
                    <BarChart data={data.daily}>
                      <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                      <XAxis dataKey="day" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} />
                      <Tooltip />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      <Bar dataKey="notices" name="Notices" fill="#b10000" />
                      <Bar dataKey="arrests" name="Arrests" fill="#0a6b28" />
                      <Bar dataKey="statements" name="Statements" fill="#0b2c4a" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>

            <div className="rounded-2xl p-4"
              style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
              <h3 className="text-sm font-bold uppercase tracking-wide mb-3"
                style={{ color: 'var(--ksp-red)' }}>Final report split</h3>
              {finalReportChartData.length === 0 ? (
                <div className="text-center italic opacity-60 py-10">
                  No entries in window.
                </div>
              ) : (
                <div style={{ width: '100%', height: 300 }}>
                  <ResponsiveContainer>
                    <PieChart>
                      <Pie data={finalReportChartData} dataKey="value" nameKey="name"
                        cx="50%" cy="50%" outerRadius={90} label>
                        {finalReportChartData.map((entry, i) => (
                          <Cell key={i} fill={entry.fill} />
                        ))}
                      </Pie>
                      <Tooltip />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
