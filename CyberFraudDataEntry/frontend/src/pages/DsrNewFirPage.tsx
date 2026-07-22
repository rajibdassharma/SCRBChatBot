import { useState } from 'react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { Save, ArrowRight } from 'lucide-react';
import { createCase } from '../lib/api/cases';
import { CRIME_TYPE_OTHERS, CYBER_CRIME_TYPES } from '../lib/utils/crime-types';
import { FIR_NO_PLACEHOLDER, validateFirNo } from '../lib/utils/fir-no';
import { INDIAN_STATES } from '../lib/utils/indian-states';
import type { CaseEntry, Victim } from '../types';

/** DSR → New FIR — lightweight daily-log entry for a fresh FIR.
 *
 *  Mirrors the full content of the CaseEntryPage's "Case Details"
 *  tab (Case Information + Victim Details + Facts) presented as a
 *  single scrolling page — **no tabs**. Everything from later tabs
 *  (arrests, petitions, lien-accounts, unfreeze, refunds) is left
 *  out on purpose per the 2026-07-22 scope revision — those child
 *  records get filled in later via Cases → Update Case.
 *
 *  Data destination: same `cases` table as the full flow. The POST
 *  body sends empty arrays for every child collection but a fully
 *  populated Victim block.
 *
 *  Post-save behaviour: form resets to blank so the operator can log
 *  the next FIR in one continuous flow. A subtle "Edit this case →"
 *  link on the toast row lets them jump into the full CaseEntryPage
 *  if they need to add children immediately.
 */

/* ── Primitives (local copies to avoid a shared-primitives refactor
      that would touch every other case-editing page in the app). ── */

function TextField({
  label, value, onChange, placeholder, type = 'text', maxLength, inputMode, wrapperClassName,
}: {
  label: string; value: string; onChange: (v: string) => void;
  placeholder?: string; type?: string; maxLength?: number;
  inputMode?: 'text' | 'numeric' | 'email' | 'tel'; wrapperClassName?: string;
}) {
  return (
    <div className={wrapperClassName}>
      <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>{label}</label>
      <input
        type={type} value={value} maxLength={maxLength} inputMode={inputMode}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder ?? ''}
        className="w-full px-3 py-2 rounded-xl text-sm outline-none"
        style={{ border: '2px solid var(--ksp-navy)', background: '#fff' }} />
    </div>
  );
}

function NumField({
  label, value, onChange, wrapperClassName,
}: { label: string; value: number; onChange: (v: number) => void; wrapperClassName?: string }) {
  return (
    <div className={wrapperClassName}>
      <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>{label}</label>
      <input
        type="number" min={0} value={value || ''}
        onChange={(e) => onChange(Number(e.target.value) || 0)}
        className="w-full px-3 py-2 rounded-xl text-sm outline-none"
        style={{ border: '2px solid var(--ksp-navy)', background: '#fff' }}
        placeholder="0" />
    </div>
  );
}

function SelectField({
  label, value, onChange, options, wrapperClassName,
}: {
  label: string; value: string; onChange: (v: string) => void;
  options: { value: string; label: string }[]; wrapperClassName?: string;
}) {
  return (
    <div className={wrapperClassName}>
      <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>{label}</label>
      <select
        value={value} onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 rounded-xl text-sm font-semibold outline-none"
        style={{ border: '2px solid var(--ksp-navy)', background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}

function TextAreaField({
  label, value, onChange, rows = 3,
}: { label: string; value: string; onChange: (v: string) => void; rows?: number }) {
  return (
    <div className="col-span-full">
      <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>{label}</label>
      <textarea
        value={value} rows={rows}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 rounded-xl text-sm outline-none resize-y"
        style={{ border: '2px solid var(--ksp-navy)', background: '#fff' }} />
    </div>
  );
}

function Section({
  title, children, cols = 3,
}: { title: string; children: React.ReactNode; cols?: 3 | 6 }) {
  // cols=6 lets fields use lg:col-span-1 .. 6 via wrapperClassName for
  // a denser layout (matches CaseEntryPage's Victim block).
  const gridClass = cols === 6
    ? 'grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4'
    : 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4';
  return (
    <div className="rounded-2xl p-5"
      style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
      <h3 className="text-sm font-bold mb-4 uppercase tracking-wide"
        style={{ color: 'var(--ksp-red)' }}>{title}</h3>
      <div className={gridClass}>{children}</div>
    </div>
  );
}

function FinancialRadio({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  const pill = (active: boolean) => ({
    background: active ? 'var(--ksp-navy)' : '#fff',
    color: active ? 'var(--ksp-yellow)' : 'var(--ksp-navy)',
    border: active ? '2px solid var(--ksp-navy)' : '2px solid rgba(11,44,74,0.18)',
    cursor: 'pointer' as const,
  });
  return (
    <div className="rounded-2xl p-4 flex items-center gap-4 flex-wrap"
      style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
      <span className="text-xs font-bold uppercase tracking-wide"
        style={{ color: 'var(--ksp-red)' }}>Case Nature</span>
      <label className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold transition" style={pill(value)}>
        <input type="radio" className="sr-only" name="dsr_financial" checked={value} onChange={() => onChange(true)} />
        Financial
      </label>
      <label className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold transition" style={pill(!value)}>
        <input type="radio" className="sr-only" name="dsr_financial" checked={!value} onChange={() => onChange(false)} />
        Non-Financial
      </label>
      <p className="text-xs opacity-60 ml-2">
        {value
          ? 'Victim banking fields are shown.'
          : 'Victim banking fields hidden.'}
      </p>
    </div>
  );
}

/* ── Form ─────────────────────────────────────────────────── */

const emptyVictim = (): Victim => ({
  first_name: '', last_name: '', age: null, gender: '',
  phone: '', email: '',
  house_no: '', street_name: '', city: '', state: '', country: 'India', pincode: '',
  amount_lost: 0, bank_account_no: '', bank_name: '', bank_branch_address: '',
});

function emptyForm(): CaseEntry {
  return {
    fir_no: '',
    registration_date: '',
    case_type: 'NCRP',
    crime_type: '',
    crime_type_other: '',
    sections: '',
    is_financial: true,
    facts: '',
    victim: emptyVictim(),
    // Child collections stay empty — this page never captures them.
    // Cases → Update Case handles arrests / petitions / lien-accounts
    // / unfreeze / refunds later.
    arrests: [],
    petitions: [],
    lien_accounts: [],
    unfreeze_details: [],
    refunds: [],
  };
}

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

export function DsrNewFirPage() {
  const navigate = useNavigate();
  const [f, setF] = useState<CaseEntry>(emptyForm());
  const [saving, setSaving] = useState(false);
  const [lastSavedId, setLastSavedId] = useState<string | null>(null);

  // Format-only error — surfaces once the operator starts typing.
  // Empty is not an error here (that's a required-check on Save).
  const firNoError = validateFirNo(f.fir_no);

  const handleSave = async () => {
    if (!f.fir_no.trim()) { toast.error('FIR No. is required.'); return; }
    if (firNoError) { toast.error(firNoError); return; }
    if (!f.crime_type) { toast.error('Crime Type is required.'); return; }
    setSaving(true);
    try {
      const saved = await createCase(f);
      setLastSavedId(saved.id ?? null);
      setF(emptyForm());
      toast.success(`FIR ${saved.fir_no} logged.`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <h1 className="text-[22px] font-bold mb-1"
        style={{ color: 'var(--ksp-navy)', letterSpacing: '-0.02em' }}>
        DSR — New FIR
      </h1>
      <p className="text-sm font-medium mb-6" style={{ color: 'var(--ksp-red)' }}>
        Log a fresh FIR registered today. Arrests, petitions, lien accounts
        and refunds are added later via Cases → Update Case.
      </p>

      {/* Success ribbon — visible after the previous save; auto-hides on
           the next input. Keeps the operator's chain-of-entry flow while
           still exposing the just-saved case for a quick jump-to-edit. */}
      {lastSavedId && (
        <div className="rounded-2xl p-3 mb-4 flex items-center justify-between flex-wrap gap-3"
          style={{ background: 'rgba(10,107,40,0.08)', border: '2px dashed #0a6b28' }}>
          <span className="text-sm font-semibold" style={{ color: '#0a6b28' }}>
            Last FIR saved. Ready for the next one.
          </span>
          <button type="button"
            onClick={() => navigate(`/cases/${lastSavedId}`)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold rounded-lg"
            style={{ background: '#0a6b28', color: '#fff' }}>
            Edit this case <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      <div className="space-y-5">
        <FinancialRadio value={f.is_financial}
          onChange={(v) => setF((p) => ({ ...p, is_financial: v }))} />

        <Section title="Case Information">
          <div>
            <TextField label="FIR No" value={f.fir_no}
              onChange={(v) => setF((p) => ({ ...p, fir_no: v }))}
              placeholder={FIR_NO_PLACEHOLDER} />
            {firNoError && (
              <p className="text-xs mt-1" style={{ color: 'var(--ksp-red)' }}>{firNoError}</p>
            )}
          </div>
          <TextField label="Registration Date" type="date"
            value={f.registration_date}
            onChange={(v) => setF((p) => ({ ...p, registration_date: v }))} />
          <SelectField label="Case Type" value={f.case_type}
            onChange={(v) => setF((p) => ({ ...p, case_type: v as CaseEntry['case_type'] }))}
            options={[
              { value: 'NCRP', label: 'NCRP' },
              { value: 'Walk-In', label: 'Walk-In' },
            ]} />
          <SelectField label="Crime Type" value={f.crime_type}
            onChange={(v) => setF((p) => ({
              ...p,
              crime_type: v,
              crime_type_other: v === CRIME_TYPE_OTHERS ? (p.crime_type_other ?? '') : '',
            }))}
            options={crimeTypeOptions(f.crime_type)} />
          <TextField label="Sections" value={f.sections ?? ''}
            onChange={(v) => setF((p) => ({ ...p, sections: v }))}
            placeholder="e.g. 318(4), 319, 340" />
          {f.crime_type === CRIME_TYPE_OTHERS && (
            <TextField label="Other — describe the crime type"
              wrapperClassName="lg:col-span-3"
              value={f.crime_type_other ?? ''}
              onChange={(v) => setF((p) => ({ ...p, crime_type_other: v }))}
              placeholder="Describe the classification that doesn't fit any of the listed sub-heads" />
          )}
        </Section>

        {/* Victim Details — mirrors CaseEntryPage's Tab-0 block
             verbatim so the two entry paths capture the same shape.
             Financial-only fields (amount lost, bank account, bank
             name, branch) collapse when Case Nature = Non-Financial. */}
        <Section title="Victim Details" cols={6}>
          {/* Row 1: Name + small Age/Gender */}
          <TextField label="First Name *" wrapperClassName="lg:col-span-2"
            value={f.victim?.first_name ?? ''}
            onChange={(v) => setF((p) => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), first_name: v } }))} />
          <TextField label="Last Name *" wrapperClassName="lg:col-span-2"
            value={f.victim?.last_name ?? ''}
            onChange={(v) => setF((p) => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), last_name: v } }))} />
          <NumField label="Age" wrapperClassName="lg:col-span-1"
            value={f.victim?.age ?? 0}
            onChange={(v) => setF((p) => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), age: v || null } }))} />
          <SelectField label="Gender" wrapperClassName="lg:col-span-1"
            value={f.victim?.gender ?? ''}
            onChange={(v) => setF((p) => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), gender: v as Victim['gender'] } }))}
            options={[
              { value: '', label: '—' },
              { value: 'Male', label: 'Male' },
              { value: 'Female', label: 'Female' },
              { value: 'Other', label: 'Other' },
              { value: 'Prefer not to say', label: 'Prefer not to say' },
            ]} />

          {/* Row 2: Contact + Country */}
          <TextField label="Phone" wrapperClassName="lg:col-span-2"
            value={f.victim?.phone ?? ''}
            onChange={(v) => setF((p) => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), phone: v.replace(/\D/g, '') } }))}
            placeholder="10-digit mobile" maxLength={10} inputMode="numeric" />
          <TextField label="Email" type="email" wrapperClassName="lg:col-span-2"
            value={f.victim?.email ?? ''}
            onChange={(v) => setF((p) => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), email: v } }))}
            placeholder="name@domain.com" inputMode="email" />
          <TextField label="Country" wrapperClassName="lg:col-span-2"
            value={f.victim?.country ?? 'India'}
            onChange={(v) => setF((p) => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), country: v } }))} />

          {/* Row 3: Address */}
          <TextField label="House No" wrapperClassName="lg:col-span-1"
            value={f.victim?.house_no ?? ''}
            onChange={(v) => setF((p) => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), house_no: v } }))} />
          <TextField label="Street Name" wrapperClassName="lg:col-span-2"
            value={f.victim?.street_name ?? ''}
            onChange={(v) => setF((p) => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), street_name: v } }))} />
          <TextField label="City" wrapperClassName="lg:col-span-1"
            value={f.victim?.city ?? ''}
            onChange={(v) => setF((p) => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), city: v } }))} />
          <SelectField label="State" wrapperClassName="lg:col-span-1"
            value={f.victim?.state ?? ''}
            onChange={(v) => setF((p) => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), state: v } }))}
            options={[
              { value: '', label: '—' },
              ...INDIAN_STATES.map((s) => ({ value: s, label: s })),
            ]} />
          <TextField label="Pincode" wrapperClassName="lg:col-span-1"
            value={f.victim?.pincode ?? ''}
            onChange={(v) => setF((p) => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), pincode: v.replace(/\D/g, '') } }))}
            placeholder="6-digit" maxLength={6} inputMode="numeric" />

          {/* Financial-only banking block */}
          {f.is_financial && (
            <>
              <NumField label="Amount Lost (₹) *" wrapperClassName="lg:col-span-2"
                value={f.victim?.amount_lost ?? 0}
                onChange={(v) => setF((p) => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), amount_lost: v } }))} />
              <TextField label="Bank Account No *" wrapperClassName="lg:col-span-2"
                value={f.victim?.bank_account_no ?? ''}
                onChange={(v) => setF((p) => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), bank_account_no: v.replace(/\D/g, '') } }))}
                placeholder="9–18 digits" maxLength={18} inputMode="numeric" />
              <TextField label="Bank Name *" wrapperClassName="lg:col-span-2"
                value={f.victim?.bank_name ?? ''}
                onChange={(v) => setF((p) => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), bank_name: v } }))} />
              <TextField label="Bank Branch Address" wrapperClassName="col-span-full"
                value={f.victim?.bank_branch_address ?? ''}
                onChange={(v) => setF((p) => ({ ...p, victim: { ...(p.victim ?? emptyVictim()), bank_branch_address: v } }))} />
            </>
          )}
        </Section>

        <Section title="Facts">
          <TextAreaField label="Facts" value={f.facts}
            onChange={(v) => setF((p) => ({ ...p, facts: v }))} rows={4} />
        </Section>
      </div>

      <div className="flex items-center justify-end gap-3 mt-6">
        <button type="button" onClick={() => setF(emptyForm())} disabled={saving}
          className="px-4 py-2 text-sm font-semibold rounded-xl"
          style={{ background: 'rgba(11,44,74,0.06)', color: 'var(--ksp-navy)' }}>
          Reset
        </button>
        <button type="button" onClick={handleSave}
          disabled={saving || !!firNoError}
          title={firNoError ?? undefined}
          className="flex items-center gap-1.5 px-4 py-2 text-sm font-bold rounded-xl transition disabled:opacity-50"
          style={{ background: 'var(--ksp-yellow)', color: '#000', border: '2px solid rgba(0,0,0,0.25)' }}>
          <Save className="w-4 h-4" />
          {saving ? 'Saving…' : 'Save FIR'}
        </button>
      </div>
    </div>
  );
}
