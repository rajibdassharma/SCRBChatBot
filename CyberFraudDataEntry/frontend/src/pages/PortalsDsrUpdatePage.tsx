import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { listPortalsDsr } from '../lib/api/portals-dsr';
import { useAuthStore } from '../lib/stores/auth-store';
import type { PortalsDsrListItem, PortalsDsrStatus } from '../types';

const STATUS_CHIP: Record<PortalsDsrStatus, { bg: string; fg: string }> = {
  draft:     { bg: 'rgba(198,124,29,0.12)', fg: '#c67c1d' },
  submitted: { bg: 'rgba(10,107,40,0.12)',  fg: '#0a6b28' },
};

const STATUS_FILTERS: ('' | PortalsDsrStatus)[] = ['', 'draft', 'submitted'];

function fmtDate(iso: string): string {
  // Just the date portion of an ISO datetime, in en-IN.
  return new Date(iso).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' });
}

/** Update / history page — PS-scoped list of Portals DSR entries.
 *  Click a row to open in edit mode. Draft rows are the ones you'd
 *  typically want to open + finish; submitted rows are archived. */
export function PortalsDsrUpdatePage() {
  const navigate = useNavigate();
  const { user } = useAuthStore();

  const [rows, setRows] = useState<PortalsDsrListItem[]>([]);
  const [statusFilter, setStatusFilter] = useState<'' | PortalsDsrStatus>('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setBusy(true);
    listPortalsDsr({
      status: statusFilter || undefined,
      limit: 100,
    })
      .then(setRows)
      .catch((e) => toast.error(e.message))
      .finally(() => setBusy(false));
  }, [statusFilter]);

  return (
    <div>
      {/* Header */}
      <div className="rounded-2xl p-4 mb-4" style={{ background: 'var(--ksp-navy)', color: '#fff' }}>
        <h1 className="text-lg font-bold" style={{ color: 'var(--ksp-yellow)' }}>Portals DSR</h1>
        <div className="flex gap-6 mt-2 text-sm">
          <span><strong>District:</strong> {user?.unit_name}</span>
          <span><strong>CCPS:</strong> {user?.ps_name || 'N/A'}</span>
          <span><strong>User:</strong> {user?.username}</span>
        </div>
      </div>

      <div className="flex items-center justify-between mb-4 gap-4 flex-wrap">
        <div>
          <h1 className="text-[22px] font-bold mb-1" style={{ color: 'var(--ksp-navy)' }}>
            Update / History
          </h1>
          <p className="text-sm font-medium" style={{ color: 'var(--ksp-red)' }}>
            {rows.length} entr{rows.length === 1 ? 'y' : 'ies'} · newest first · multiple entries per day are legal
          </p>
        </div>
        <Link to="/portals-dsr/new"
          className="flex items-center gap-1.5 px-4 py-2 text-sm font-bold rounded-xl transition"
          style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)', border: '2px solid rgba(0,0,0,0.25)' }}>
          <Plus className="w-4 h-4" /> New Entry
        </Link>
      </div>

      {/* Filters */}
      <div className="rounded-2xl p-4 mb-4 flex items-center gap-3 flex-wrap"
        style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
        <label className="text-sm flex items-center gap-2">
          <span className="font-semibold" style={{ color: 'var(--ksp-navy)' }}>Status:</span>
          <select value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as '' | PortalsDsrStatus)}
            className="px-3 py-1.5 rounded-lg text-sm bg-white"
            style={{ border: '2px solid var(--ksp-navy)' }}>
            {STATUS_FILTERS.map((s) => (
              <option key={s || 'all'} value={s}>{s || 'All'}</option>
            ))}
          </select>
        </label>
      </div>

      {/* Table */}
      <div className="rounded-2xl overflow-hidden shadow-sm bg-white">
        <table className="w-full text-sm">
          <thead style={{ background: 'var(--ksp-navy)', color: '#fff' }}>
            <tr>
              <th className="px-3 py-2 text-left">Report Date</th>
              <th className="px-3 py-2 text-left">Status</th>
              <th className="px-3 py-2 text-right">Grand Total</th>
              <th className="px-3 py-2 text-left">Created</th>
            </tr>
          </thead>
          <tbody>
            {busy && (
              <tr><td colSpan={4} className="px-3 py-8 text-center italic opacity-60">Loading…</td></tr>
            )}
            {!busy && rows.length === 0 && (
              <tr><td colSpan={4} className="px-3 py-8 text-center italic opacity-60">
                No entries yet. Click New Entry to start.
              </td></tr>
            )}
            {!busy && rows.map((r) => (
              <tr key={r.id}
                onClick={() => navigate(`/portals-dsr/${r.id}`)}
                className="border-t border-slate-100 hover:bg-slate-50 cursor-pointer">
                <td className="px-3 py-2 font-mono">{r.report_date}</td>
                <td className="px-3 py-2">
                  <span className="px-2 py-0.5 rounded-full text-xs font-semibold"
                    style={{
                      background: STATUS_CHIP[r.status].bg,
                      color:      STATUS_CHIP[r.status].fg,
                    }}>
                    {r.status}
                  </span>
                </td>
                <td className="px-3 py-2 text-right font-mono font-bold">{r.total}</td>
                <td className="px-3 py-2 whitespace-nowrap text-xs opacity-70">{fmtDate(r.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
