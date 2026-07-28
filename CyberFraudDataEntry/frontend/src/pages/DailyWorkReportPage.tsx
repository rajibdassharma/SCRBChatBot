import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { ClipboardList, FileDown, FileSpreadsheet } from 'lucide-react';
import {
  downloadDailyWorkDailyExcel,
  downloadDailyWorkDailyPdf,
  fetchDailyWorkDailyPreview,
} from '../lib/api/reports';
import { todayISO, yesterdayISO } from '../lib/utils/format';
import type { DailyWorkDailyPreviewRow } from '../types';

/** Daily Work Done report -- date picker, on-screen preview
 *  (per-PS totals), 2 download buttons. Defaults to yesterday.
 *
 *  todayISO / yesterdayISO imported from the shared helper -- the
 *  old local copies used .toISOString() which drops back a day at
 *  IST midnight. */
function fmtNum(v: number | null | undefined): string {
  if (v === null || v === undefined || v === 0) return '';
  return v.toLocaleString('en-IN');
}
function fmtAmt(v: number | null | undefined): string {
  if (v === null || v === undefined || v === 0) return '';
  return Math.round(v).toLocaleString('en-IN');
}

const cardStyle = {
  background: '#fff',
  border: '1px solid rgba(0,0,0,0.06)',
  boxShadow: '0 6px 16px rgba(0,0,0,0.08)',
};

// Colour bands match the paper form: red / yellow / green.
const RED = '#b10000';
const YEL = '#c67c1d';
const GRN = '#0a6b28';

type ColDef = {
  label: string;
  key: keyof DailyWorkDailyPreviewRow;
  isAmount?: boolean;
};

const GROUPS: { name: string; colour: string; cols: ColDef[] }[] = [
  { name: 'Notices', colour: RED, cols: [
    { label: '35(3)/41A',            key: 'notices_35_41a_count' },
    { label: '91/92/94 — Banks',     key: 'notices_91_92_94_banks' },
    { label: '91/92/94 — Intermed.', key: 'notices_91_92_94_intermediary' },
    { label: '91/92/94 — Acc. Hldr', key: 'notices_91_92_94_account_holder' },
    { label: '91/92/94 — CDR/IPDR',  key: 'notices_91_92_94_cdr_ipdr' },
  ]},
  { name: 'Lien / Unlien', colour: YEL, cols: [
    { label: 'Lien Req',    key: 'lien_requests_count' },
    { label: 'Freeze Req',  key: 'freeze_requests_count' },
    { label: 'Lien Amount', key: 'total_lien_amount', isAmount: true },
    { label: 'Unlien Req',  key: 'unlien_requests_count' },
    { label: 'Defreeze Req',key: 'defreeze_requests_count' },
    { label: 'Unlien Amt',  key: 'total_unlien_amount', isAmount: true },
  ]},
  { name: 'Outcomes', colour: GRN, cols: [
    { label: 'Arrests',       key: 'arrests_count' },
    { label: 'Statements',    key: 'statements_count' },
    { label: 'Final (A/B/C)', key: 'final_report_abc' },
  ]},
];

const TOTAL_COLS = 3 + GROUPS.reduce((s, g) => s + g.cols.length, 0);

export function DailyWorkReportPage() {
  const [date, setDate] = useState(yesterdayISO());
  const [dl, setDl] = useState<'pdf' | 'xlsx' | null>(null);
  const [rows, setRows] = useState<DailyWorkDailyPreviewRow[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchDailyWorkDailyPreview(date)
      .then((r) => { if (!cancelled) setRows(r); })
      .catch((e) => toast.error(e instanceof Error ? e.message : 'Preview failed'))
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [date]);

  const handle = async (kind: 'pdf' | 'xlsx') => {
    setDl(kind);
    try {
      if (kind === 'pdf') await downloadDailyWorkDailyPdf(date);
      else await downloadDailyWorkDailyExcel(date);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : `${kind.toUpperCase()} download failed`);
    } finally {
      setDl(null);
    }
  };

  const totalFirCount = rows.reduce((s, r) => s + (r.fir_count || 0), 0);
  const submittedPsCount = rows.filter((r) => r.fir_count > 0).length;

  return (
    <div>
      <div className="mb-4">
        <h1 className="text-[22px] font-bold flex items-center gap-2"
          style={{ color: 'var(--ksp-navy)', letterSpacing: '-0.02em' }}>
          <ClipboardList className="w-6 h-6" /> Daily Work Done Report
        </h1>
        <p className="text-sm font-medium" style={{ color: 'var(--ksp-red)' }}>
          Police-station-wise totals of investigation activity (notices, lien/unlien, arrests, statements, final reports) for a single date. Preview below.
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
            : `${submittedPsCount} of ${rows.length} PSes logged activity · ${totalFirCount} FIRs worked on. Blank cells = no activity for that PS.`}
        </p>
      </div>

      {/* Preview table — 17 cols with red/yellow/green grouped headers. */}
      <div className="rounded-2xl overflow-x-auto" style={cardStyle}>
        <table className="w-full text-xs" style={{ borderCollapse: 'collapse' }}>
          <thead>
            {/* Group row */}
            <tr style={{ color: '#fff' }}>
              <th rowSpan={2} className="px-2 py-2 text-center font-bold sticky left-0 z-10"
                style={{ background: 'var(--ksp-navy)', minWidth: 40 }}>#</th>
              <th rowSpan={2} className="px-2 py-2 text-left font-bold sticky z-10"
                style={{ background: 'var(--ksp-navy)', left: 40, minWidth: 200 }}>Police Station</th>
              <th rowSpan={2} className="px-2 py-2 text-center font-bold sticky z-10"
                style={{ background: 'var(--ksp-navy)', left: 240, minWidth: 60 }}>FIR Count</th>
              {GROUPS.map((g) => (
                <th key={g.name} colSpan={g.cols.length}
                  className="px-2 py-2 text-center font-bold border-l border-white/20"
                  style={{ background: g.colour }}>
                  {g.name}
                </th>
              ))}
            </tr>
            {/* Metric row */}
            <tr style={{ background: '#1c4267', color: '#fff' }}>
              {GROUPS.flatMap((g) =>
                g.cols.map((c, i) => (
                  <th key={`${g.name}-${String(c.key)}`}
                    className={`px-1.5 py-1.5 text-center font-semibold whitespace-nowrap ${i === 0 ? 'border-l border-white/20' : ''}`}
                    style={{ minWidth: 80, fontSize: 10 }}>
                    {c.label}
                  </th>
                )),
              )}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={TOTAL_COLS} className="px-4 py-6 text-center italic opacity-60">Loading…</td></tr>
            )}
            {!loading && rows.length === 0 && (
              <tr><td colSpan={TOTAL_COLS} className="px-4 py-6 text-center italic opacity-60">No PSes active.</td></tr>
            )}
            {!loading && rows.map((r, i) => {
              const bg = i % 2 === 0 ? '#fff' : '#f5f5f7';
              return (
                <tr key={r.ps_id} className="border-t" style={{ borderColor: 'rgba(0,0,0,0.06)' }}>
                  <td className="px-2 py-1.5 text-center opacity-60 sticky left-0"
                    style={{ background: bg }}>{i + 1}</td>
                  <td className="px-2 py-1.5 font-semibold sticky"
                    style={{ color: 'var(--ksp-navy)', background: bg, left: 40 }}>
                    {r.ps_name}
                  </td>
                  <td className="px-2 py-1.5 text-right font-bold sticky"
                    style={{ color: r.fir_count > 0 ? 'var(--ksp-navy)' : 'rgba(0,0,0,0.25)', background: bg, left: 240 }}>
                    {fmtNum(r.fir_count)}
                  </td>
                  {GROUPS.flatMap((g) =>
                    g.cols.map((c, j) => {
                      const raw = r[c.key];
                      const isBlank = raw === null || raw === undefined || raw === 0 || raw === '';
                      let display: string;
                      if (typeof raw === 'string') display = raw;
                      else if (c.isAmount) display = fmtAmt(raw as number | null);
                      else display = fmtNum(raw as number | null);
                      return (
                        <td key={`${g.name}-${String(c.key)}`}
                          className={`px-1.5 py-1.5 text-right ${j === 0 ? 'border-l' : ''}`}
                          style={{
                            borderColor: 'rgba(0,0,0,0.06)',
                            background: bg,
                            color: isBlank ? 'rgba(0,0,0,0.25)' : 'var(--ksp-navy)',
                            fontWeight: isBlank ? 400 : 700,
                          }}>
                          {display}
                        </td>
                      );
                    }),
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
