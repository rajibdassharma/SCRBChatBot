import { useState } from 'react';
import { toast } from 'sonner';
import { FileDown, FileSpreadsheet, Globe } from 'lucide-react';
import {
  downloadPortalsDsrDailyExcel,
  downloadPortalsDsrDailyPdf,
} from '../lib/api/reports';

/** Portals DSR daily report -- one-page picker that lets the operator
 *  (admin+) pick a date and download the PS-wise portal counters as
 *  Excel or PDF. Layout mirrors the paper form the operators submit
 *  today (all 45 PSes always shown, one row each, 25 metric columns
 *  grouped by portal).
 *
 *  Defaults to yesterday because the report is almost always pulled
 *  the next morning to reconcile the previous day's submissions.
 */

function yesterdayISO(): string {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return d.toISOString().slice(0, 10);
}

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

const cardStyle = {
  background: '#fff',
  border: '1px solid rgba(0,0,0,0.06)',
  boxShadow: '0 6px 16px rgba(0,0,0,0.08)',
};

export function PortalsDsrReportPage() {
  const [date, setDate] = useState(yesterdayISO());
  const [dl, setDl] = useState<'pdf' | 'xlsx' | null>(null);

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

  return (
    <div>
      <div className="mb-4">
        <h1 className="text-[22px] font-bold flex items-center gap-2"
          style={{ color: 'var(--ksp-navy)', letterSpacing: '-0.02em' }}>
          <Globe className="w-6 h-6" /> Portals DSR Report
        </h1>
        <p className="text-sm font-medium" style={{ color: 'var(--ksp-red)' }}>
          Police-station-wise counters across all 8 external portals for a single date.
          Matches the paper submission format. Defaults to yesterday.
        </p>
      </div>

      <div className="rounded-2xl p-5 max-w-2xl" style={cardStyle}>
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="block text-xs font-semibold mb-1"
              style={{ color: 'var(--ksp-navy)' }}>Report date</label>
            <input type="date" value={date} max={todayISO()}
              onChange={(e) => setDate(e.target.value)}
              className="px-3 py-2 rounded-xl text-sm outline-none"
              style={{ border: '2px solid var(--ksp-navy)', background: '#fff' }} />
          </div>
          <button type="button"
            onClick={() => setDate(yesterdayISO())}
            className="px-3 py-2 text-xs font-semibold rounded-lg"
            style={{ background: 'rgba(11,44,74,0.06)', color: 'var(--ksp-navy)' }}>
            Yesterday
          </button>
        </div>

        <div className="flex flex-wrap gap-3 mt-5">
          <button type="button"
            onClick={() => handle('xlsx')}
            disabled={dl !== null}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-bold transition disabled:opacity-50"
            style={{ background: '#0a5c2a', color: '#fff' }}>
            <FileSpreadsheet className="w-4 h-4" />
            {dl === 'xlsx' ? 'Generating…' : 'Download Excel'}
          </button>
          <button type="button"
            onClick={() => handle('pdf')}
            disabled={dl !== null}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-bold transition disabled:opacity-50"
            style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}>
            <FileDown className="w-4 h-4" />
            {dl === 'pdf' ? 'Generating…' : 'Download PDF'}
          </button>
        </div>

        <p className="text-xs opacity-60 mt-4">
          Report includes all 45 active Cyber Crime PSes. Blank cells indicate no submission for that PS on the selected date. Only rows with status = "submitted" are counted; drafts are excluded.
        </p>
      </div>
    </div>
  );
}
