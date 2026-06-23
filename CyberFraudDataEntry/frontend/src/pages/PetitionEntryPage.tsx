import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router';
import { toast } from 'sonner';
import { Save, ChevronRight, ChevronLeft, Plus, Trash2, X } from 'lucide-react';
import { createCase, updateCase, getCase, deleteCase } from '../lib/api/cases';
import { useAuthStore } from '../lib/stores/auth-store';
import type { CaseEntry, Petition, LienAccount, UnfreezeDetail, Refund, Victim } from '../types';

/* --- Empty factories --- */

const emptyPetition = (): Petition => ({
  fir_registered: 'yes', why_not: '', nature: '', petition_type: 'amount_lost', amount: 0,
});

const emptyLien = (): LienAccount => ({
  case_type: 'Petition', account_no: '', amount_lien_marked: 0, layer: 1, total_amount_in_account: 0, bank_name: '',
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

const initialForm = (): CaseEntry => ({
  fir_no: '', petition_no: '', registration_date: '', case_type: 'Petition', crime_type: 'Internet',
  is_financial: true,
  facts: '',
  arrests: [], petitions: [], lien_accounts: [], unfreeze_details: [], refunds: [],
  victim: emptyVictim(),
  status: 'draft',
});

// Indian states + UTs alphabetical, plus "Other" pinned to the end.
const INDIAN_STATES: string[] = [
  'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chhattisgarh',
  'Goa', 'Gujarat', 'Haryana', 'Himachal Pradesh', 'Jharkhand',
  'Karnataka', 'Kerala', 'Madhya Pradesh', 'Maharashtra', 'Manipur',
  'Meghalaya', 'Mizoram', 'Nagaland', 'Odisha', 'Punjab',
  'Rajasthan', 'Sikkim', 'Tamil Nadu', 'Telangana', 'Tripura',
  'Uttar Pradesh', 'Uttarakhand', 'West Bengal',
  'Andaman and Nicobar Islands', 'Chandigarh',
  'Dadra and Nagar Haveli and Daman and Diu', 'Delhi',
  'Jammu and Kashmir', 'Ladakh', 'Lakshadweep', 'Puducherry',
  'Other',
].sort((a, b) => a === 'Other' ? 1 : b === 'Other' ? -1 : a.localeCompare(b));

/* --- Reusable field components --- */

function TextField({ label, value, onChange, placeholder, type = 'text', wrapperClassName, maxLength, inputMode }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string; type?: string; wrapperClassName?: string; maxLength?: number; inputMode?: 'text' | 'numeric' | 'email' | 'tel';
}) {
  return (
    <div className={wrapperClassName}>
      <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        maxLength={maxLength}
        inputMode={inputMode}
        className="w-full px-3 py-2 rounded-xl text-sm outline-none"
        style={{ border: '2px solid var(--ksp-navy)', background: '#fff' }}
        placeholder={placeholder ?? ''}
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

function Section({ title, children, cols = 3 }: { title: string; children: React.ReactNode; cols?: 3 | 6 }) {
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

/** Radio group for Financial vs Non-Financial petition nature. Mirror of
 *  the one in CaseEntryPage. */
function FinancialRadio({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  const pillStyle = (active: boolean) => ({
    background: active ? 'var(--ksp-navy)' : '#fff',
    color: active ? 'var(--ksp-yellow)' : 'var(--ksp-navy)',
    border: active ? '2px solid var(--ksp-navy)' : '2px solid rgba(11,44,74,0.18)',
    cursor: 'pointer' as const,
  });
  return (
    <div className="rounded-2xl p-4 flex items-center gap-4" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
      <span className="text-xs font-bold uppercase tracking-wide" style={{ color: 'var(--ksp-red)' }}>Petition Nature</span>
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

// Tabs visible on a Financial petition (everything). Non-Financial petitions
// hide the financial-only tabs (Lien Marked, Unfreeze, Refunds).
const FINANCIAL_TABS = ['Petitions', 'Lien Marked', 'Unfreeze', 'Refunds'];
const NON_FINANCIAL_TABS = ['Petitions'];

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

export function PetitionEntryPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const isEdit = !!id;

  const [tab, setTab] = useState(0);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [f, setF] = useState<CaseEntry>(initialForm());
  const [caseId, setCaseId] = useState<string | undefined>(id);

  // Tab list depends on financial nature.
  const TABS = f.is_financial ? FINANCIAL_TABS : NON_FINANCIAL_TABS;

  // Snap back to tab 0 if user flips to Non-Financial while sitting on a
  // hidden tab.
  useEffect(() => {
    if (tab >= TABS.length) setTab(0);
  }, [TABS.length, tab]);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setCaseId(id);
    getCase(id)
      .then((data) => setF({ ...initialForm(), ...data }))
      .catch((err) => toast.error(`Failed to load petition: ${err.message}`))
      .finally(() => setLoading(false));
  }, [id]);

  /* --- Save Draft --- */
  const handleSaveDraft = async () => {
    setSaving(true);
    try {
      const payload: CaseEntry = { ...f, case_type: 'Petition', fir_no: '', status: 'draft' };
      if (caseId) {
        await updateCase(caseId, payload);
        toast.success('Draft saved');
      } else {
        const created = await createCase(payload);
        setCaseId(created.id);
        toast.success('Draft saved');
        navigate(`/petitions/${created.id}`, { replace: true });
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
    if (!f.petition_no?.trim()) { toast.error('Petition No is required'); return; }
    setSaving(true);
    try {
      const payload: CaseEntry = { ...f, case_type: 'Petition', fir_no: '', status: 'submitted' };
      if (caseId) {
        await updateCase(caseId, payload);
        toast.success('Petition submitted');
      } else {
        await createCase(payload);
        toast.success('Petition submitted');
      }
      navigate('/petitions/new');
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
      toast.success('Petition cancelled');
      navigate('/petitions/new');
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
        {isEdit ? 'Edit Petition' : 'New Petition Entry'}
      </h1>
      <p className="text-sm font-medium mb-6" style={{ color: 'var(--ksp-red)' }}>
        {isEdit ? `Editing Petition ${f.petition_no}` : 'Enter petition details across all tabs'}
      </p>

      <form onSubmit={handleSubmit} className="space-y-5 max-w-5xl">
        {/* Tab bar — sits above the form, matching New Case layout */}
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

        {/* === TAB 1 -- Petitions === */}
        {tab === 0 && (
          <div className="space-y-5">
            {/* Financial / Non-Financial radio drives which tabs + victim fields show */}
            <FinancialRadio value={f.is_financial} onChange={(v) => setF(p => ({ ...p, is_financial: v }))} />

            <Section title="Petition Information">
              <TextField label="Petition No" value={f.petition_no || ''} onChange={(v) => setF(p => ({ ...p, petition_no: v }))} placeholder="e.g. PET-2026-001" />
              <TextField label="Date" value={f.registration_date} onChange={(v) => setF(p => ({ ...p, registration_date: v }))} type="date" />
            </Section>

            {/* Victim Details — same compact layout as New Case. Financial
                fields (amount, bank) hidden when Petition is Non-Financial. */}
            <Section title="Victim Details" cols={6}>
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
              <TextField label="Phone" wrapperClassName="lg:col-span-2" value={f.victim?.phone ?? ''}
                onChange={(v) => setF(p => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), phone: v.replace(/\D/g, '') } }))}
                placeholder="10-digit mobile" maxLength={10} inputMode="numeric" />
              <TextField label="Email" type="email" wrapperClassName="lg:col-span-2" value={f.victim?.email ?? ''}
                onChange={(v) => setF(p => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), email: v } }))}
                placeholder="name@domain.com" inputMode="email" />
              <TextField label="Country" wrapperClassName="lg:col-span-2" value={f.victim?.country ?? 'India'}
                onChange={(v) => setF(p => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), country: v } }))} />
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

        {/* === TAB 2 -- Lien Marked === */}
        {tab === 1 && (
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

        {/* === TAB 3 -- Unfreeze === */}
        {tab === 2 && (
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
                  <TextField label="Crime No" value={u.crime_no}
                    onChange={(v) => { const arr = [...f.unfreeze_details]; arr[ui] = { ...arr[ui], crime_no: v }; setF(p => ({ ...p, unfreeze_details: arr })); }} />
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

        {/* === TAB 4 -- Refunds === */}
        {tab === 3 && (
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
                  <TextField label="Crime No / Petition No" value={r.crime_no_or_petition_no}
                    onChange={(v) => { const arr = [...f.refunds]; arr[ri] = { ...arr[ri], crime_no_or_petition_no: v }; setF(p => ({ ...p, refunds: arr })); }} />
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
            <button type="button" onClick={handleSaveDraft} disabled={saving}
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
                <button type="submit" disabled={saving}
                  className="flex items-center gap-2 px-6 py-2.5 font-bold rounded-xl transition disabled:opacity-50"
                  style={{ background: 'var(--ksp-yellow)', color: '#000', border: '2px solid rgba(0,0,0,0.25)' }}>
                  <Save className="w-4 h-4" /> {saving ? 'Saving...' : 'Submit Petition'}
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
      </form>
    </div>
  );
}
