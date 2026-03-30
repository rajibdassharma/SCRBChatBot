import { useState, useEffect } from 'react';
import { getDsrHistory } from '../lib/api/dsr';
import { getMuleHistory } from '../lib/api/mule';
import { formatINR, formatNumber } from '../lib/utils/format';
import type { DsrEntry, MuleEntry } from '../types';
import { Clock } from 'lucide-react';

export function HistoryPage() {
  const [tab, setTab] = useState<'dsr' | 'mule'>('dsr');
  const [dsrHistory, setDsrHistory] = useState<DsrEntry[]>([]);
  const [muleHistory, setMuleHistory] = useState<MuleEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([getDsrHistory(60), getMuleHistory(60)])
      .then(([d, m]) => { setDsrHistory(d); setMuleHistory(m); })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <h1 className="text-[22px] font-bold mb-1 flex items-center gap-2" style={{ color: 'var(--ksp-navy)' }}>
        <Clock className="w-6 h-6" /> Submission History
      </h1>
      <p className="text-sm font-medium mb-6" style={{ color: 'var(--ksp-red)' }}>View your past submissions</p>

      <div className="flex gap-2 mb-4">
        <button
          onClick={() => setTab('dsr')}
          className="px-4 py-2 rounded-xl text-sm font-semibold transition"
          style={{
            background: tab === 'dsr' ? 'var(--ksp-navy)' : 'var(--ksp-yellow)',
            color: tab === 'dsr' ? 'var(--ksp-yellow)' : '#000',
            border: '2px solid rgba(0,0,0,0.2)',
          }}
        >
          DSR Entries ({dsrHistory.length})
        </button>
        <button
          onClick={() => setTab('mule')}
          className="px-4 py-2 rounded-xl text-sm font-semibold transition"
          style={{
            background: tab === 'mule' ? 'var(--ksp-navy)' : 'var(--ksp-yellow)',
            color: tab === 'mule' ? 'var(--ksp-yellow)' : '#000',
            border: '2px solid rgba(0,0,0,0.2)',
          }}
        >
          Mule Entries ({muleHistory.length})
        </button>
      </div>

      {loading ? (
        <div className="text-sm py-8 text-center" style={{ color: 'var(--ksp-navy)' }}>Loading...</div>
      ) : tab === 'dsr' ? (
        <div className="rounded-2xl overflow-x-auto" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
          <table className="w-full text-sm text-left">
            <thead style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}>
              <tr>
                <th className="px-4 py-3 text-xs uppercase font-bold">Date</th>
                <th className="px-4 py-3 text-xs uppercase font-bold">Cases</th>
                <th className="px-4 py-3 text-xs uppercase font-bold">Petitions</th>
                <th className="px-4 py-3 text-xs uppercase font-bold">Arrests</th>
                <th className="px-4 py-3 text-xs uppercase font-bold">Amt Lien Marked</th>
                <th className="px-4 py-3 text-xs uppercase font-bold">Amt Refunded</th>
                <th className="px-4 py-3 text-xs uppercase font-bold">Updated</th>
              </tr>
            </thead>
            <tbody>
              {dsrHistory.map((d) => (
                <tr key={d.id} className="border-t hover:bg-[#fff3b0]/30" style={{ borderColor: 'rgba(0,0,0,0.06)' }}>
                  <td className="px-4 py-3 font-semibold" style={{ color: 'var(--ksp-navy)' }}>{d.report_date}</td>
                  <td className="px-4 py-3">{formatNumber(d.cases)}</td>
                  <td className="px-4 py-3">{formatNumber(d.petitions)}</td>
                  <td className="px-4 py-3">{formatNumber(d.details_of_arrest)}</td>
                  <td className="px-4 py-3">{formatINR(Number(d.cumulative_amount_lien_marked))}</td>
                  <td className="px-4 py-3">{formatINR(Number(d.amount_refunded_to_victim))}</td>
                  <td className="px-4 py-3 text-xs opacity-60">{d.updated_at?.split('T')[0] ?? '-'}</td>
                </tr>
              ))}
              {dsrHistory.length === 0 && (
                <tr><td colSpan={7} className="px-4 py-8 text-center opacity-50">No DSR entries yet</td></tr>
              )}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="rounded-2xl overflow-x-auto" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
          <table className="w-full text-sm text-left">
            <thead style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}>
              <tr>
                <th className="px-4 py-3 text-xs uppercase font-bold">Date</th>
                <th className="px-4 py-3 text-xs uppercase font-bold">Accounts w/ Liens</th>
                <th className="px-4 py-3 text-xs uppercase font-bold">Max Money Routed</th>
                <th className="px-4 py-3 text-xs uppercase font-bold">Crypto Accounts</th>
                <th className="px-4 py-3 text-xs uppercase font-bold">Updated</th>
              </tr>
            </thead>
            <tbody>
              {muleHistory.map((m) => (
                <tr key={m.id} className="border-t hover:bg-[#fff3b0]/30" style={{ borderColor: 'rgba(0,0,0,0.06)' }}>
                  <td className="px-4 py-3 font-semibold" style={{ color: 'var(--ksp-navy)' }}>{m.report_date}</td>
                  <td className="px-4 py-3 max-w-xs truncate">{m.accounts_most_liens || '-'}</td>
                  <td className="px-4 py-3 max-w-xs truncate">{m.accounts_max_money_routed || '-'}</td>
                  <td className="px-4 py-3 max-w-xs truncate">{m.crypto_mule_accounts || '-'}</td>
                  <td className="px-4 py-3 text-xs opacity-60">{m.updated_at?.split('T')[0] ?? '-'}</td>
                </tr>
              ))}
              {muleHistory.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-8 text-center opacity-50">No Mule entries yet</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
