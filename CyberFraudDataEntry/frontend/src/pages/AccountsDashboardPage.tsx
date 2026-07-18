import { useEffect, useState } from 'react';
import { BarChart3 } from 'lucide-react';
import { toast } from 'sonner';
import { getAccountsSummary, getAccountsComparison } from '../lib/api/dashboard';
import { formatNumber, todayISO } from '../lib/utils/format';
import type { AccountsKpiSummary, AccountsPsComparison } from '../types';

/** Account Details Dashboard — mirrors the shell + feel of the DSR
 *  Overview tab (KPI cards + per-PS comparison table) but populated
 *  from all_accounts. Single tab for now; can grow into Investigation
 *  / Operations tabs later if the volume justifies it. */

const cardStyle = {
  background: '#fff',
  border: '1px solid rgba(0,0,0,0.06)',
  boxShadow: '0 6px 16px rgba(0,0,0,0.08)',
};

function KpiCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-2xl p-5"
      style={{ ...cardStyle, borderLeft: '4px solid var(--ksp-yellow)' }}>
      <p className="text-xs uppercase tracking-wide font-bold mb-1" style={{ color: 'var(--ksp-red)' }}>{label}</p>
      <p className="text-2xl font-bold" style={{ color: 'var(--ksp-navy)' }}>{value}</p>
      {sub && <p className="text-xs mt-1 opacity-60">{sub}</p>}
    </div>
  );
}

export function AccountsDashboardPage() {
  const [date, setDate] = useState(todayISO());
  const [summary, setSummary] = useState<AccountsKpiSummary | null>(null);
  const [rows, setRows] = useState<AccountsPsComparison[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      getAccountsSummary(date),
      getAccountsComparison(date),
    ]).then(([s, u]) => {
      if (s.status === 'fulfilled') setSummary(s.value); else { setSummary(null); toast.error(`Summary: ${(s as any).reason?.message ?? 'failed'}`); }
      if (u.status === 'fulfilled') setRows(u.value); else { setRows([]); toast.error(`Per-PS: ${(u as any).reason?.message ?? 'failed'}`); }
    }).finally(() => setLoading(false));
  }, [date]);

  return (
    <div>
      {/* Header + date picker */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-[22px] font-bold mb-1 flex items-center gap-2" style={{ color: 'var(--ksp-navy)' }}>
            <BarChart3 className="w-5 h-5" /> Account Details Dashboard
          </h1>
          <p className="text-sm font-medium" style={{ color: 'var(--ksp-red)' }}>
            Cumulative account KPIs as of the selected date.
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
          {/* KPI cards row */}
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-4">
            <KpiCard label="Total Accounts" value={formatNumber(summary?.total_accounts ?? 0)} />
            <KpiCard label="Victim Accounts" value={formatNumber(summary?.victim_accounts ?? 0)} />
            <KpiCard label="Mule Accounts" value={formatNumber(summary?.mule_accounts ?? 0)} />
            <KpiCard label="Non-Mule Accounts" value={formatNumber(summary?.non_mule_accounts ?? 0)} />
            <KpiCard label="Unique Banks" value={formatNumber(summary?.unique_banks ?? 0)} />
            <KpiCard label="Mule Herders" value={formatNumber(summary?.unique_mule_herders ?? 0)}
              sub="distinct names" />
            <KpiCard label="With ID Photo" value={formatNumber(summary?.accounts_with_photo ?? 0)} />
          </div>

          {/* PS submission summary */}
          <div className="rounded-2xl p-5" style={cardStyle}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold" style={{ color: 'var(--ksp-navy)' }}>
                PSes with account data
              </h3>
              <span className="text-xs opacity-60">
                {summary?.units_submitted ?? 0} / {summary?.units_total ?? 0} PS{(summary?.units_total ?? 0) === 1 ? '' : 'es'} reporting
              </span>
            </div>
          </div>

          {/* Per-PS comparison table */}
          <div className="rounded-2xl overflow-hidden" style={cardStyle}>
            <div className="px-5 py-3 border-b">
              <h3 className="text-sm font-bold" style={{ color: 'var(--ksp-navy)' }}>
                Per-PS Account Comparison
              </h3>
              <p className="text-xs opacity-60">Descending by total account count.</p>
            </div>
            <table className="w-full text-sm">
              <thead style={{ background: '#f5f5f7' }}>
                <tr>
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
                    <td colSpan={6} className="px-3 py-8 text-center italic opacity-60">
                      No account records yet for this cut-off date.
                    </td>
                  </tr>
                )}
                {rows.map((r) => (
                  <tr key={`${r.unit_id}-${r.ps_id}`} className="border-t border-slate-100">
                    <td className="px-3 py-2">{r.unit_name}</td>
                    <td className="px-3 py-2">{r.ps_name}</td>
                    <td className="px-3 py-2 text-right font-mono">{formatNumber(r.total)}</td>
                    <td className="px-3 py-2 text-right font-mono">
                      <span style={{ color: '#0a6b28' }}>{formatNumber(r.victims)}</span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      <span style={{ color: '#8b1919' }}>{formatNumber(r.mules)}</span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      <span style={{ color: '#0b2c4a' }}>{formatNumber(r.non_mules)}</span>
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
