import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { toast } from 'sonner';
import { Plus, Search } from 'lucide-react';
import { listAllAccounts } from '../lib/api/all-accounts';
import { useAuthStore } from '../lib/stores/auth-store';
import type { AccountType, AllAccountListItem } from '../types';

const TYPE_FILTERS: ('' | 'Victim' | 'Mule' | 'Non-Mule')[] = ['', 'Victim', 'Mule', 'Non-Mule'];

/** Chip colour per account type — green for Victim (positive
 *  identification of a wronged party), red for Mule (confirmed
 *  fraudster account), slate for Non-Mule (under review or
 *  cleared). */
const TYPE_CHIP: Record<AccountType, { bg: string; fg: string }> = {
  Victim:     { bg: 'rgba(10,107,40,0.12)', fg: '#0a6b28' },
  Mule:       { bg: 'rgba(177,0,0,0.10)',   fg: '#8b1919' },
  'Non-Mule': { bg: 'rgba(11,44,74,0.08)',  fg: '#0b2c4a' },
};

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' });
}

/** Update / search page — PS-scoped list with a free-text filter.
 *  Click a row to open the entry page in edit mode. */
export function AllAccountUpdatePage() {
  const navigate = useNavigate();
  const { user } = useAuthStore();

  const [rows, setRows] = useState<AllAccountListItem[]>([]);
  const [q, setQ] = useState('');
  const [typeFilter, setTypeFilter] = useState<'' | 'Victim' | 'Mule' | 'Non-Mule'>('');
  const [busy, setBusy] = useState(false);

  // Debounced fetch so we don't slam the server on every keystroke.
  const debouncedQ = useDebounce(q, 300);

  useEffect(() => {
    setBusy(true);
    listAllAccounts({
      q: debouncedQ || undefined,
      accountType: typeFilter || undefined,
      limit: 100,
    })
      .then(setRows)
      .catch((e) => toast.error(e.message))
      .finally(() => setBusy(false));
  }, [debouncedQ, typeFilter]);

  const summary = useMemo(() => {
    const victims = rows.filter((r) => r.account_type === 'Victim').length;
    const mules = rows.filter((r) => r.account_type === 'Mule').length;
    const nonMules = rows.filter((r) => r.account_type === 'Non-Mule').length;
    return { victims, mules, nonMules };
  }, [rows]);

  return (
    <div>
      {/* Header */}
      <div className="rounded-2xl p-4 mb-4" style={{ background: 'var(--ksp-navy)', color: '#fff' }}>
        <h1 className="text-lg font-bold" style={{ color: 'var(--ksp-yellow)' }}>All Accounts</h1>
        <div className="flex gap-6 mt-2 text-sm">
          <span><strong>District:</strong> {user?.unit_name}</span>
          <span><strong>CCPS:</strong> {user?.ps_name || 'N/A'}</span>
          <span><strong>User:</strong> {user?.username}</span>
        </div>
      </div>

      <div className="flex items-center justify-between mb-4 gap-4 flex-wrap">
        <div>
          <h1 className="text-[22px] font-bold mb-1" style={{ color: 'var(--ksp-navy)' }}>
            Update Account
          </h1>
          <p className="text-sm font-medium" style={{ color: 'var(--ksp-red)' }}>
            {rows.length} record{rows.length === 1 ? '' : 's'} · {summary.victims} victim · {summary.mules} mule · {summary.nonMules} non-mule
          </p>
        </div>
        <Link to="/all-accounts/new"
          className="flex items-center gap-1.5 px-4 py-2 text-sm font-bold rounded-xl transition"
          style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)', border: '2px solid rgba(0,0,0,0.25)' }}>
          <Plus className="w-4 h-4" /> New Account
        </Link>
      </div>

      {/* Filters */}
      <div className="rounded-2xl p-4 mb-4 flex items-center gap-3 flex-wrap"
        style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
        <div className="relative flex-1 min-w-[280px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 opacity-40" />
          <input type="text" value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Search account no, holder name, FIR, NCRP ack…"
            className="w-full pl-9 pr-3 py-2 rounded-xl text-sm outline-none"
            style={{ border: '2px solid var(--ksp-navy)', background: '#fff' }} />
        </div>
        <label className="text-sm flex items-center gap-2">
          <span className="font-semibold" style={{ color: 'var(--ksp-navy)' }}>Type:</span>
          <select value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value as '' | 'Victim' | 'Mule')}
            className="px-3 py-1.5 rounded-lg text-sm bg-white"
            style={{ border: '2px solid var(--ksp-navy)' }}>
            {TYPE_FILTERS.map((t) => (
              <option key={t || 'all'} value={t}>{t || 'All'}</option>
            ))}
          </select>
        </label>
      </div>

      {/* Table */}
      <div className="rounded-2xl overflow-hidden shadow-sm bg-white">
        <table className="w-full text-sm">
          <thead style={{ background: 'var(--ksp-navy)', color: '#fff' }}>
            <tr>
              <th className="px-3 py-2 text-left">Serial</th>
              <th className="px-3 py-2 text-left">Account No</th>
              <th className="px-3 py-2 text-left">Bank</th>
              <th className="px-3 py-2 text-left">Holder</th>
              <th className="px-3 py-2 text-left">Type</th>
              <th className="px-3 py-2 text-left">FIR / NCRP</th>
              <th className="px-3 py-2 text-left">Created</th>
            </tr>
          </thead>
          <tbody>
            {busy && (
              <tr><td colSpan={7} className="px-3 py-8 text-center italic opacity-60">Loading…</td></tr>
            )}
            {!busy && rows.length === 0 && (
              <tr><td colSpan={7} className="px-3 py-8 text-center italic opacity-60">
                No records match. Try a broader search or click New Account.
              </td></tr>
            )}
            {!busy && rows.map((r) => (
              <tr key={r.id}
                onClick={() => navigate(`/all-accounts/${r.id}`)}
                className="border-t border-slate-100 hover:bg-slate-50 cursor-pointer">
                <td className="px-3 py-2 font-mono">{r.serial_no}</td>
                <td className="px-3 py-2 font-mono">{r.account_no}</td>
                <td className="px-3 py-2">{r.bank_name}</td>
                <td className="px-3 py-2">{r.account_holder_name}</td>
                <td className="px-3 py-2">
                  <span className="px-2 py-0.5 rounded-full text-xs font-semibold"
                    style={{
                      background: TYPE_CHIP[r.account_type].bg,
                      color:      TYPE_CHIP[r.account_type].fg,
                    }}>
                    {r.account_type}
                  </span>
                </td>
                <td className="px-3 py-2 text-xs opacity-80">
                  {r.fir_no ?? '—'} / {r.ncrp_ack_no ?? '—'}
                </td>
                <td className="px-3 py-2 whitespace-nowrap text-xs opacity-70">{fmtDate(r.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Tiny debounce hook (avoids adding a dep just for this).
function useDebounce<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}
