import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { Search } from 'lucide-react';
import { getDailyWorkByFir, getDailyWorkHistory } from '../lib/api/daily-work';
import type { DailyWorkEntry } from '../types';

/** Investigation Log — Update / History.
 *
 *  Top: FIR-scoped lookup. Type an FIR number → hit search → the
 *  table below shows every daily-work row for that FIR at this PS,
 *  most-recent first. Click any row to edit it.
 *
 *  Bottom (default): the operator's own PS's most recent 30 rows
 *  across all FIRs. Gives a landing view without typing anything —
 *  useful for "which FIRs did I touch this week?".
 */
export function DailyWorkUpdatePage() {
  const navigate = useNavigate();
  const [firNo, setFirNo] = useState('');
  const [rows, setRows] = useState<DailyWorkEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [scope, setScope] = useState<'recent' | 'fir'>('recent');

  // Landing load — recent PS-wide rows.
  useEffect(() => {
    setBusy(true);
    getDailyWorkHistory(30)
      .then((rs) => { setRows(rs); setScope('recent'); })
      .catch((e) => toast.error(e instanceof Error ? e.message : 'Failed to load history'))
      .finally(() => setBusy(false));
  }, []);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = firNo.trim();
    if (!trimmed) return;
    setBusy(true);
    try {
      const rs = await getDailyWorkByFir(trimmed);
      setRows(rs);
      setScope('fir');
      if (rs.length === 0) toast.info(`No entries yet for FIR ${trimmed}.`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Search failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <h1 className="text-[22px] font-bold mb-1"
        style={{ color: 'var(--ksp-navy)', letterSpacing: '-0.02em' }}>
        Daily Work Done — Update / History
      </h1>
      <p className="text-sm font-medium mb-6" style={{ color: 'var(--ksp-red)' }}>
        Search a specific FIR, or scroll the recent activity below. Click any row to edit.
      </p>

      <form onSubmit={handleSearch}
        className="rounded-2xl p-5 mb-5 flex flex-wrap gap-3 items-end"
        style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
        <div className="flex-1 min-w-[220px]">
          <label className="block text-xs font-semibold mb-1"
            style={{ color: 'var(--ksp-navy)' }}>FIR No.</label>
          <input
            type="text" value={firNo}
            onChange={(e) => setFirNo(e.target.value)}
            placeholder="e.g. 42/2026"
            maxLength={50}
            className="w-full px-3 py-2 rounded-xl text-sm outline-none"
            style={{ border: '2px solid var(--ksp-navy)', background: '#fff' }} />
        </div>
        <button type="submit"
          className="flex items-center gap-1.5 px-4 py-2 text-sm font-bold rounded-xl transition"
          style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)', border: '2px solid rgba(0,0,0,0.25)' }}>
          <Search className="w-4 h-4" /> Search
        </button>
        {scope === 'fir' && (
          <button type="button"
            onClick={async () => {
              setFirNo(''); setBusy(true);
              try { setRows(await getDailyWorkHistory(30)); setScope('recent'); }
              finally { setBusy(false); }
            }}
            className="px-4 py-2 text-sm font-semibold rounded-xl"
            style={{ background: 'rgba(11,44,74,0.06)', color: 'var(--ksp-navy)' }}>
            Show recent activity
          </button>
        )}
      </form>

      <div className="rounded-2xl overflow-hidden shadow-sm bg-white">
        <div className="px-4 py-3 text-xs font-bold uppercase tracking-wide"
          style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}>
          {scope === 'fir'
            ? `Entries for FIR ${firNo.trim()}`
            : `Recent activity — this PS (last ${rows.length})`}
        </div>
        <table className="w-full text-sm">
          <thead style={{ background: '#eef2f7' }}>
            <tr>
              <th className="px-3 py-2 text-left">Date</th>
              <th className="px-3 py-2 text-left">FIR No.</th>
              <th className="px-3 py-2 text-right">Notices</th>
              <th className="px-3 py-2 text-right">Lien Req.</th>
              <th className="px-3 py-2 text-right">Unlien Req.</th>
              <th className="px-3 py-2 text-right">Arrests</th>
              <th className="px-3 py-2 text-right">Statements</th>
              <th className="px-3 py-2 text-center">Final</th>
            </tr>
          </thead>
          <tbody>
            {busy && (
              <tr><td colSpan={8} className="px-3 py-6 text-center italic">Loading…</td></tr>
            )}
            {!busy && rows.length === 0 && (
              <tr><td colSpan={8} className="px-3 py-6 text-center italic">
                No entries {scope === 'fir' ? 'for this FIR' : 'yet at this PS'}.
              </td></tr>
            )}
            {!busy && rows.map((r) => (
              <tr key={r.id}
                className="border-t border-slate-100 hover:bg-slate-50 cursor-pointer"
                onClick={() => navigate(`/daily-work/${r.id}`)}>
                <td className="px-3 py-2 whitespace-nowrap">{r.report_date}</td>
                <td className="px-3 py-2 font-semibold"
                  style={{ color: 'var(--ksp-navy)' }}>{r.fir_no}</td>
                <td className="px-3 py-2 text-right">
                  {sumNotices(r)}
                </td>
                <td className="px-3 py-2 text-right">
                  {r.lien_requests_count + r.freeze_requests_count}
                </td>
                <td className="px-3 py-2 text-right">
                  {r.unlien_requests_count + r.defreeze_requests_count}
                </td>
                <td className="px-3 py-2 text-right">{r.arrests_count}</td>
                <td className="px-3 py-2 text-right">{r.statements_count}</td>
                <td className="px-3 py-2 text-center">
                  {r.final_report
                    ? <span className="px-2 py-0.5 rounded-full text-xs font-bold"
                        style={{ background: 'var(--ksp-yellow)', color: '#000' }}>
                        {r.final_report}
                      </span>
                    : <span className="text-xs opacity-40">—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function sumNotices(r: DailyWorkEntry): number {
  return r.notices_35_41a_count
    + r.notices_91_92_94_banks
    + r.notices_91_92_94_intermediary
    + r.notices_91_92_94_account_holder
    + r.notices_91_92_94_cdr_ipdr;
}
