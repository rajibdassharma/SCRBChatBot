import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { BarChart3, FileDown, FileSpreadsheet } from 'lucide-react';
import { getFirPsPerformance } from '../lib/api/dashboard';
import {
  downloadFirPsPerformanceExcel, downloadFirPsPerformancePdf,
} from '../lib/api/reports';
import { todayISO, isoDaysAgo } from '../lib/utils/format';
import type { FirPsPerformanceRow } from '../types';

/** DSR → FIR Dashboard.
 *
 *  Single table for now (2026-07-22 spec): District, PS Name, Total
 *  FIRs registered in the selected date range. Purpose is to measure
 *  PS performance — hence the sort defaulting to fir_count DESC so
 *  the busiest PSes surface at the top.
 *
 *  Data sourced entirely from the `cases` table (Case Detail entry
 *  fields — no derived arrest/petition/lien metrics). Registration
 *  date drives the window, not created_at, so back-dated entries
 *  count on the day the FIR was actually registered.
 *
 *  Scoping (same VAPT 7.7/7.8 rule as every other admin dashboard):
 *   - admin       → one row for own (district, PS)
 *   - super_admin → all active (district, PS) pairs, zero counts
 *                    included so under-performers show up.
 */

// todayISO + isoDaysAgo imported from lib/utils/format -- the local
// copies used .toISOString() which drops back a day at IST midnight.
const isoNDaysAgo = isoDaysAgo;

function fmtInt(n: number): string { return n.toLocaleString('en-IN'); }

// "24 Jul" — short header label for the Yesterday column. Client-side
// so the label tracks the user's local date, matching the server's
// today-1 window (both machines are on the same IST tz in production).
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

// Sort control — click a header once to sort by that column in its
// default direction, click again to reverse. Default direction:
// count DESC (bigger performers first), district/PS ASC (A→Z).
type SortKey = 'district' | 'ps_name' | 'fir_count' | 'yesterday_count';
type SortDir = 'asc' | 'desc';
const DEFAULT_DIR: Record<SortKey, SortDir> = {
  district: 'asc',
  ps_name: 'asc',
  fir_count: 'desc',
  yesterday_count: 'desc',
};

export function DsrFirDashboardPage() {
  const [from, setFrom] = useState(isoNDaysAgo(29));
  const [to, setTo] = useState(todayISO());
  const [rows, setRows] = useState<FirPsPerformanceRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [sortBy, setSortBy] = useState<SortKey>('fir_count');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [dl, setDl] = useState<'pdf' | 'xlsx' | null>(null);

  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    getFirPsPerformance(from, to)
      .then((r) => { if (!cancelled) setRows(r); })
      .catch((e) => toast.error(e instanceof Error ? e.message : 'Dashboard load failed'))
      .finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
  }, [from, to]);

  const onSort = (k: SortKey) => {
    if (sortBy === k) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortBy(k);
      setSortDir(DEFAULT_DIR[k]);
    }
  };

  // Sorted rows — the backend already returns fir_count DESC; we
  // re-sort locally so header clicks re-order without a round-trip.
  // Tiebreaker keeps stable ordering across renders.
  const sortedRows = useMemo(() => {
    const copy = [...rows];
    copy.sort((a, b) => {
      let cmp = 0;
      if (sortBy === 'district') cmp = a.district.localeCompare(b.district);
      else if (sortBy === 'ps_name') cmp = a.ps_name.localeCompare(b.ps_name);
      else if (sortBy === 'yesterday_count') cmp = a.yesterday_count - b.yesterday_count;
      else cmp = a.fir_count - b.fir_count;
      if (sortDir === 'desc') cmp = -cmp;
      // Stable tiebreak: district, then ps_name — so identical fir_counts
      // keep a deterministic A→Z order rather than jumping between renders.
      return cmp
        || a.district.localeCompare(b.district)
        || a.ps_name.localeCompare(b.ps_name);
    });
    return copy;
  }, [rows, sortBy, sortDir]);

  const grandTotal = useMemo(
    () => rows.reduce((s, r) => s + r.fir_count, 0),
    [rows]);
  const grandYesterday = useMemo(
    () => rows.reduce((s, r) => s + r.yesterday_count, 0),
    [rows]);
  const yestLabel = yesterdayShortLabel();

  const handleDownload = async (kind: 'pdf' | 'xlsx') => {
    setDl(kind);
    try {
      if (kind === 'pdf') await downloadFirPsPerformancePdf(from, to);
      else await downloadFirPsPerformanceExcel(from, to);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : `Failed to download ${kind.toUpperCase()}`);
    } finally {
      setDl(null);
    }
  };

  const arrow = (k: SortKey) =>
    sortBy === k ? <span className="ml-1 opacity-80">{sortDir === 'asc' ? '▲' : '▼'}</span> : null;

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-4 mb-4">
        <div>
          <h1 className="text-[22px] font-bold flex items-center gap-2"
            style={{ color: 'var(--ksp-navy)', letterSpacing: '-0.02em' }}>
            <BarChart3 className="w-6 h-6" /> FIR Dashboard
          </h1>
          <p className="text-sm font-medium" style={{ color: 'var(--ksp-red)' }}>
            PS performance — FIRs registered in the selected date range.
          </p>
        </div>
        {/* Download buttons — page-level action, always top-right so
             they don't shift around when the table header wraps. */}
        <div className="flex gap-2 ml-auto">
          <button type="button"
            onClick={() => handleDownload('xlsx')}
            disabled={dl !== null || busy || rows.length === 0}
            title="Download this table as an Excel (.xlsx) file"
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-bold transition disabled:opacity-50"
            style={{ background: '#0a5c2a', color: '#fff' }}>
            <FileSpreadsheet className="w-3.5 h-3.5" />
            {dl === 'xlsx' ? 'Generating…' : 'Excel'}
          </button>
          <button type="button"
            onClick={() => handleDownload('pdf')}
            disabled={dl !== null || busy || rows.length === 0}
            title="Download this table as a PDF file"
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-bold transition disabled:opacity-50"
            style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}>
            <FileDown className="w-3.5 h-3.5" />
            {dl === 'pdf' ? 'Generating…' : 'PDF'}
          </button>
        </div>
      </div>

      {/* Date window controls */}
      <div className="rounded-2xl p-4 mb-5 flex flex-wrap gap-3 items-end"
        style={cardStyle}>
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
        <div className="flex gap-2 ml-auto flex-wrap">
          {[1, 7, 30, 90].map((n) => (
            <button key={n} type="button"
              onClick={() => { setFrom(isoNDaysAgo(n - 1)); setTo(todayISO()); }}
              className="px-3 py-2 text-xs font-semibold rounded-lg"
              style={{ background: 'rgba(11,44,74,0.06)', color: 'var(--ksp-navy)' }}>
              {n === 1 ? 'Today' : `Last ${n} days`}
            </button>
          ))}
        </div>
      </div>

      {/* PS-performance table */}
      <div className="rounded-2xl overflow-x-auto" style={cardStyle}>
        <div className="px-5 py-4 flex items-start justify-between gap-4 flex-wrap"
          style={{ borderBottom: '3px solid var(--ksp-yellow)' }}>
          <div className="min-w-0">
            <h3 className="text-sm font-bold" style={{ color: 'var(--ksp-navy)' }}>
              FIRs registered per PS
            </h3>
            <p className="text-xs mt-1 opacity-60">
              Window: {from} → {to}. Click a column header to sort — click again to reverse.
              Zero-count PSes are shown so silent stations stay visible.
            </p>
          </div>

          <div className="flex gap-6 text-right">
            <div>
              <p className="text-[11px] uppercase tracking-wide font-bold"
                style={{ color: '#0a6b28' }}>Yesterday ({yestLabel})</p>
              <p className="text-xl font-bold" style={{ color: '#0a6b28' }}>
                {fmtInt(grandYesterday)}
              </p>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-wide font-bold"
                style={{ color: 'var(--ksp-red)' }}>Grand Total</p>
              <p className="text-xl font-bold" style={{ color: 'var(--ksp-navy)' }}>
                {fmtInt(grandTotal)}
              </p>
            </div>
          </div>
        </div>

        <table className="w-full text-sm text-left">
          <thead style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}>
            <tr>
              <th className="px-4 py-3 text-xs uppercase font-bold">#</th>
              <th className="px-4 py-3 text-xs uppercase font-bold"
                style={{ cursor: 'pointer', userSelect: 'none' }}
                onClick={() => onSort('district')}
                title="Sort by District">
                District{arrow('district')}
              </th>
              <th className="px-4 py-3 text-xs uppercase font-bold"
                style={{ cursor: 'pointer', userSelect: 'none' }}
                onClick={() => onSort('ps_name')}
                title="Sort by Police Station">
                Police Station{arrow('ps_name')}
              </th>
              <th className="px-4 py-3 text-xs uppercase font-bold text-right"
                style={{ cursor: 'pointer', userSelect: 'none' }}
                onClick={() => onSort('yesterday_count')}
                title={`FIRs registered yesterday (${yestLabel})`}>
                Yesterday ({yestLabel}){arrow('yesterday_count')}
              </th>
              <th className="px-4 py-3 text-xs uppercase font-bold text-right"
                style={{ cursor: 'pointer', userSelect: 'none' }}
                onClick={() => onSort('fir_count')}
                title="Sort by Total FIRs">
                Total FIRs{arrow('fir_count')}
              </th>
            </tr>
          </thead>
          <tbody>
            {busy && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center italic opacity-60">Loading…</td>
              </tr>
            )}
            {!busy && sortedRows.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center italic opacity-60">
                  No active PSes in scope.
                </td>
              </tr>
            )}
            {!busy && sortedRows.map((r, i) => (
              <tr key={`${r.unit_id}-${r.ps_id}`}
                className="border-t hover:bg-[#fff3b0]/30"
                style={{ borderColor: 'rgba(0,0,0,0.06)' }}>
                <td className="px-4 py-2 opacity-50">{i + 1}</td>
                <td className="px-4 py-2 font-semibold" style={{ color: 'var(--ksp-navy)' }}>
                  {r.district}
                </td>
                <td className="px-4 py-2" style={{ color: 'var(--ksp-navy)' }}>
                  {r.ps_name || '—'}
                </td>
                <td className="px-4 py-2 text-right font-bold"
                  style={{ color: r.yesterday_count === 0 ? 'rgba(0,0,0,0.35)' : '#0a6b28' }}>
                  {fmtInt(r.yesterday_count)}
                </td>
                <td className="px-4 py-2 text-right font-bold"
                  style={{ color: r.fir_count === 0 ? 'var(--ksp-red)' : 'var(--ksp-navy)' }}>
                  {fmtInt(r.fir_count)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
