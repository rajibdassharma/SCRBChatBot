import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router';
import { toast } from 'sonner';
import { Save, ChevronRight, ChevronLeft, Plus, Trash2, X, Upload } from 'lucide-react';
import { createCase, updateCase, getCase, deleteCase } from '../lib/api/cases';
import { useAuthStore } from '../lib/stores/auth-store';
import type { CaseEntry, Arrest, Accomplice, Petition, LienAccount, UnfreezeDetail, Refund } from '../types';

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

const initialForm = (): CaseEntry => ({
  fir_no: '', registration_date: '', case_type: 'NCRP', crime_type: 'Internet', facts: '',
  arrests: [], petitions: [], lien_accounts: [], unfreeze_details: [], refunds: [],
  status: 'draft',
});

/* --- Reusable field components --- */

function TextField({ label, value, onChange, placeholder, type = 'text', readOnly = false, hint }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string; type?: string; readOnly?: boolean; hint?: string;
}) {
  return (
    <div>
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

function NumField({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <div>
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

function SelectField({ label, value, onChange, options }: {
  label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[];
}) {
  return (
    <div>
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

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl p-5" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
      <h3 className="text-sm font-bold mb-4 uppercase tracking-wide" style={{ color: 'var(--ksp-red)' }}>{title}</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">{children}</div>
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

const TABS = ['Case Details', 'Arrests', 'IR Details', 'Petitions', 'Lien Marked', 'Unfreeze', 'Refunds'];

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

  const [tab, setTab] = useState(0);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [f, setF] = useState<CaseEntry>(initialForm());
  const [caseId, setCaseId] = useState<number | undefined>(id ? Number(id) : undefined);
  const [uploadingIdx, setUploadingIdx] = useState<number | null>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setCaseId(Number(id));
    getCase(Number(id))
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

  /* --- Save Draft --- */
  const handleSaveDraft = async () => {
    setSaving(true);
    try {
      const payload = { ...f, status: 'draft' as const };
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
    if (!f.registration_date) { toast.error('Registration Date is required'); setTab(0); return; }
    setSaving(true);
    try {
      const payload = { ...f, status: 'submitted' as const };
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
        {isEdit ? 'Edit Case' : 'New Case Entry'}
      </h1>
      <p className="text-sm font-medium mb-6" style={{ color: 'var(--ksp-red)' }}>
        {isEdit ? `Editing FIR ${f.fir_no}` : 'Enter case details across all tabs'}
      </p>

      <form onSubmit={handleSubmit} className="space-y-5 max-w-5xl">
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
          <Section title="Case Information">
            <TextField label="FIR No" value={f.fir_no} onChange={(v) => setF(p => ({ ...p, fir_no: v }))} placeholder="e.g. 123/2026" readOnly={isEdit} hint={isEdit ? "FIR number cannot be changed after creation" : undefined} />
            <TextField label="Registration Date" value={f.registration_date} onChange={(v) => setF(p => ({ ...p, registration_date: v }))} type="date" />
            <SelectField label="Case Type" value={f.case_type}
              onChange={(v) => setF(p => ({ ...p, case_type: v as CaseEntry['case_type'] }))}
              options={[{ value: 'NCRP', label: 'NCRP' }, { value: 'Walk-In', label: 'Walk-In' }]} />
            <SelectField label="Crime Type" value={f.crime_type}
              onChange={(v) => setF(p => ({ ...p, crime_type: v as CaseEntry['crime_type'] }))}
              options={[{ value: 'Internet', label: 'Internet' }, { value: 'Digital', label: 'Digital' }, { value: 'Crypto', label: 'Crypto' }]} />
            <TextAreaField label="Facts" value={f.facts} onChange={(v) => setF(p => ({ ...p, facts: v }))} rows={4} />
          </Section>
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
      </form>
    </div>
  );
}
