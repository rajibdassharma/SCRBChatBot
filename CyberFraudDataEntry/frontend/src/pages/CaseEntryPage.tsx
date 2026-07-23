import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router';
import { toast } from 'sonner';
import { Save, ChevronRight, ChevronLeft, Plus, Trash2, X, Upload } from 'lucide-react';
import { createCase, updateCase, getCase, deleteCase } from '../lib/api/cases';
import { useAuthStore } from '../lib/stores/auth-store';
import { CRIME_TYPE_OTHERS, CYBER_CRIME_TYPES } from '../lib/utils/crime-types';
import { FIR_NO_PLACEHOLDER, validateFirNo } from '../lib/utils/fir-no';
import { isSuperAdmin } from '../lib/utils/roles';
import type { CaseEntry, Arrest, Accomplice, Petition, LienAccount, UnfreezeDetail, Refund, Victim } from '../types';

const BASE = import.meta.env.VITE_API_BASE ?? '';

/* --- Empty factories --- */

const emptyAccomplice = (): Accomplice => ({
  where_met: '', where_stayed: '', interrogation_details: '',
});

const emptyArrest = (): Arrest => ({
  name: '', address: '', email: '', aadhar: '', pan: '', date_of_arrest: '', statement: '',
  accomplices: [emptyAccomplice()], accused_details: [],
});

const emptyPetition = (): Petition => ({
  fir_registered: 'yes', why_not: '', nature: '', petition_type: 'amount_lost', amount: 0,
});

const emptyLien = (): LienAccount => ({
  case_type: 'FIR', account_no: '', amount_lien_marked: 0, layer: 1, total_amount_in_account: 0, bank_name: '',
});

const emptyUnfreeze = (): UnfreezeDetail => ({
  unfreeze_type: 'letter', crime_no: '', bank_name: '', account_no: '', amount: 0,
});

const emptyRefund = (): Refund => ({
  refunded: 'yes', victim_name: '', amount: 0, crime_no_or_petition_no: '',
});

const emptyVictim = (): Victim => ({
  first_name: '', last_name: '', age: null, gender: '',
  phone: '', email: '',
  house_no: '', street_name: '', city: '', state: '', country: 'India', pincode: '',
  amount_lost: 0, bank_account_no: '', bank_name: '', bank_branch_address: '',
});

// 28 Indian states + 8 union territories, alphabetical, plus "Other" for
// non-India addresses. Stored as the literal label; backend accepts any
// string (VARCHAR(100)) so we don't need a separate code.
const INDIAN_STATES: string[] = [
  'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chhattisgarh',
  'Goa', 'Gujarat', 'Haryana', 'Himachal Pradesh', 'Jharkhand',
  'Karnataka', 'Kerala', 'Madhya Pradesh', 'Maharashtra', 'Manipur',
  'Meghalaya', 'Mizoram', 'Nagaland', 'Odisha', 'Punjab',
  'Rajasthan', 'Sikkim', 'Tamil Nadu', 'Telangana', 'Tripura',
  'Uttar Pradesh', 'Uttarakhand', 'West Bengal',
  // Union Territories
  'Andaman and Nicobar Islands', 'Chandigarh',
  'Dadra and Nagar Haveli and Daman and Diu', 'Delhi',
  'Jammu and Kashmir', 'Ladakh', 'Lakshadweep', 'Puducherry',
  // Fallback for non-India addresses
  'Other',
].sort((a, b) => a === 'Other' ? 1 : b === 'Other' ? -1 : a.localeCompare(b));

/** Build the Crime Type dropdown options — the 31-entry classification
 *  list prefixed by a "— Select —" placeholder. If the case currently
 *  holds a legacy value ({Internet, Digital, Crypto} from before
 *  migration 016, or any other value that's since been removed), the
 *  value is surfaced as a "(legacy)" option so the row can save without
 *  losing its category. Unknown value never mutates the underlying
 *  constant. */
function crimeTypeOptions(current: string): { value: string; label: string }[] {
  const opts = [
    { value: '', label: '— Select —' },
    ...CYBER_CRIME_TYPES.map((v) => ({ value: v, label: v })),
  ];
  if (current && !CYBER_CRIME_TYPES.includes(current)) {
    opts.push({ value: current, label: `${current} (legacy)` });
  }
  return opts;
}

const initialForm = (): CaseEntry => ({
  // Since migration 016 (2026-07-22), crime_type is an open string
  // sourced from CYBER_CRIME_TYPES. Start empty so operators explicitly
  // pick — no misleading default. Legacy values on existing rows are
  // preserved by the dropdown's fallback below.
  fir_no: '', registration_date: '', case_type: 'NCRP', crime_type: '',
  crime_type_other: '',
  sections: '',
  is_financial: true,
  facts: '',
  arrests: [], petitions: [], lien_accounts: [], unfreeze_details: [], refunds: [],
  victim: emptyVictim(),
  status: 'draft',
});

// Tabs visible on a Financial case (everything). Non-Financial cases hide
// the last three (Lien Marked, Unfreeze, Refunds) since they don't apply.
const FINANCIAL_TABS = ['Case Details', 'Arrests', 'IR Details', 'Petitions', 'Lien Marked', 'Unfreeze', 'Refunds'];
const NON_FINANCIAL_TABS = ['Case Details', 'Arrests', 'IR Details', 'Petitions'];

/* --- Reusable field components --- */

function TextField({ label, value, onChange, placeholder, type = 'text', readOnly = false, hint, wrapperClassName, maxLength, inputMode }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string; type?: string; readOnly?: boolean; hint?: string; wrapperClassName?: string; maxLength?: number; inputMode?: 'text' | 'numeric' | 'email' | 'tel';
}) {
  return (
    <div className={wrapperClassName}>
      <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>
        {label}
        {readOnly && hint && (
          <span className="ml-2 font-normal italic" style={{ color: 'rgba(11,44,74,0.6)' }}>({hint})</span>
        )}
      </label>
      <input
        type={type}
        value={value}
        onChange={(e) => !readOnly && onChange(e.target.value)}
        readOnly={readOnly}
        maxLength={maxLength}
        inputMode={inputMode}
        className="w-full px-3 py-2 rounded-xl text-sm outline-none"
        style={{
          border: readOnly ? '1px solid rgba(11,44,74,0.15)' : '2px solid var(--ksp-navy)',
          background: readOnly ? 'rgba(11,44,74,0.04)' : '#fff',
          color: readOnly ? 'rgba(0,0,0,0.6)' : 'inherit',
          cursor: readOnly ? 'not-allowed' : 'text',
        }}
        placeholder={readOnly ? '' : (placeholder ?? '')}
      />
    </div>
  );
}

function NumField({ label, value, onChange, wrapperClassName }: { label: string; value: number; onChange: (v: number) => void; wrapperClassName?: string }) {
  return (
    <div className={wrapperClassName}>
      <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>{label}</label>
      <input
        type="number"
        min={0}
        value={value || ''}
        onChange={(e) => onChange(Number(e.target.value) || 0)}
        className="w-full px-3 py-2 rounded-xl text-sm outline-none"
        style={{ border: '2px solid var(--ksp-navy)', background: '#fff' }}
        placeholder="0"
      />
    </div>
  );
}

function SelectField({ label, value, onChange, options, wrapperClassName }: {
  label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; wrapperClassName?: string;
}) {
  return (
    <div className={wrapperClassName}>
      <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 rounded-xl text-sm font-semibold outline-none"
        style={{ border: '2px solid var(--ksp-navy)', background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}
      >
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}

function TextAreaField({ label, value, onChange, rows = 3 }: {
  label: string; value: string; onChange: (v: string) => void; rows?: number;
}) {
  return (
    <div className="col-span-full">
      <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>{label}</label>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={rows}
        className="w-full px-3 py-2 rounded-xl text-sm outline-none resize-y"
        style={{ border: '2px solid var(--ksp-navy)', background: '#fff' }}
      />
    </div>
  );
}

/** Radio group for Financial vs Non-Financial case nature. Drives which
 *  tabs and victim fields are visible. Lives at the top of Tab 1. */
function FinancialRadio({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  const pillStyle = (active: boolean) => ({
    background: active ? 'var(--ksp-navy)' : '#fff',
    color: active ? 'var(--ksp-yellow)' : 'var(--ksp-navy)',
    border: active ? '2px solid var(--ksp-navy)' : '2px solid rgba(11,44,74,0.18)',
    cursor: 'pointer' as const,
  });
  return (
    <div className="rounded-2xl p-4 flex items-center gap-4" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
      <span className="text-xs font-bold uppercase tracking-wide" style={{ color: 'var(--ksp-red)' }}>Case Nature</span>
      <label className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold transition" style={pillStyle(value === true)}>
        <input type="radio" className="sr-only" name="financial_nature" checked={value === true} onChange={() => onChange(true)} />
        Financial
      </label>
      <label className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold transition" style={pillStyle(value === false)}>
        <input type="radio" className="sr-only" name="financial_nature" checked={value === false} onChange={() => onChange(false)} />
        Non-Financial
      </label>
      <p className="text-xs opacity-60 ml-2">
        {value
          ? 'Lien Marked / Unfreeze / Refunds tabs and victim banking fields are shown.'
          : 'Lien / Unfreeze / Refunds tabs hidden; victim banking fields hidden.'}
      </p>
    </div>
  );
}

function Section({ title, children, cols = 3 }: { title: string; children: React.ReactNode; cols?: 3 | 6 }) {
  // cols=6 lets fields use lg:col-span-1 .. 6 via wrapperClassName for
  // a denser layout (e.g. Age + Gender at 1/6 width each).
  const gridClass = cols === 6
    ? "grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4"
    : "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4";
  return (
    <div className="rounded-2xl p-5" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
      <h3 className="text-sm font-bold mb-4 uppercase tracking-wide" style={{ color: 'var(--ksp-red)' }}>{title}</h3>
      <div className={gridClass}>{children}</div>
    </div>
  );
}

function AddBtn({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button type="button" onClick={onClick}
      className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-xl transition"
      style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)', border: '2px solid rgba(0,0,0,0.25)' }}>
      <Plus className="w-4 h-4" /> {label}
    </button>
  );
}

function RemBtn({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" onClick={onClick}
      className="flex items-center gap-1 px-3 py-1.5 text-xs font-semibold rounded-lg transition"
      style={{ background: 'rgba(177,0,0,0.08)', color: 'var(--ksp-red)', border: '1px solid rgba(177,0,0,0.2)' }}>
      <Trash2 className="w-3.5 h-3.5" /> Remove
    </button>
  );
}

/* --- Tab definitions --- */


const NATURE_OPTIONS = [
  { value: '', label: '-- Select --' },
  { value: 'Cheating', label: 'Cheating' },
  { value: 'Impersonation', label: 'Impersonation' },
  { value: 'Phishing', label: 'Phishing' },
  { value: 'Vishing', label: 'Vishing' },
  { value: 'OTP Fraud', label: 'OTP Fraud' },
  { value: 'Investment Fraud', label: 'Investment Fraud' },
  { value: 'Loan Fraud', label: 'Loan Fraud' },
  { value: 'Sextortion', label: 'Sextortion' },
  { value: 'Job Fraud', label: 'Job Fraud' },
  { value: 'Other', label: 'Other' },
];

/* --- Main Component --- */

export function CaseEntryPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const isEdit = !!id;
  // Senior Officer (super_admin) is view-only across every FIR entry
  // point (2026-07-23). Backend rejects the mutation itself; this flag
  // hides Save / Save Draft / Submit / Delete + shows a banner so the
  // reason is obvious.
  const readOnly = isSuperAdmin(user);

  const [tab, setTab] = useState(0);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [f, setF] = useState<CaseEntry>(initialForm());
  const [caseId, setCaseId] = useState<string | undefined>(id);
  const [uploadingIdx, setUploadingIdx] = useState<number | null>(null);

  // Tab list depends on financial nature — non-financial hides the three
  // financial-only tabs (Lien Marked, Unfreeze, Refunds).
  const TABS = f.is_financial ? FINANCIAL_TABS : NON_FINANCIAL_TABS;

  // If user flips to Non-Financial while sitting on a tab that gets
  // hidden, snap back to tab 0 so they don't see a blank screen.
  useEffect(() => {
    if (tab >= TABS.length) setTab(0);
  }, [TABS.length, tab]);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setCaseId(id);
    getCase(id)
      .then((data) => setF({ ...initialForm(), ...data }))
      .catch((err) => toast.error(`Failed to load case: ${err.message}`))
      .finally(() => setLoading(false));
  }, [id]);

  /* --- Photo upload handler --- */
  const handlePhotoUpload = async (arrestIdx: number, file: File) => {
    setUploadingIdx(arrestIdx);
    try {
      const token = localStorage.getItem('token');
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(`${BASE}/api/v1/uploads/photo`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      const photoPath: string = data.photo_path;

      // Update the arrest's accused_details with the photo_path
      const arrests = [...f.arrests];
      const existing = arrests[arrestIdx].accused_details;
      if (existing.length > 0) {
        existing[0] = { ...existing[0], photo_path: photoPath };
      } else {
        existing.push({ photo_path: photoPath, email: '', mobile: '', occupation: '', remarks: '' });
      }
      arrests[arrestIdx] = { ...arrests[arrestIdx], accused_details: [...existing] };
      setF(p => ({ ...p, arrests }));
      toast.success('Photo uploaded');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploadingIdx(null);
    }
  };

  /* Build the payload — both the unfreeze rows' crime_no and the refund
   * rows' crime_no_or_petition_no mirror the case FIR No. Those fields
   * are displayed read-only as "FIR No" in the UI; we keep the DB
   * columns populated so downstream reports stay correct.
   *
   * Victim: if the operator hasn't touched the section, omit it from the
   * payload (send null) so we don't create an empty victim row on disk.
   * Backend's submit-time validator separately requires the victim block
   * with non-empty mandatory fields when status === 'submitted'. */
  const buildPayload = (status: 'draft' | 'submitted'): CaseEntry => {
    const v = f.victim;
    // Country defaults to "India" so we exclude it from the "all blank?"
    // check — otherwise every untouched form would falsely look filled.
    const hasVictimData = !!v && (
      !!v.first_name || !!v.last_name || !!v.age || !!v.gender ||
      !!v.phone || !!v.email ||
      !!v.house_no || !!v.street_name || !!v.city || !!v.state || !!v.pincode ||
      !!v.amount_lost || !!v.bank_account_no || !!v.bank_name || !!v.bank_branch_address
    );
    return {
      ...f,
      status,
      unfreeze_details: f.unfreeze_details.map(u => ({ ...u, crime_no: f.fir_no })),
      refunds: f.refunds.map(r => ({ ...r, crime_no_or_petition_no: f.fir_no })),
      victim: hasVictimData ? v : null,
    };
  };

  // Format check — non-empty invalid FIR shows a red hint under the
  // field AND blocks Save. `isEdit` cases are read-only on this
  // field (fir_no is immutable-after-create per the update route), so
  // the check only matters for the create path.
  const firNoError = !isEdit ? validateFirNo(f.fir_no) : null;

  /* --- Save Draft --- */
  const handleSaveDraft = async () => {
    if (firNoError) { toast.error(firNoError); setTab(0); return; }
    setSaving(true);
    try {
      const payload = buildPayload('draft');
      if (caseId) {
        await updateCase(caseId, payload);
        toast.success('Draft saved');
      } else {
        const created = await createCase(payload);
        setCaseId(created.id);
        toast.success('Draft saved');
        navigate(`/cases/${created.id}`, { replace: true });
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  /* --- Submit --- */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!f.fir_no.trim()) { toast.error('FIR No is required'); setTab(0); return; }
    if (firNoError) { toast.error(firNoError); setTab(0); return; }
    if (!f.registration_date) { toast.error('Registration Date is required'); setTab(0); return; }
    setSaving(true);
    try {
      const payload = buildPayload('submitted');
      if (caseId) {
        await updateCase(caseId, payload);
        toast.success('Case submitted');
      } else {
        await createCase(payload);
        toast.success('Case submitted');
      }
      navigate('/cases/new');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  /* --- Cancel --- */
  const handleCancel = async () => {
    if (!window.confirm('Are you sure? All entered data will be deleted.')) return;
    try {
      if (caseId) {
        await deleteCase(caseId);
      }
      toast.success('Case cancelled');
      navigate('/cases/new');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Cancel failed');
    }
  };

  if (loading) return <div className="flex items-center justify-center py-20"><span className="text-sm text-slate-400">Loading...</span></div>;

  return (
    <div>
      {/* DSR Header */}
      <div className="rounded-2xl p-4 mb-4" style={{ background: 'var(--ksp-navy)', color: '#fff' }}>
        <h1 className="text-lg font-bold" style={{ color: 'var(--ksp-yellow)' }}>Daily Status Report</h1>
        <div className="flex gap-6 mt-2 text-sm">
          <span><strong>District:</strong> {user?.unit_name}</span>
          <span><strong>CCPS:</strong> {user?.ps_name || 'N/A'}</span>
          <span><strong>User:</strong> {user?.username}</span>
        </div>
      </div>

      <h1 className="text-[22px] font-bold mb-1" style={{ color: 'var(--ksp-navy)' }}>
        {readOnly ? 'View Case' : (isEdit ? 'Edit Case' : 'New Case Entry')}
      </h1>
      <p className="text-sm font-medium mb-6" style={{ color: 'var(--ksp-red)' }}>
        {readOnly
          ? `Viewing FIR ${f.fir_no} (read-only)`
          : (isEdit ? `Editing FIR ${f.fir_no}` : 'Enter case details across all tabs')}
      </p>

      {readOnly && (
        <div className="rounded-2xl p-4 mb-4 max-w-5xl"
          style={{ background: '#fff7d6', border: '2px dashed #c49500' }}>
          <p className="text-sm font-semibold" style={{ color: '#8a5b00' }}>
            Senior Officer accounts are view-only for FIRs.
          </p>
          <p className="text-xs mt-1 opacity-80">
            The form below is disabled. Only PS admins can create / edit /
            delete a case. This case belongs to {user?.unit_name ?? 'another district'}
            {' '}— you have read access for oversight.
          </p>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-5 max-w-5xl">
      {/* fieldset disabled= toggles every native input / button INSIDE
           it into a disabled state — one wrapper handles the entire
           read-only mode for super_admin without touching every field. */}
      <fieldset disabled={readOnly} className="space-y-5" style={{ border: 'none', padding: 0, margin: 0 }}>
        {/* Tab bar */}
        <div className="flex flex-wrap gap-2">
          {TABS.map((label, i) => (
            <button key={label} type="button" onClick={() => setTab(i)}
              className="px-4 py-2 text-sm font-semibold rounded-xl transition"
              style={{
                background: tab === i ? 'var(--ksp-navy)' : 'var(--ksp-yellow)',
                color: tab === i ? 'var(--ksp-yellow)' : '#000',
                border: '2px solid rgba(0,0,0,0.2)',
              }}>
              <span className="inline-flex items-center gap-1.5">
                <span className="w-5 h-5 rounded-full text-xs flex items-center justify-center font-bold"
                  style={{ background: tab === i ? 'var(--ksp-yellow)' : 'var(--ksp-navy)', color: tab === i ? 'var(--ksp-navy)' : 'var(--ksp-yellow)' }}>
                  {i + 1}
                </span>
                {label}
              </span>
            </button>
          ))}
        </div>

        {/* === TAB 1 -- Case Details === */}
        {tab === 0 && (
          <div className="space-y-5">
            <FinancialRadio value={f.is_financial} onChange={(v) => setF(p => ({ ...p, is_financial: v }))} />
            <Section title="Case Information">
              <div>
                <TextField label="FIR No" value={f.fir_no} onChange={(v) => setF(p => ({ ...p, fir_no: v }))} placeholder={FIR_NO_PLACEHOLDER} readOnly={isEdit} hint={isEdit ? "FIR number cannot be changed after creation" : undefined} />
                {firNoError && (
                  <p className="text-xs mt-1" style={{ color: 'var(--ksp-red)' }}>{firNoError}</p>
                )}
              </div>
              <TextField label="Registration Date" value={f.registration_date} onChange={(v) => setF(p => ({ ...p, registration_date: v }))} type="date" />
              <SelectField label="Case Type" value={f.case_type}
                onChange={(v) => setF(p => ({ ...p, case_type: v as CaseEntry['case_type'] }))}
                options={[{ value: 'NCRP', label: 'NCRP' }, { value: 'Walk-In', label: 'Walk-In' }]} />
              <SelectField label="Crime Type" value={f.crime_type}
                onChange={(v) => setF(p => ({
                  ...p,
                  crime_type: v,
                  // Clear the free-text when leaving Others so the
                  // stale value never round-trips back to the API.
                  // (Backend also enforces this; belt + braces.)
                  crime_type_other: v === CRIME_TYPE_OTHERS ? (p.crime_type_other ?? '') : '',
                }))}
                options={crimeTypeOptions(f.crime_type)} />
              <TextField label="Sections" value={f.sections ?? ''}
                onChange={(v) => setF(p => ({ ...p, sections: v }))}
                placeholder="e.g. 318(4), 319, 340" />
              {f.crime_type === CRIME_TYPE_OTHERS && (
                <TextField label="Other — describe the crime type"
                  wrapperClassName="lg:col-span-3"
                  value={f.crime_type_other ?? ''}
                  onChange={(v) => setF(p => ({ ...p, crime_type_other: v }))}
                  placeholder="Describe the classification that doesn't fit any of the listed sub-heads" />
              )}
            </Section>

            <Section title="Victim Details" cols={6}>
              {/* Row 1: Name + small Age/Gender */}
              <TextField label="First Name *" wrapperClassName="lg:col-span-2" value={f.victim?.first_name ?? ''}
                onChange={(v) => setF(p => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), first_name: v } }))} />
              <TextField label="Last Name *" wrapperClassName="lg:col-span-2" value={f.victim?.last_name ?? ''}
                onChange={(v) => setF(p => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), last_name: v } }))} />
              <NumField label="Age" wrapperClassName="lg:col-span-1" value={f.victim?.age ?? 0}
                onChange={(v) => setF(p => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), age: v || null } }))} />
              <SelectField label="Gender" wrapperClassName="lg:col-span-1" value={f.victim?.gender ?? ''}
                onChange={(v) => setF(p => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), gender: v as Victim['gender'] } }))}
                options={[
                  { value: '', label: '—' },
                  { value: 'Male', label: 'Male' },
                  { value: 'Female', label: 'Female' },
                  { value: 'Other', label: 'Other' },
                  { value: 'Prefer not to say', label: 'Prefer not to say' },
                ]} />

              {/* Row 2: Contact + Country (all compact identifiers) */}
              <TextField label="Phone" wrapperClassName="lg:col-span-2" value={f.victim?.phone ?? ''}
                onChange={(v) => setF(p => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), phone: v.replace(/\D/g, '') } }))}
                placeholder="10-digit mobile" maxLength={10} inputMode="numeric" />
              <TextField label="Email" type="email" wrapperClassName="lg:col-span-2" value={f.victim?.email ?? ''}
                onChange={(v) => setF(p => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), email: v } }))}
                placeholder="name@domain.com" inputMode="email" />
              <TextField label="Country" wrapperClassName="lg:col-span-2" value={f.victim?.country ?? 'India'}
                onChange={(v) => setF(p => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), country: v } }))} />

              {/* Row 3: Address — fits the entire breakdown on one row */}
              <TextField label="House No" wrapperClassName="lg:col-span-1" value={f.victim?.house_no ?? ''}
                onChange={(v) => setF(p => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), house_no: v } }))} />
              <TextField label="Street Name" wrapperClassName="lg:col-span-2" value={f.victim?.street_name ?? ''}
                onChange={(v) => setF(p => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), street_name: v } }))} />
              <TextField label="City" wrapperClassName="lg:col-span-1" value={f.victim?.city ?? ''}
                onChange={(v) => setF(p => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), city: v } }))} />
              <SelectField label="State" wrapperClassName="lg:col-span-1" value={f.victim?.state ?? ''}
                onChange={(v) => setF(p => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), state: v } }))}
                options={[
                  { value: '', label: '—' },
                  ...INDIAN_STATES.map(s => ({ value: s, label: s })),
                ]} />
              <TextField label="Pincode" wrapperClassName="lg:col-span-1" value={f.victim?.pincode ?? ''}
                onChange={(v) => setF(p => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), pincode: v.replace(/\D/g, '') } }))}
                placeholder="6-digit" maxLength={6} inputMode="numeric" />

              {/* Rows 5+6 — Financial fields only, hidden when Non-Financial */}
              {f.is_financial && (
                <>
                  <NumField label="Amount Lost (₹) *" wrapperClassName="lg:col-span-2" value={f.victim?.amount_lost ?? 0}
                    onChange={(v) => setF(p => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), amount_lost: v } }))} />
                  <TextField label="Bank Account No *" wrapperClassName="lg:col-span-2" value={f.victim?.bank_account_no ?? ''}
                    onChange={(v) => setF(p => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), bank_account_no: v.replace(/\D/g, '') } }))}
                    placeholder="9–18 digits" maxLength={18} inputMode="numeric" />
                  <TextField label="Bank Name *" wrapperClassName="lg:col-span-2" value={f.victim?.bank_name ?? ''}
                    onChange={(v) => setF(p => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), bank_name: v } }))} />
                  <TextField label="Bank Branch Address" wrapperClassName="col-span-full" value={f.victim?.bank_branch_address ?? ''}
                    onChange={(v) => setF(p => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), bank_branch_address: v } }))} />
                </>
              )}
            </Section>

            <Section title="Facts">
              <TextAreaField label="Facts" value={f.facts} onChange={(v) => setF(p => ({ ...p, facts: v }))} rows={4} />
            </Section>
          </div>
        )}

        {/* === TAB 2 -- Arrests === */}
        {tab === 1 && (
          <div className="space-y-5">
            {f.arrests.map((a, ai) => (
              <div key={ai} className="rounded-2xl p-5 space-y-4" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-bold uppercase tracking-wide" style={{ color: 'var(--ksp-red)' }}>Arrest #{ai + 1}</h3>
                  <RemBtn onClick={() => setF(p => ({ ...p, arrests: p.arrests.filter((_, i) => i !== ai) }))} />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  <TextField label="Name" value={a.name} onChange={(v) => { const arr = [...f.arrests]; arr[ai] = { ...arr[ai], name: v }; setF(p => ({ ...p, arrests: arr })); }} />
                  <TextField label="Address" value={a.address} onChange={(v) => { const arr = [...f.arrests]; arr[ai] = { ...arr[ai], address: v }; setF(p => ({ ...p, arrests: arr })); }} />
                  <TextField label="Email" value={a.email} onChange={(v) => { const arr = [...f.arrests]; arr[ai] = { ...arr[ai], email: v }; setF(p => ({ ...p, arrests: arr })); }} type="email" />
                  <TextField label="Aadhar" value={a.aadhar} onChange={(v) => { const arr = [...f.arrests]; arr[ai] = { ...arr[ai], aadhar: v }; setF(p => ({ ...p, arrests: arr })); }} placeholder="12-digit" />
                  <TextField label="PAN" value={a.pan} onChange={(v) => { const arr = [...f.arrests]; arr[ai] = { ...arr[ai], pan: v }; setF(p => ({ ...p, arrests: arr })); }} placeholder="ABCDE1234F" />
                  <TextField label="Date of Arrest" value={a.date_of_arrest} onChange={(v) => { const arr = [...f.arrests]; arr[ai] = { ...arr[ai], date_of_arrest: v }; setF(p => ({ ...p, arrests: arr })); }} type="date" />
                </div>

                {/* Accomplice sub-section */}
                <div className="mt-3 pt-3" style={{ borderTop: '1px dashed rgba(11,44,74,0.2)' }}>
                  <h4 className="text-xs font-bold mb-3 uppercase tracking-wide" style={{ color: 'var(--ksp-navy)' }}>Accomplice & Interrogation</h4>
                  {a.accomplices.map((acc, aci) => (
                    <div key={aci} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-3">
                      <TextField label="Where Met" value={acc.where_met} onChange={(v) => {
                        const arrests = [...f.arrests];
                        const comps = [...arrests[ai].accomplices];
                        comps[aci] = { ...comps[aci], where_met: v };
                        arrests[ai] = { ...arrests[ai], accomplices: comps };
                        setF(p => ({ ...p, arrests }));
                      }} />
                      <TextField label="Where Stayed" value={acc.where_stayed} onChange={(v) => {
                        const arrests = [...f.arrests];
                        const comps = [...arrests[ai].accomplices];
                        comps[aci] = { ...comps[aci], where_stayed: v };
                        arrests[ai] = { ...arrests[ai], accomplices: comps };
                        setF(p => ({ ...p, arrests }));
                      }} />
                      <TextAreaField label="Interrogation Details" value={acc.interrogation_details} onChange={(v) => {
                        const arrests = [...f.arrests];
                        const comps = [...arrests[ai].accomplices];
                        comps[aci] = { ...comps[aci], interrogation_details: v };
                        arrests[ai] = { ...arrests[ai], accomplices: comps };
                        setF(p => ({ ...p, arrests }));
                      }} />
                    </div>
                  ))}
                </div>
              </div>
            ))}
            <AddBtn onClick={() => setF(p => ({ ...p, arrests: [...p.arrests, emptyArrest()] }))} label="Add Arrest" />
          </div>
        )}

        {/* === TAB 3 -- IR Details === */}
        {tab === 2 && (
          <div className="space-y-5">
            {f.arrests.length === 0 ? (
              <div className="rounded-2xl p-6 text-center" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
                <p className="text-sm font-semibold" style={{ color: 'var(--ksp-navy)' }}>No arrested persons yet. Add arrests in the Arrests tab first.</p>
              </div>
            ) : (
              f.arrests.map((a, ai) => {
                const photoPath = a.accused_details?.[0]?.photo_path || '';
                return (
                  <div key={ai} className="rounded-2xl p-5 space-y-4" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
                    <h3 className="text-sm font-bold uppercase tracking-wide" style={{ color: 'var(--ksp-red)' }}>Arrested Person #{ai + 1}</h3>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                      <div>
                        <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>Name</label>
                        <p className="px-3 py-2 rounded-xl text-sm" style={{ background: 'rgba(11,44,74,0.05)', border: '2px solid rgba(11,44,74,0.15)' }}>
                          {a.name || 'N/A'}
                        </p>
                      </div>
                      <div>
                        <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>Date of Arrest</label>
                        <p className="px-3 py-2 rounded-xl text-sm" style={{ background: 'rgba(11,44,74,0.05)', border: '2px solid rgba(11,44,74,0.15)' }}>
                          {a.date_of_arrest || 'N/A'}
                        </p>
                      </div>
                      <div>
                        <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>Photo</label>
                        {photoPath ? (
                          <div className="flex items-center gap-3">
                            <img
                              src={`${BASE}${photoPath}`}
                              alt={`Photo of ${a.name}`}
                              className="w-16 h-16 rounded-xl object-cover"
                              style={{ border: '2px solid var(--ksp-navy)' }}
                            />
                            <label className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg cursor-pointer transition"
                              style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)', border: '2px solid rgba(0,0,0,0.25)' }}>
                              <Upload className="w-3.5 h-3.5" /> Replace
                              <input type="file" accept="image/*" className="hidden"
                                onChange={(e) => { const file = e.target.files?.[0]; if (file) handlePhotoUpload(ai, file); }}
                              />
                            </label>
                          </div>
                        ) : (
                          <label className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-xl cursor-pointer transition w-fit"
                            style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)', border: '2px solid rgba(0,0,0,0.25)' }}>
                            <Upload className="w-4 h-4" /> {uploadingIdx === ai ? 'Uploading...' : 'Upload Photo'}
                            <input type="file" accept="image/*" className="hidden"
                              disabled={uploadingIdx === ai}
                              onChange={(e) => { const file = e.target.files?.[0]; if (file) handlePhotoUpload(ai, file); }}
                            />
                          </label>
                        )}
                      </div>
                    </div>
                    {/* Statement */}
                    <div className="mt-4">
                      <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>Statement (max 5000 characters)</label>
                      <textarea
                        value={a.statement || ''}
                        onChange={(e) => {
                          if (e.target.value.length <= 5000) {
                            setF(prev => ({
                              ...prev,
                              arrests: prev.arrests.map((arr, idx) => idx === ai ? { ...arr, statement: e.target.value } : arr),
                            }));
                          }
                        }}
                        maxLength={5000}
                        rows={8}
                        className="w-full px-3 py-2 rounded-xl text-sm outline-none resize-y"
                        style={{ border: '2px solid var(--ksp-navy)', background: '#fff' }}
                        placeholder="Enter the statement of the arrested person..."
                      />
                      <p className="text-xs mt-1" style={{ color: 'rgba(11,44,74,0.4)' }}>
                        {(a.statement || '').length} / 5000 characters
                      </p>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}

        {/* === TAB 4 -- Petitions === */}
        {tab === 3 && (
          <div className="space-y-5">
            {f.petitions.map((p, pi) => (
              <div key={pi} className="rounded-2xl p-5" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-bold uppercase tracking-wide" style={{ color: 'var(--ksp-red)' }}>Petition #{pi + 1}</h3>
                  <RemBtn onClick={() => setF(prev => ({ ...prev, petitions: prev.petitions.filter((_, i) => i !== pi) }))} />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  <SelectField label="FIR Registered" value={p.fir_registered}
                    onChange={(v) => { const arr = [...f.petitions]; arr[pi] = { ...arr[pi], fir_registered: v as Petition['fir_registered'] }; setF(prev => ({ ...prev, petitions: arr })); }}
                    options={[{ value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }, { value: 'transferred', label: 'Transferred to Other PS' }]} />
                  {(p.fir_registered === 'no' || p.fir_registered === 'transferred') && (
                    <TextField label="Why Not?" value={p.why_not}
                      onChange={(v) => { const arr = [...f.petitions]; arr[pi] = { ...arr[pi], why_not: v }; setF(prev => ({ ...prev, petitions: arr })); }} />
                  )}
                  <SelectField label="Nature" value={p.nature}
                    onChange={(v) => { const arr = [...f.petitions]; arr[pi] = { ...arr[pi], nature: v }; setF(prev => ({ ...prev, petitions: arr })); }}
                    options={NATURE_OPTIONS} />
                  <SelectField label="Type" value={p.petition_type}
                    onChange={(v) => { const arr = [...f.petitions]; arr[pi] = { ...arr[pi], petition_type: v as Petition['petition_type'] }; setF(prev => ({ ...prev, petitions: arr })); }}
                    options={[{ value: 'amount_lost', label: 'Amount Lost' }, { value: 'fraud_case', label: 'Fraud Case' }]} />
                  <NumField label="Amount" value={p.amount}
                    onChange={(v) => { const arr = [...f.petitions]; arr[pi] = { ...arr[pi], amount: v }; setF(prev => ({ ...prev, petitions: arr })); }} />
                </div>
              </div>
            ))}
            <AddBtn onClick={() => setF(p => ({ ...p, petitions: [...p.petitions, emptyPetition()] }))} label="Add Petition" />
          </div>
        )}

        {/* === TAB 5 -- Lien Marked === */}
        {tab === 4 && (
          <div className="space-y-5">
            {f.lien_accounts.map((l, li) => (
              <div key={li} className="rounded-2xl p-5" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-bold uppercase tracking-wide" style={{ color: 'var(--ksp-red)' }}>Account #{li + 1}</h3>
                  <RemBtn onClick={() => setF(p => ({ ...p, lien_accounts: p.lien_accounts.filter((_, i) => i !== li) }))} />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  <SelectField label="Case Type" value={l.case_type}
                    onChange={(v) => { const arr = [...f.lien_accounts]; arr[li] = { ...arr[li], case_type: v as LienAccount['case_type'] }; setF(p => ({ ...p, lien_accounts: arr })); }}
                    options={[{ value: 'FIR', label: 'FIR' }, { value: 'NCRP', label: 'NCRP' }, { value: 'Petition', label: 'Petition' }]} />
                  <TextField label="Account No" value={l.account_no}
                    onChange={(v) => { const arr = [...f.lien_accounts]; arr[li] = { ...arr[li], account_no: v }; setF(p => ({ ...p, lien_accounts: arr })); }} />
                  <NumField label="Amount Lien Marked" value={l.amount_lien_marked}
                    onChange={(v) => { const arr = [...f.lien_accounts]; arr[li] = { ...arr[li], amount_lien_marked: v }; setF(p => ({ ...p, lien_accounts: arr })); }} />
                  <NumField label="Layer" value={l.layer}
                    onChange={(v) => { const arr = [...f.lien_accounts]; arr[li] = { ...arr[li], layer: v }; setF(p => ({ ...p, lien_accounts: arr })); }} />
                  <NumField label="Total Amount in Account" value={l.total_amount_in_account}
                    onChange={(v) => { const arr = [...f.lien_accounts]; arr[li] = { ...arr[li], total_amount_in_account: v }; setF(p => ({ ...p, lien_accounts: arr })); }} />
                  <TextField label="Bank Name" value={l.bank_name}
                    onChange={(v) => { const arr = [...f.lien_accounts]; arr[li] = { ...arr[li], bank_name: v }; setF(p => ({ ...p, lien_accounts: arr })); }} />
                </div>
              </div>
            ))}
            <AddBtn onClick={() => setF(p => ({ ...p, lien_accounts: [...p.lien_accounts, emptyLien()] }))} label="Add Lien Account" />
          </div>
        )}

        {/* === TAB 6 -- Unfreeze === */}
        {tab === 5 && (
          <div className="space-y-5">
            {f.unfreeze_details.map((u, ui) => (
              <div key={ui} className="rounded-2xl p-5" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-bold uppercase tracking-wide" style={{ color: 'var(--ksp-red)' }}>Unfreeze #{ui + 1}</h3>
                  <RemBtn onClick={() => setF(p => ({ ...p, unfreeze_details: p.unfreeze_details.filter((_, i) => i !== ui) }))} />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  <SelectField label="Type" value={u.unfreeze_type}
                    onChange={(v) => { const arr = [...f.unfreeze_details]; arr[ui] = { ...arr[ui], unfreeze_type: v as UnfreezeDetail['unfreeze_type'] }; setF(p => ({ ...p, unfreeze_details: arr })); }}
                    options={[{ value: 'letter', label: 'Letter' }, { value: 'court_order', label: 'Court Order' }]} />
                  <TextField label="FIR No" value={f.fir_no} onChange={() => {}}
                    readOnly hint="Auto-filled from the case FIR number" />
                  <TextField label="Bank Name" value={u.bank_name}
                    onChange={(v) => { const arr = [...f.unfreeze_details]; arr[ui] = { ...arr[ui], bank_name: v }; setF(p => ({ ...p, unfreeze_details: arr })); }} />
                  <TextField label="Account No" value={u.account_no}
                    onChange={(v) => { const arr = [...f.unfreeze_details]; arr[ui] = { ...arr[ui], account_no: v }; setF(p => ({ ...p, unfreeze_details: arr })); }} />
                  <NumField label="Amount" value={u.amount}
                    onChange={(v) => { const arr = [...f.unfreeze_details]; arr[ui] = { ...arr[ui], amount: v }; setF(p => ({ ...p, unfreeze_details: arr })); }} />
                </div>
              </div>
            ))}
            <AddBtn onClick={() => setF(p => ({ ...p, unfreeze_details: [...p.unfreeze_details, emptyUnfreeze()] }))} label="Add Unfreeze" />
          </div>
        )}

        {/* === TAB 7 -- Refunds === */}
        {tab === 6 && (
          <div className="space-y-5">
            {f.refunds.map((r, ri) => (
              <div key={ri} className="rounded-2xl p-5" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-bold uppercase tracking-wide" style={{ color: 'var(--ksp-red)' }}>Refund #{ri + 1}</h3>
                  <RemBtn onClick={() => setF(p => ({ ...p, refunds: p.refunds.filter((_, i) => i !== ri) }))} />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  <SelectField label="Refunded" value={r.refunded}
                    onChange={(v) => { const arr = [...f.refunds]; arr[ri] = { ...arr[ri], refunded: v as Refund['refunded'] }; setF(p => ({ ...p, refunds: arr })); }}
                    options={[{ value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }]} />
                  <TextField label="Victim Name" value={r.victim_name}
                    onChange={(v) => { const arr = [...f.refunds]; arr[ri] = { ...arr[ri], victim_name: v }; setF(p => ({ ...p, refunds: arr })); }} />
                  <NumField label="Amount" value={r.amount}
                    onChange={(v) => { const arr = [...f.refunds]; arr[ri] = { ...arr[ri], amount: v }; setF(p => ({ ...p, refunds: arr })); }} />
                  <TextField label="FIR No" value={f.fir_no} onChange={() => {}}
                    readOnly hint="Auto-filled from the case FIR number" />
                </div>
              </div>
            ))}
            <AddBtn onClick={() => setF(p => ({ ...p, refunds: [...p.refunds, emptyRefund()] }))} label="Add Refund" />
          </div>
        )}

        {/* Nav + Save Draft + Submit + Cancel */}
        <div className="flex items-center justify-between">
          <button type="button" onClick={() => setTab(t => Math.max(0, t - 1))} disabled={tab === 0}
            className="flex items-center gap-1 px-4 py-2 text-sm font-semibold rounded-xl transition disabled:opacity-30"
            style={{ background: 'var(--ksp-yellow)', color: '#000', border: '2px solid rgba(0,0,0,0.25)' }}>
            <ChevronLeft className="w-4 h-4" /> Previous
          </button>
          <div className="flex items-center gap-3">
            <button type="button" onClick={handleSaveDraft}
              disabled={saving || !!firNoError}
              title={firNoError ?? undefined}
              className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-xl transition disabled:opacity-50"
              style={{ background: '#fff', color: 'var(--ksp-navy)', border: '2px solid var(--ksp-navy)' }}>
              <Save className="w-4 h-4" /> {saving ? 'Saving...' : 'Save Draft'}
            </button>
            {tab < TABS.length - 1 ? (
              <button type="button" onClick={() => setTab(t => Math.min(TABS.length - 1, t + 1))}
                className="flex items-center gap-1 px-5 py-2.5 font-semibold rounded-xl transition"
                style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)', border: '2px solid rgba(0,0,0,0.25)' }}>
                Next <ChevronRight className="w-4 h-4" />
              </button>
            ) : (
              <>
                <button type="submit"
                  disabled={saving || !!firNoError}
                  title={firNoError ?? undefined}
                  className="flex items-center gap-2 px-6 py-2.5 font-bold rounded-xl transition disabled:opacity-50"
                  style={{ background: 'var(--ksp-yellow)', color: '#000', border: '2px solid rgba(0,0,0,0.25)' }}>
                  <Save className="w-4 h-4" /> {saving ? 'Saving...' : 'Submit Case'}
                </button>
                <button type="button" onClick={handleCancel}
                  className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-xl transition"
                  style={{ background: 'rgba(177,0,0,0.08)', color: 'var(--ksp-red)', border: '2px solid rgba(177,0,0,0.3)' }}>
                  <X className="w-4 h-4" /> Cancel
                </button>
              </>
            )}
          </div>
        </div>
      </fieldset>
      </form>
    </div>
  );
}
