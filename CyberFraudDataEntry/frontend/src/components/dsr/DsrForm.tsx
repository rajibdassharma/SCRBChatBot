import { useState, useEffect } from 'react';
import { useAuthStore } from '../../lib/stores/auth-store';
import { upsertDsr, getOwnDsr } from '../../lib/api/dsr';
import { todayISO } from '../../lib/utils/format';
import { Save, CheckCircle, ChevronRight, ChevronLeft } from 'lucide-react';

const NUM = (v: unknown) => Number(v) || 0;

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <div>
      <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>{label}</label>
      <input
        type="number"
        min={0}
        value={value || ''}
        onChange={(e) => onChange(NUM(e.target.value))}
        className="w-full px-3 py-2 rounded-xl text-sm outline-none"
        style={{ border: '2px solid var(--ksp-navy)', background: '#fff' }}
        placeholder="0"
      />
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl p-5" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
      <h3 className="text-sm font-bold mb-4 uppercase tracking-wide" style={{ color: 'var(--ksp-red)' }}>{title}</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">{children}</div>
    </div>
  );
}

const TABS = [
  { key: 'cases', label: 'Cases & Lien' },
  { key: 'pending', label: 'UI Cases Pending' },
  { key: 'disposal', label: 'Disposal & Trial' },
] as const;

export function DsrForm() {
  const { user } = useAuthStore();
  const [date, setDate] = useState(todayISO());
  const [tab, setTab] = useState(0);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const [loaded, setLoaded] = useState(false);

  const [f, setF] = useState({
    cases: 0, petitions: 0, details_of_arrest: 0,
    case_type: 'FIR',
    cumulative_amount_lien_marked: 0, cumulative_accounts_lien_marked: 0, cumulative_accounts_defreezed: 0,
    amount_refunded_to_victim: 0,
    ui_cases_pending_2021: 0, ui_cases_pending_2022: 0, ui_cases_pending_2023: 0,
    ui_cases_pending_2024: 0, ui_cases_pending_2025: 0, ui_cases_pending_2026: 0,
    disposed_detected_chargesheeted: 0, disposed_transferred: 0, disposed_false: 0, disposed_undetected: 0,
    trial_convicted: 0, trial_discharged: 0, trial_acquitted: 0,
    trial_abated: 0, trial_compounded: 0, trial_ut: 0,
  });

  const set = (key: string) => (v: number) => setF((p) => ({ ...p, [key]: v }));

  useEffect(() => {
    setLoaded(false);
    setSaved(false);
    getOwnDsr(date).then((entry) => {
      if (entry) {
        setF({
          cases: entry.cases, petitions: entry.petitions, details_of_arrest: entry.details_of_arrest,
          case_type: entry.case_type || 'FIR',
          cumulative_amount_lien_marked: Number(entry.cumulative_amount_lien_marked),
          cumulative_accounts_lien_marked: entry.cumulative_accounts_lien_marked,
          cumulative_accounts_defreezed: entry.cumulative_accounts_defreezed,
          amount_refunded_to_victim: Number(entry.amount_refunded_to_victim),
          ui_cases_pending_2021: entry.ui_cases_pending_2021, ui_cases_pending_2022: entry.ui_cases_pending_2022,
          ui_cases_pending_2023: entry.ui_cases_pending_2023, ui_cases_pending_2024: entry.ui_cases_pending_2024,
          ui_cases_pending_2025: entry.ui_cases_pending_2025, ui_cases_pending_2026: entry.ui_cases_pending_2026,
          disposed_detected_chargesheeted: entry.disposed_detected_chargesheeted,
          disposed_transferred: entry.disposed_transferred, disposed_false: entry.disposed_false,
          disposed_undetected: entry.disposed_undetected,
          trial_convicted: entry.trial_convicted, trial_discharged: entry.trial_discharged,
          trial_acquitted: entry.trial_acquitted, trial_abated: entry.trial_abated,
          trial_compounded: entry.trial_compounded, trial_ut: entry.trial_ut,
        });
      }
      setLoaded(true);
    }).catch(() => setLoaded(true));
  }, [date]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    setSaved(false);
    try {
      await upsertDsr({ report_date: date, ...f });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5 max-w-5xl">
      {/* Date & Unit header */}
      <div className="flex flex-wrap items-center gap-4 mb-2">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Report Date</label>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="px-3 py-2 rounded-xl text-sm outline-none"
            style={{ border: '2px solid var(--ksp-navy)' }}
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Unit</label>
          <div className="px-3 py-2 rounded-xl text-sm font-bold" style={{ background: 'var(--ksp-yellow-soft)', border: '2px solid var(--ksp-yellow-border)', color: 'var(--ksp-navy)' }}>
            {user?.unit_name ?? 'N/A'}
          </div>
        </div>
        {!loaded && <span className="text-xs text-slate-400 self-end">Loading...</span>}
      </div>

      {/* Tab bar */}
      <div className="flex gap-2">
        {TABS.map((t, i) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(i)}
            className="px-4 py-2 text-sm font-semibold rounded-xl transition"
            style={{
              background: tab === i ? 'var(--ksp-navy)' : 'var(--ksp-yellow)',
              color: tab === i ? 'var(--ksp-yellow)' : '#000',
              border: '2px solid rgba(0,0,0,0.2)',
            }}
          >
            <span className="inline-flex items-center gap-1.5">
              <span className="w-5 h-5 rounded-full text-xs flex items-center justify-center font-bold"
                style={{ background: tab === i ? 'var(--ksp-yellow)' : 'var(--ksp-navy)', color: tab === i ? 'var(--ksp-navy)' : 'var(--ksp-yellow)' }}
              >{i + 1}</span>
              {t.label}
            </span>
          </button>
        ))}
      </div>

      {/* Tab 1: Cases & Lien */}
      {tab === 0 && (
        <div className="space-y-5">
          <Section title="Details of Cases & Petitions">
            <NumberField label="Cases" value={f.cases} onChange={set('cases')} />
            <NumberField label="Petitions" value={f.petitions} onChange={set('petitions')} />
            <NumberField label="Details of Arrest" value={f.details_of_arrest} onChange={set('details_of_arrest')} />
          </Section>

          <Section title="Details of Amount Lien Marked (FIR/1930/NCRP)">
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Case Type</label>
              <select
                value={f.case_type}
                onChange={(e) => setF((p) => ({ ...p, case_type: e.target.value }))}
                className="w-full px-3 py-2 rounded-xl text-sm font-semibold outline-none"
            style={{ border: '2px solid var(--ksp-navy)', background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}
              >
                <option value="FIR">FIR</option>
                <option value="NCRP">NCRP</option>
              </select>
            </div>
            <NumberField label="Cumulative Amount Lien Marked (since Jan 2024)" value={f.cumulative_amount_lien_marked} onChange={set('cumulative_amount_lien_marked')} />
            <NumberField label="Cumulative Accounts Lien Marked (since Jan 2024)" value={f.cumulative_accounts_lien_marked} onChange={set('cumulative_accounts_lien_marked')} />
            <NumberField label="Cumulative Accounts De-Freezed / Lien Removed (since Jan 2024)" value={f.cumulative_accounts_defreezed} onChange={set('cumulative_accounts_defreezed')} />
          </Section>

          <Section title="Amount Refunded">
            <NumberField label="Amount Refunded to Victim (since records began)" value={f.amount_refunded_to_victim} onChange={set('amount_refunded_to_victim')} />
          </Section>
        </div>
      )}

      {/* Tab 2: UI Cases Pending */}
      {tab === 1 && (
        <div className="space-y-5">
          <Section title="Total UI Cases Pending (by Year)">
            <NumberField label="2021" value={f.ui_cases_pending_2021} onChange={set('ui_cases_pending_2021')} />
            <NumberField label="2022" value={f.ui_cases_pending_2022} onChange={set('ui_cases_pending_2022')} />
            <NumberField label="2023" value={f.ui_cases_pending_2023} onChange={set('ui_cases_pending_2023')} />
            <NumberField label="2024" value={f.ui_cases_pending_2024} onChange={set('ui_cases_pending_2024')} />
            <NumberField label="2025" value={f.ui_cases_pending_2025} onChange={set('ui_cases_pending_2025')} />
            <NumberField label="2026" value={f.ui_cases_pending_2026} onChange={set('ui_cases_pending_2026')} />
          </Section>
        </div>
      )}

      {/* Tab 3: Disposal & Trial */}
      {tab === 2 && (
        <div className="space-y-5">
          <Section title="Cases Disposed from Investigation (since 1 Jan 2026)">
            <NumberField label="Detected & Chargesheeted" value={f.disposed_detected_chargesheeted} onChange={set('disposed_detected_chargesheeted')} />
            <NumberField label="Transferred" value={f.disposed_transferred} onChange={set('disposed_transferred')} />
            <NumberField label="False" value={f.disposed_false} onChange={set('disposed_false')} />
            <NumberField label="Un-Detected" value={f.disposed_undetected} onChange={set('disposed_undetected')} />
          </Section>

          <Section title="Status of Trial (from 1 Jan 2026)">
            <NumberField label="Convicted" value={f.trial_convicted} onChange={set('trial_convicted')} />
            <NumberField label="Discharged" value={f.trial_discharged} onChange={set('trial_discharged')} />
            <NumberField label="Acquitted" value={f.trial_acquitted} onChange={set('trial_acquitted')} />
            <NumberField label="Abated" value={f.trial_abated} onChange={set('trial_abated')} />
            <NumberField label="Compounded" value={f.trial_compounded} onChange={set('trial_compounded')} />
            <NumberField label="UT" value={f.trial_ut} onChange={set('trial_ut')} />
          </Section>
        </div>
      )}

      {error && <div className="px-4 py-3 rounded-xl text-sm font-semibold" style={{ background: 'rgba(177,0,0,0.08)', color: 'var(--ksp-red)' }}>{error}</div>}

      {/* Navigation + Submit */}
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => setTab((t) => Math.max(0, t - 1))}
          disabled={tab === 0}
          className="flex items-center gap-1 px-4 py-2 text-sm font-semibold rounded-xl transition disabled:opacity-30 disabled:cursor-not-allowed"
          style={{ background: 'var(--ksp-yellow)', color: '#000', border: '2px solid rgba(0,0,0,0.25)' }}
        >
          <ChevronLeft className="w-4 h-4" /> Previous
        </button>

        <div className="flex items-center gap-3">
          {tab < TABS.length - 1 ? (
            <button
              type="button"
              onClick={() => setTab((t) => Math.min(TABS.length - 1, t + 1))}
              className="flex items-center gap-1 px-5 py-2.5 font-semibold rounded-xl transition"
              style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)', border: '2px solid rgba(0,0,0,0.25)' }}
            >
              Next <ChevronRight className="w-4 h-4" />
            </button>
          ) : (
            <button
              type="submit"
              disabled={saving}
              className="flex items-center gap-2 px-6 py-2.5 font-bold rounded-xl transition disabled:opacity-50"
              style={{ background: 'var(--ksp-yellow)', color: '#000', border: '2px solid rgba(0,0,0,0.25)' }}
            >
              <Save className="w-4 h-4" />
              {saving ? 'Saving...' : 'Submit DSR'}
            </button>
          )}
          {saved && (
            <span className="flex items-center gap-1 text-sm font-bold" style={{ color: '#0a5c2a' }}>
              <CheckCircle className="w-4 h-4" /> Saved
            </span>
          )}
        </div>
      </div>
    </form>
  );
}
