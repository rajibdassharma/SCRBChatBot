import { useEffect, useMemo, useState } from 'react';
import { BarChart3, Trophy } from 'lucide-react';
import { toast } from 'sonner';
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, PieChart, Pie,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { getDailyWorkDashboard } from '../lib/api/daily-work';
import { todayISO, isoDaysAgo } from '../lib/utils/format';
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

// todayISO + isoDaysAgo imported from lib/utils/format -- the local
// copies used .toISOString() which drops back a day at IST midnight.
const isoNDaysAgo = isoDaysAgo;

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
  // Overview / PS Ranking, matching the FIR Dashboard. Both tabs read
  // the same fetched response and the same date window, so switching
  // never re-requests and the two can never disagree.
  const [tab, setTab] = useState<'overview' | 'ranking'>('overview');

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
        {data?.cross_ps
          ? 'Aggregated investigation activity across all police stations for the selected date range.'
          : 'Aggregated activity for this PS across the selected date range.'}
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

      {/* Tab bar. PS Ranking is super_admin-only: a PS-level admin gets
           exactly one row, so the comparison would be noise. The bar
           itself is gated the same way. */}
      {!busy && data?.cross_ps && (
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
            <Trophy className="w-4 h-4" /> PS Ranking
          </button>
        </div>
      )}

      {busy && <div className="text-center py-10 italic">Loading…</div>}

      {!busy && data && (
        <>
          {(!data.cross_ps || tab === 'overview') && (<>
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

          </>)}

          {/* PS Ranking tab. Stations that logged nothing are INCLUDED
               with zeros: silence is the finding here, and hiding a
               silent station would hide exactly the row worth asking
               about. */}
          {data.cross_ps && tab === 'ranking' && (data.per_ps?.length ?? 0) > 0 && (
            <div className="rounded-2xl overflow-x-auto mt-5"
              style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
              <div className="px-5 py-4"
                style={{ borderBottom: '3px solid var(--ksp-yellow)' }}>
                <h3 className="text-sm font-bold" style={{ color: 'var(--ksp-navy)' }}>
                  Investigation activity by Police Station
                </h3>
                <p className="text-xs mt-1 opacity-60">
                  {data.date_from} → {data.date_to}. Busiest first. Stations with no
                  entries in this window are shown with zeros rather than omitted —
                  {' '}<b>{(data.per_ps ?? []).filter((r) => r.entries === 0).length}</b> of
                  {' '}{(data.per_ps ?? []).length} logged nothing.
                </p>
              </div>
              <table className="w-full text-sm text-left">
                <thead style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}>
                  <tr>
                    <th className="px-4 py-3 text-xs uppercase font-bold">#</th>
                    <th className="px-4 py-3 text-xs uppercase font-bold">District</th>
                    <th className="px-4 py-3 text-xs uppercase font-bold">Police Station</th>
                    <th className="px-4 py-3 text-xs uppercase font-bold text-right">Entries</th>
                    <th className="px-4 py-3 text-xs uppercase font-bold text-right">FIRs</th>
                    <th className="px-4 py-3 text-xs uppercase font-bold text-right">Notices</th>
                    <th className="px-4 py-3 text-xs uppercase font-bold text-right">Lien req.</th>
                    <th className="px-4 py-3 text-xs uppercase font-bold text-right">Arrests</th>
                    <th className="px-4 py-3 text-xs uppercase font-bold text-right">Statements</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.per_ps ?? []).map((r, i) => (
                    <tr key={`${r.unit_id}-${r.ps_id}`} className="border-t"
                      style={{ borderColor: 'rgba(11,44,74,0.08)' }}>
                      <td className="px-4 py-2 opacity-60">{i + 1}</td>
                      <td className="px-4 py-2">{r.district}</td>
                      <td className="px-4 py-2 font-semibold" style={{ color: 'var(--ksp-navy)' }}>
                        {r.ps_name}
                      </td>
                      <td className="px-4 py-2 text-right font-bold"
                        style={{ color: r.entries === 0 ? 'var(--ksp-red)' : 'var(--ksp-navy)' }}>
                        {r.entries.toLocaleString('en-IN')}
                      </td>
                      <td className="px-4 py-2 text-right">{r.unique_firs.toLocaleString('en-IN')}</td>
                      <td className="px-4 py-2 text-right">{r.notices.toLocaleString('en-IN')}</td>
                      <td className="px-4 py-2 text-right">{r.lien_requests.toLocaleString('en-IN')}</td>
                      <td className="px-4 py-2 text-right">{r.arrests.toLocaleString('en-IN')}</td>
                      <td className="px-4 py-2 text-right">{r.statements.toLocaleString('en-IN')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
