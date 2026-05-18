import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { FileDown, Calendar, MapPin, Building2, Hash, FileText, ClipboardList, Coins } from 'lucide-react';
import { downloadDsrPdf, downloadMulePdf, downloadCasePdf } from '../lib/api/reports';
import { useAuthStore } from '../lib/stores/auth-store';

/**
 * Reports page — tabbed UX. Each tab is one report type and gets its
 * own input controls. Same content as the previous stacked layout,
 * just easier to scan.
 */
type Tab = 'dsr' | 'case' | 'mule';

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: 'dsr',  label: 'DSR Report',         icon: <ClipboardList className="w-4 h-4" /> },
  { id: 'case', label: 'Case File Report',   icon: <FileText className="w-4 h-4" /> },
  { id: 'mule', label: 'Mule Account Report', icon: <Coins className="w-4 h-4" /> },
];


export function ReportsPage() {
  const [tab, setTab] = useState<Tab>('dsr');

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-1" style={{ color: 'var(--ksp-navy)' }}>Reports</h1>
      <p className="text-sm mb-5" style={{ color: 'var(--ksp-red)' }}>
        Download PDF reports
      </p>

      {/* Tab strip */}
      <div className="flex gap-1 mb-5 border-b-2" style={{ borderColor: 'var(--ksp-navy)' }}>
        {TABS.map(t => {
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className="flex items-center gap-2 px-4 py-2.5 text-sm font-bold rounded-t-lg transition -mb-[2px]"
              style={
                active
                  ? { background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)', border: '2px solid var(--ksp-navy)', borderBottom: '2px solid var(--ksp-navy)' }
                  : { background: 'transparent', color: 'var(--ksp-navy)', border: '2px solid transparent' }
              }
            >
              {t.icon}
              {t.label}
            </button>
          );
        })}
      </div>

      {tab === 'dsr'  && <DsrSection />}
      {tab === 'case' && <CaseFileSection />}
      {tab === 'mule' && <MuleReportSection />}
    </div>
  );
}


// ── DSR (date-range, district + PS aware) ────────────────────────────


type PsRow = { id: number; district_name: string; station_name: string };

const DISTRICT_OWN = '__OWN__';
const DISTRICT_ALL = '__ALL__';
const PS_ALL_IN_DISTRICT = 0;


function DsrSection() {
  const { user } = useAuthStore();
  const isSuperAdmin = user?.role === 'super_admin';

  const today = new Date().toISOString().slice(0, 10);
  const [dateFrom, setDateFrom] = useState(today);
  const [dateTo, setDateTo] = useState(today);

  const [district, setDistrict] = useState<string>(DISTRICT_OWN);
  const [psId, setPsId] = useState<number>(PS_ALL_IN_DISTRICT);
  const [psOptions, setPsOptions] = useState<PsRow[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!isSuperAdmin) return;
    const base = import.meta.env.VITE_API_BASE ?? '';
    fetch(`${base}/api/v1/police-stations/public`)
      .then(r => r.ok ? r.json() : [])
      .then((rows: PsRow[]) => setPsOptions(rows))
      .catch(() => setPsOptions([]));
  }, [isSuperAdmin]);

  const districts = useMemo(() => {
    const seen = new Set<string>();
    for (const p of psOptions) seen.add(p.district_name);
    return Array.from(seen).sort();
  }, [psOptions]);

  const psInDistrict = useMemo(() => {
    if (district === DISTRICT_OWN || district === DISTRICT_ALL) return [];
    return psOptions
      .filter(p => p.district_name === district)
      .sort((a, b) => a.station_name.localeCompare(b.station_name));
  }, [psOptions, district]);

  useEffect(() => { setPsId(PS_ALL_IN_DISTRICT); }, [district]);

  async function run() {
    if (dateTo < dateFrom) {
      toast.error('"To" date must be on or after "From" date');
      return;
    }
    setBusy(true);
    try {
      const opts: { psId?: number; district?: string } = {};
      if (isSuperAdmin) {
        if (district === DISTRICT_OWN) {
          // No params → backend defaults to super_admin's own PS
        } else if (district === DISTRICT_ALL) {
          opts.psId = 0;
        } else if (psId === PS_ALL_IN_DISTRICT) {
          opts.district = district;
        } else {
          opts.psId = psId;
        }
      }
      await downloadDsrPdf(dateFrom, dateTo, opts);
      toast.success('DSR downloaded');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Download failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <ReportCard
      title="Daily Status Report (DSR)"
      description={
        isSuperAdmin
          ? 'Aggregate of cases, arrests, petitions, lien accounts, refunds and mule reports created in the selected period. Pick any single PS, an entire district, or all police stations.'
          : 'Aggregate of cases, arrests, petitions, lien accounts, refunds and mule reports created in the selected period for your police station.'
      }
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        <DateField label="From" value={dateFrom} max={today} onChange={setDateFrom} />
        <DateField label="To" value={dateTo} max={today} onChange={setDateTo} />
      </div>

      {isSuperAdmin && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
          <div>
            <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>
              District
            </label>
            <div className="flex items-center gap-2">
              <MapPin className="w-4 h-4" style={{ color: 'var(--ksp-navy)' }} />
              <select
                value={district}
                onChange={e => setDistrict(e.target.value)}
                className="flex-1 px-3 py-2 rounded-lg text-sm outline-none bg-white"
                style={{ border: '2px solid var(--ksp-navy)' }}
              >
                <option value={DISTRICT_OWN}>My District (defaults to my PS)</option>
                <option value={DISTRICT_ALL}>— All Districts (every PS combined) —</option>
                <optgroup label="Specific district">
                  {districts.map(d => <option key={d} value={d}>{d}</option>)}
                </optgroup>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>
              Police Station
            </label>
            <div className="flex items-center gap-2">
              <Building2 className="w-4 h-4" style={{ color: 'var(--ksp-navy)' }} />
              <select
                value={psId}
                onChange={e => setPsId(Number(e.target.value))}
                disabled={district === DISTRICT_OWN || district === DISTRICT_ALL}
                className="flex-1 px-3 py-2 rounded-lg text-sm outline-none bg-white disabled:bg-gray-100 disabled:text-gray-500"
                style={{ border: '2px solid var(--ksp-navy)' }}
              >
                <option value={PS_ALL_IN_DISTRICT}>
                  {district === DISTRICT_OWN || district === DISTRICT_ALL
                    ? '(pick a district first)'
                    : `— All PSes in ${district} —`}
                </option>
                {psInDistrict.map(p => (
                  <option key={p.id} value={p.id}>{p.station_name}</option>
                ))}
              </select>
            </div>
          </div>
        </div>
      )}

      <DownloadButton onClick={run} busy={busy} disabled={!dateFrom || !dateTo} />
    </ReportCard>
  );
}


// ── Case File Report ─────────────────────────────────────────────────


function CaseFileSection() {
  const [lookupBy, setLookupBy] = useState<'fir' | 'petition'>('fir');
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);

  async function run() {
    const v = value.trim();
    if (!v) {
      toast.error(`Enter a ${lookupBy === 'fir' ? 'FIR' : 'petition'} number`);
      return;
    }
    setBusy(true);
    try {
      await downloadCasePdf(lookupBy === 'fir' ? { firNo: v } : { petitionNo: v });
      toast.success('Case file downloaded');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Download failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <ReportCard
      title="Case File Report"
      description="Full case dossier — header, facts, arrests (with accomplices and accused details), petitions, lien accounts, unfreeze records, and refunds."
    >
      <div className="flex items-end gap-3 flex-wrap">
        <div>
          <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>
            Lookup by
          </label>
          <select
            value={lookupBy}
            onChange={e => setLookupBy(e.target.value as 'fir' | 'petition')}
            className="px-3 py-2 rounded-lg text-sm outline-none bg-white"
            style={{ border: '2px solid var(--ksp-navy)' }}
          >
            <option value="fir">FIR Number</option>
            <option value="petition">Petition Number</option>
          </select>
        </div>
        <div className="flex-1 min-w-[240px]">
          <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>
            {lookupBy === 'fir' ? 'FIR Number' : 'Petition Number'}
          </label>
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4" style={{ color: 'var(--ksp-navy)' }} />
            <input
              type="text"
              value={value}
              onChange={e => setValue(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') run(); }}
              placeholder={lookupBy === 'fir' ? 'e.g. CR-12/2026' : 'e.g. P-5/2026'}
              className="flex-1 px-3 py-2 rounded-lg text-sm outline-none font-mono"
              style={{ border: '2px solid var(--ksp-navy)' }}
            />
          </div>
        </div>
        <DownloadButton onClick={run} busy={busy} disabled={!value.trim()} />
      </div>
    </ReportCard>
  );
}


// ── Mule Report (lookup by acknowledgement no) ───────────────────────


function MuleReportSection() {
  const [ackNo, setAckNo] = useState('');
  const [busy, setBusy] = useState(false);

  async function run() {
    const v = ackNo.trim();
    if (!v) {
      toast.error('Enter an acknowledgement number');
      return;
    }
    setBusy(true);
    try {
      await downloadMulePdf(v);
      toast.success('Mule report downloaded');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Download failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <ReportCard
      title="Mule Account Report"
      description="One full report — header details plus all six transaction tables (Money Transfers, Other Transactions, On-Hold, < ₹500, AEPS, ATM). Landscape layout."
    >
      <div className="flex items-end gap-3 flex-wrap">
        <div className="flex-1 min-w-[240px]">
          <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>
            Acknowledgement Number
          </label>
          <div className="flex items-center gap-2">
            <Hash className="w-4 h-4" style={{ color: 'var(--ksp-navy)' }} />
            <input
              type="text"
              value={ackNo}
              onChange={e => setAckNo(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') run(); }}
              placeholder="e.g. 21612250083721"
              className="flex-1 px-3 py-2 rounded-lg text-sm outline-none font-mono"
              style={{ border: '2px solid var(--ksp-navy)' }}
            />
          </div>
        </div>
        <DownloadButton onClick={run} busy={busy} disabled={!ackNo.trim()} />
      </div>
    </ReportCard>
  );
}


// ── Helpers ──────────────────────────────────────────────────────────


function DateField({
  label, value, max, onChange,
}: {
  label: string; value: string; max?: string; onChange: (v: string) => void;
}) {
  return (
    <div>
      <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>{label}</label>
      <div className="flex items-center gap-1">
        <Calendar className="w-4 h-4" style={{ color: 'var(--ksp-navy)' }} />
        <input
          type="date"
          value={value}
          max={max}
          onChange={e => onChange(e.target.value)}
          className="flex-1 px-3 py-2 rounded-lg text-sm outline-none"
          style={{ border: '2px solid var(--ksp-navy)' }}
        />
      </div>
    </div>
  );
}


function DownloadButton({ onClick, busy, disabled }: { onClick: () => void; busy: boolean; disabled?: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={busy || disabled}
      className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold disabled:opacity-50"
      style={{ background: 'var(--ksp-yellow)', color: '#000', border: '2px solid rgba(0,0,0,0.25)' }}
    >
      <FileDown className="w-4 h-4" />
      {busy ? 'Generating…' : 'Download PDF'}
    </button>
  );
}


function ReportCard({
  title, description, children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl bg-white shadow p-5" style={{ border: '2px solid var(--ksp-navy)' }}>
      <h2 className="text-lg font-bold mb-1" style={{ color: 'var(--ksp-navy)' }}>{title}</h2>
      <p className="text-xs text-gray-600 mb-4">{description}</p>
      {children}
    </div>
  );
}
