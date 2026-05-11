import { useState, useEffect } from 'react';
import { getSummary, getUnitComparison, getTrends, getSubmissionStatus } from '../lib/api/dashboard';
import { formatINR, formatNumber, todayISO } from '../lib/utils/format';
import type { KpiSummary, UnitComparison, TrendPoint, SubmissionStatus } from '../types';
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { BarChart3, CheckCircle, XCircle } from 'lucide-react';

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

export function DashboardPage() {
  const [date, setDate] = useState(todayISO());
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

    // allSettled so a single endpoint failing (e.g. partial deploy) doesn't
    // blank out the whole page — each section degrades to its empty state.
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

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between mb-6">
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

      {loading ? (
        <div className="text-center py-16 font-semibold" style={{ color: 'var(--ksp-navy)' }}>Loading dashboard...</div>
      ) : (
        <div className="space-y-6">
          {/* KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <KpiCard label="Total Cases" value={formatNumber(summary?.total_cases ?? 0)} />
            <KpiCard label="Total Arrests" value={formatNumber(summary?.total_arrests ?? 0)} />
            <KpiCard label="Amount Lien Marked" value={formatINR(summary?.total_amount_lien_marked ?? 0)} />
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

            <div className="rounded-2xl p-5" style={cardStyle}>
              <h3 className="text-sm font-bold mb-4" style={{ color: 'var(--ksp-navy)' }}>Cases by Unit</h3>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={top15} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" tick={{ fontSize: 11 }} />
                  <YAxis dataKey="unit_name" type="category" width={140} tick={{ fontSize: 9 }} />
                  <Tooltip />
                  <Bar dataKey="cases" fill="#0b2c4a" name="Cases" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Amount Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="rounded-2xl p-5" style={cardStyle}>
              <h3 className="text-sm font-bold mb-4" style={{ color: 'var(--ksp-navy)' }}>Amount Overview</h3>
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie
                    data={[
                      { name: 'Lien Marked', value: summary?.total_amount_lien_marked ?? 0 },
                      { name: 'Refunded', value: summary?.total_amount_refunded ?? 0 },
                    ]}
                    cx="50%" cy="50%" outerRadius={80}
                    dataKey="value" label={({ name, value }) => `${name}: ${formatINR(value)}`}
                  >
                    <Cell fill="#0b2c4a" />
                    <Cell fill="#ffd400" />
                  </Pie>
                  <Tooltip formatter={(val) => formatINR(Number(val) || 0)} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>

            <div className="rounded-2xl p-5" style={cardStyle}>
              <h3 className="text-sm font-bold mb-4" style={{ color: 'var(--ksp-navy)' }}>Accounts Summary</h3>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={[{
                  name: 'District Total',
                  lien_marked: summary?.total_accounts_lien_marked ?? 0,
                  defreezed: summary?.total_accounts_defreezed ?? 0,
                }]}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="lien_marked" fill="#0b2c4a" name="Accounts Lien Marked" />
                  <Bar dataKey="defreezed" fill="#ffd400" name="Accounts De-Freezed" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Submission Status Table */}
          <div className="rounded-2xl overflow-x-auto" style={cardStyle}>
            <div className="px-5 py-4" style={{ borderBottom: '3px solid var(--ksp-yellow)' }}>
              <h3 className="text-sm font-bold" style={{ color: 'var(--ksp-navy)' }}>Submission Status for {date}</h3>
            </div>
            <table className="w-full text-sm text-left">
              <thead style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}>
                <tr>
                  <th className="px-4 py-3 text-xs uppercase font-bold">#</th>
                  <th className="px-4 py-3 text-xs uppercase font-bold">Unit Name</th>
                  <th className="px-4 py-3 text-xs uppercase font-bold text-center">DSR</th>
                  <th className="px-4 py-3 text-xs uppercase font-bold text-center">Mule</th>
                </tr>
              </thead>
              <tbody>
                {statuses.map((s, i) => (
                  <tr key={s.unit_id} className="border-t hover:bg-[#fff3b0]/30" style={{ borderColor: 'rgba(0,0,0,0.06)' }}>
                    <td className="px-4 py-2 opacity-50">{i + 1}</td>
                    <td className="px-4 py-2 font-semibold" style={{ color: 'var(--ksp-navy)' }}>{s.unit_name}</td>
                    <td className="px-4 py-2 text-center">
                      {s.dsr_submitted
                        ? <CheckCircle className="w-4 h-4 inline" style={{ color: '#0a5c2a' }} />
                        : <XCircle className="w-4 h-4 inline" style={{ color: 'var(--ksp-red)' }} />}
                    </td>
                    <td className="px-4 py-2 text-center">
                      {s.mule_submitted
                        ? <CheckCircle className="w-4 h-4 inline" style={{ color: '#0a5c2a' }} />
                        : <XCircle className="w-4 h-4 inline" style={{ color: 'var(--ksp-red)' }} />}
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
