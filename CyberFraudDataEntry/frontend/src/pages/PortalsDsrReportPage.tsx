import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { FileDown, FileSpreadsheet, Globe } from 'lucide-react';
import {
  downloadPortalsDsrDailyExcel,
  downloadPortalsDsrDailyPdf,
  fetchPortalsDsrDailyPreview,
} from '../lib/api/reports';
import type { PortalsDsrDailyPreviewRow } from '../types';

/** Portals DSR daily report -- date picker, on-screen preview table
 *  (same shape as the downloadable Excel/PDF), and 2 download buttons.
 *
 *  Defaults to yesterday: the report is almost always pulled the next
 *  morning to reconcile the previous day's submissions.
 */

function yesterdayISO(): string {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return d.toISOString().slice(0, 10);
}
function todayISO(): string { return new Date().toISOString().slice(0, 10); }

const cardStyle = {
  background: '#fff',
  border: '1px solid rgba(0,0,0,0.06)',
  boxShadow: '0 6px 16px rgba(0,0,0,0.08)',
};

// Column groups -- mirror the paper form + PDF/XLSX renderer exactly.
type Col = { label: string; key: keyof PortalsDsrDailyPreviewRow };
const GROUPS: { name: string; cols: Col[] }[] = [
  { name: 'NCRP', cols: [
    { label: 'Recv', key: 'ncrp_received' },
    { label: 'Disp', key: 'ncrp_disposed' },
    { label: 'Pend', key: 'ncrp_pending' },
  ]},
  { name: 'Samanvaya', cols: [
    { label: 'Req Recv',   key: 'samanvaya_request_received' },
    { label: 'Actions',    key: 'samanvaya_actions' },
    { label: 'Act Pend',   key: 'samanvaya_action_pending' },
    { label: 'Req Sent',   key: 'samanvaya_request_sent' },
    { label: 'Reply Recv', key: 'samanvaya_reply_received' },
    { label: 'Rep Pend',   key: 'samanvaya_replies_pending' },
  ]},
  { name: 'Sahayog', cols: [
    { label: 'Unlawful',     key: 'sahayog_unlawful_content_removal' },
    { label: 'Intermediary', key: 'sahayog_intermediary_requests' },
    { label: 'Crypto',       key: 'sahayog_crypto_requests' },
  ]},
  { name: 'GRM', cols: [
    { label: 'Req Recv', key: 'grm_request_received' },
    { label: 'Action',   key: 'grm_action' },
    { label: 'Pending',  key: 'grm_pending' },
  ]},
  { name: 'MRM', cols: [
    { label: 'Req Recv', key: 'mrm_request_received' },
    { label: 'Action',   key: 'mrm_action' },
    { label: 'Pending',  key: 'mrm_pending' },
  ]},
  { name: 'Bharatpol', cols: [
    { label: 'Req Sent', key: 'bharatpol_request_received' },
  ]},
  { name: 'OCWC', cols: [
    { label: 'Recv', key: 'ocwc_received' },
    { label: 'Disp', key: 'ocwc_disposed' },
    { label: 'Pend', key: 'ocwc_pending' },
  ]},
  { name: 'NCMEC', cols: [
    { label: 'Recv', key: 'ncmec_received' },
    { label: 'Disp', key: 'ncmec_disposed' },
    { label: 'Pend', key: 'ncmec_pending' },
  ]},
];

export function PortalsDsrReportPage() {
  const [date, setDate] = useState(yesterdayISO());
  const [dl, setDl] = useState<'pdf' | 'xlsx' | null>(null);
  const [rows, setRows] = useState<PortalsDsrDailyPreviewRow[]>([]);
  const [loading, setLoading] = useState(false);

  // Auto-fetch preview whenever the date changes.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchPortalsDsrDailyPreview(date)
      .then((r) => { if (!cancelled) setRows(r); })
      .catch((e) => toast.error(e instanceof Error ? e.message : 'Preview failed'))
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [date]);

  const handle = async (kind: 'pdf' | 'xlsx') => {
    setDl(kind);
    try {
      if (kind === 'pdf') await downloadPortalsDsrDailyPdf(date);
      else await downloadPortalsDsrDailyExcel(date);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : `${kind.toUpperCase()} download failed`);
    } finally {
      setDl(null);
    }
  };

  const submittedPsCount = rows.filter(
    (r) => r.ncrp_received !== null || r.samanvaya_request_received !== null,
  ).length;

  return (
    <div>
      <div className="mb-4">
        <h1 className="text-[22px] font-bold flex items-center gap-2"
          style={{ color: 'var(--ksp-navy)', letterSpacing: '-0.02em' }}>
          <Globe className="w-6 h-6" /> Portals DSR Report
        </h1>
        <p className="text-sm font-medium" style={{ color: 'var(--ksp-red)' }}>
          Police-station-wise counters across all 8 external portals for a single date. Preview below; download as Excel or PDF.
        </p>
      </div>

      <div className="rounded-2xl p-5 mb-5" style={cardStyle}>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs font-semibold mb-1"
              style={{ color: 'var(--ksp-navy)' }}>Report date</label>
            <input type="date" value={date} max={todayISO()}
              onChange={(e) => setDate(e.target.value)}
              className="px-3 py-2 rounded-xl text-sm outline-none"
              style={{ border: '2px solid var(--ksp-navy)', background: '#fff' }} />
          </div>
          <button type="button" onClick={() => setDate(yesterdayISO())}
            className="px-3 py-2 text-xs font-semibold rounded-lg"
            style={{ background: 'rgba(11,44,74,0.06)', color: 'var(--ksp-navy)' }}>
            Yesterday
          </button>
          <div className="flex-1" />
          <button type="button" onClick={() => handle('xlsx')}
            disabled={dl !== null || loading}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-bold transition disabled:opacity-50"
            style={{ background: '#0a5c2a', color: '#fff' }}>
            <FileSpreadsheet className="w-3.5 h-3.5" />
            {dl === 'xlsx' ? 'Generating…' : 'Excel'}
          </button>
          <button type="button" onClick={() => handle('pdf')}
            disabled={dl !== null || loading}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-bold transition disabled:opacity-50"
            style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}>
            <FileDown className="w-3.5 h-3.5" />
            {dl === 'pdf' ? 'Generating…' : 'PDF'}
          </button>
        </div>
        <p className="text-xs opacity-60 mt-3">
          {loading
            ? 'Loading preview…'
            : `${submittedPsCount} of ${rows.length} PSes submitted. Blank cells = no submission for that PS. Drafts excluded.`}
        </p>
      </div>

      {/* Preview table — matches the paper form + downloadable file
           layout. Wide (27 cols) so wrapped in overflow-x scroll. */}
      <div className="rounded-2xl overflow-x-auto" style={cardStyle}>
        <table className="w-full text-xs" style={{ borderCollapse: 'collapse' }}>
          <thead>
            {/* Group row */}
            <tr style={{ background: 'var(--ksp-navy)', color: '#fff' }}>
              <th rowSpan={2} className="px-2 py-2 text-center font-bold sticky left-0 z-10"
                style={{ background: 'var(--ksp-navy)', minWidth: 40 }}>#</th>
              <th rowSpan={2} className="px-2 py-2 text-left font-bold sticky z-10"
                style={{ background: 'var(--ksp-navy)', left: 40, minWidth: 200 }}>Police Station</th>
              {GROUPS.map((g) => (
                <th key={g.name} colSpan={g.cols.length}
                  className="px-2 py-2 text-center font-bold border-l border-white/20">
                  {g.name}
                </th>
              ))}
            </tr>
            {/* Metric row */}
            <tr style={{ background: '#1c4267', color: '#fff' }}>
              {GROUPS.flatMap((g) =>
                g.cols.map((c, i) => (
                  <th key={`${g.name}-${c.key}`}
                    className={`px-1.5 py-1.5 text-center font-semibold whitespace-nowrap ${i === 0 ? 'border-l border-white/20' : ''}`}
                    style={{ minWidth: 52, fontSize: 10 }}>
                    {c.label}
                  </th>
                )),
              )}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={27} className="px-4 py-6 text-center italic opacity-60">Loading…</td></tr>
            )}
            {!loading && rows.length === 0 && (
              <tr><td colSpan={27} className="px-4 py-6 text-center italic opacity-60">No PSes active.</td></tr>
            )}
            {!loading && rows.map((r, i) => (
              <tr key={r.ps_id} className="border-t" style={{ borderColor: 'rgba(0,0,0,0.06)' }}>
                <td className="px-2 py-1.5 text-center opacity-60 sticky left-0"
                  style={{ background: i % 2 === 0 ? '#fff' : '#f5f5f7' }}>{i + 1}</td>
                <td className="px-2 py-1.5 font-semibold sticky"
                  style={{ color: 'var(--ksp-navy)', background: i % 2 === 0 ? '#fff' : '#f5f5f7', left: 40 }}>
                  {r.ps_name}
                </td>
                {GROUPS.flatMap((g) =>
                  g.cols.map((c, j) => {
                    // GROUPS only references numeric metric keys, but
                    // keyof PortalsDsrDailyPreviewRow includes string
                    // fields too (ps_name, district) — TS can't narrow
                    // through the union, so cast at the read.
                    const v = r[c.key] as number | null;
                    return (
                      <td key={`${g.name}-${c.key}`}
                        className={`px-1.5 py-1.5 text-right ${j === 0 ? 'border-l' : ''}`}
                        style={{
                          borderColor: 'rgba(0,0,0,0.06)',
                          background: i % 2 === 0 ? '#fff' : '#f5f5f7',
                          color: v === null ? 'rgba(0,0,0,0.25)' : 'var(--ksp-navy)',
                          fontWeight: v !== null && v > 0 ? 700 : 400,
                        }}>
                        {v === null ? '' : v}
                      </td>
                    );
                  }),
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
