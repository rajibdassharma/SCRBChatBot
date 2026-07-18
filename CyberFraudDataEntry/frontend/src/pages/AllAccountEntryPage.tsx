import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { toast } from 'sonner';
import { Plus, Save, Trash2, Upload, X } from 'lucide-react';
import {
  createAllAccount, deleteAllAccount, getAllAccount, updateAllAccount,
} from '../lib/api/all-accounts';
import { useAuthStore } from '../lib/stores/auth-store';
import type { AllAccount, AllAccountWritePayload, MuleHerder } from '../types';

const BASE = import.meta.env.VITE_API_BASE ?? '';

/* --- Empty factories --- */

const emptyHerder = (): MuleHerder => ({ name: '', address: '', mobile_no: '' });

const emptyForm = (): AllAccountWritePayload => ({
  fir_no: null, ncrp_ack_no: null,
  account_no: '', bank_name: '', branch_name: null, ifsc_code: null,
  account_holder_name: '', kyc_address: null, kyc_mobile: null,
  id_photo_path: null,
  account_type: 'Victim',
  mule_herders: [],
});

/* --- Reusable field components (same shape as CaseEntryPage's) --- */

function TextField({
  label, value, onChange, placeholder, type = 'text', readOnly = false,
  hint, wrapperClassName, maxLength, inputMode,
}: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string;
  type?: string; readOnly?: boolean; hint?: string;
  wrapperClassName?: string; maxLength?: number;
  inputMode?: 'text' | 'numeric' | 'email' | 'tel';
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
        type={type} value={value} maxLength={maxLength} inputMode={inputMode}
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

function TextAreaField({
  label, value, onChange, rows = 3,
}: { label: string; value: string; onChange: (v: string) => void; rows?: number }) {
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
    <div className="rounded-2xl p-5"
      style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
      <h3 className="text-sm font-bold mb-4 uppercase tracking-wide" style={{ color: 'var(--ksp-red)' }}>{title}</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {children}
      </div>
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

/** Victim / Mule pill radio — flipping to Victim clears any herders. */
function TypeRadio({ value, onChange }: { value: 'Victim' | 'Mule'; onChange: (v: 'Victim' | 'Mule') => void }) {
  const pill = (active: boolean) => ({
    background: active ? 'var(--ksp-navy)' : '#fff',
    color: active ? 'var(--ksp-yellow)' : 'var(--ksp-navy)',
    border: active ? '2px solid var(--ksp-navy)' : '2px solid rgba(11,44,74,0.18)',
    cursor: 'pointer' as const,
  });
  return (
    <div className="rounded-2xl p-4 flex items-center gap-4"
      style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
      <span className="text-xs font-bold uppercase tracking-wide" style={{ color: 'var(--ksp-red)' }}>Account Type</span>
      <label className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold transition" style={pill(value === 'Victim')}>
        <input type="radio" className="sr-only" checked={value === 'Victim'} onChange={() => onChange('Victim')} />
        Victim
      </label>
      <label className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold transition" style={pill(value === 'Mule')}>
        <input type="radio" className="sr-only" checked={value === 'Mule'} onChange={() => onChange('Mule')} />
        Mule
      </label>
      <p className="text-xs opacity-60 ml-2">
        {value === 'Mule'
          ? 'Mule herder rows appear below — add one per person.'
          : 'Herder rows are hidden — they only apply to Mule accounts.'}
      </p>
    </div>
  );
}

/* --- Main component --- */

export function AllAccountEntryPage() {
  const { id } = useParams<{ id: string }>();
  const isEdit = !!id;
  const navigate = useNavigate();
  const { user } = useAuthStore();

  const [f, setF] = useState<AllAccountWritePayload>(emptyForm());
  const [existing, setExisting] = useState<AllAccount | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getAllAccount(id)
      .then((data) => {
        setExisting(data);
        setF({
          fir_no: data.fir_no,
          ncrp_ack_no: data.ncrp_ack_no,
          account_no: data.account_no,
          bank_name: data.bank_name,
          branch_name: data.branch_name,
          ifsc_code: data.ifsc_code,
          account_holder_name: data.account_holder_name,
          kyc_address: data.kyc_address,
          kyc_mobile: data.kyc_mobile,
          id_photo_path: data.id_photo_path,
          account_type: data.account_type,
          mule_herders: data.mule_herders.map((h) => ({
            id: h.id, name: h.name, address: h.address, mobile_no: h.mobile_no,
          })),
        });
      })
      .catch((err) => toast.error(`Failed to load account: ${err.message}`))
      .finally(() => setLoading(false));
  }, [id]);

  const upd = <K extends keyof AllAccountWritePayload>(k: K, v: AllAccountWritePayload[K]) =>
    setF((p) => ({ ...p, [k]: v }));

  /** Reuses the existing /api/v1/uploads/photo endpoint the accused-photo
   *  flow uses — accepts image/pdf, 500KB cap on the server. */
  const handlePhotoUpload = async (file: File) => {
    setUploading(true);
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
      upd('id_photo_path', data.photo_path);
      toast.success('Photo uploaded');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const handleSave = async () => {
    if (!f.account_no.trim())          { toast.error('Account No is required'); return; }
    if (!f.bank_name.trim())           { toast.error('Bank Name is required'); return; }
    if (!f.account_holder_name.trim()) { toast.error('Account Holder Name is required'); return; }
    if (f.account_type === 'Mule') {
      const badHerder = f.mule_herders.find((h) => !h.name?.trim());
      if (badHerder) { toast.error('Each Mule Herder needs a name'); return; }
    }

    setSaving(true);
    try {
      // Coerce empty strings to null so blanks land as NULL in the DB
      // (matches how the Case entry form serialises optional strings).
      const payload: AllAccountWritePayload = {
        ...f,
        fir_no: f.fir_no?.trim() || null,
        ncrp_ack_no: f.ncrp_ack_no?.trim() || null,
        branch_name: f.branch_name?.trim() || null,
        ifsc_code: f.ifsc_code?.trim() || null,
        kyc_address: f.kyc_address?.trim() || null,
        kyc_mobile: f.kyc_mobile?.trim() || null,
        id_photo_path: f.id_photo_path?.trim() || null,
        mule_herders: f.account_type === 'Mule'
          ? f.mule_herders.map((h) => ({
              id: h.id,
              name: h.name.trim(),
              address: h.address?.trim() || null,
              mobile_no: h.mobile_no?.trim() || null,
            }))
          : [],   // Victim never carries herders.
      };
      const saved = isEdit
        ? await updateAllAccount(id!, payload)
        : await createAllAccount(payload);
      toast.success(isEdit ? 'Account updated' : `Account saved (Serial No ${saved.serial_no})`);
      navigate('/all-accounts/update');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = async () => {
    if (!isEdit) {
      navigate('/all-accounts/update');
      return;
    }
    if (!window.confirm('Delete this account record? This cannot be undone.')) return;
    try {
      await deleteAllAccount(id!);
      toast.success('Account deleted');
      navigate('/all-accounts/update');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Delete failed');
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center py-20"><span className="text-sm text-slate-400">Loading...</span></div>;
  }

  return (
    <div>
      {/* Header — same navy strip as Case Entry / Mule Report */}
      <div className="rounded-2xl p-4 mb-4" style={{ background: 'var(--ksp-navy)', color: '#fff' }}>
        <h1 className="text-lg font-bold" style={{ color: 'var(--ksp-yellow)' }}>All Accounts</h1>
        <div className="flex gap-6 mt-2 text-sm">
          <span><strong>District:</strong> {user?.unit_name}</span>
          <span><strong>CCPS:</strong> {user?.ps_name || 'N/A'}</span>
          <span><strong>User:</strong> {user?.username}</span>
          {existing && (
            <span><strong>Serial No:</strong> {existing.serial_no}</span>
          )}
        </div>
      </div>

      <h1 className="text-[22px] font-bold mb-1" style={{ color: 'var(--ksp-navy)' }}>
        {isEdit ? 'Edit Account' : 'New Account'}
      </h1>
      <p className="text-sm font-medium mb-6" style={{ color: 'var(--ksp-red)' }}>
        {isEdit
          ? `Editing account #${existing?.serial_no ?? '…'}`
          : 'Serial No is assigned automatically on save.'}
      </p>

      <div className="space-y-5 max-w-5xl">
        <Section title="Case Reference">
          <TextField label="FIR No" value={f.fir_no ?? ''}
            onChange={(v) => upd('fir_no', v)} placeholder="e.g. 123/2026" />
          <TextField label="NCRP Ack No" value={f.ncrp_ack_no ?? ''}
            onChange={(v) => upd('ncrp_ack_no', v)}
            placeholder="e.g. 30811260070042" />
        </Section>

        <Section title="Account Details">
          <TextField label="Account No *" value={f.account_no}
            onChange={(v) => upd('account_no', v)} />
          <TextField label="Bank Name *" value={f.bank_name}
            onChange={(v) => upd('bank_name', v)} />
          <TextField label="Branch Name" value={f.branch_name ?? ''}
            onChange={(v) => upd('branch_name', v)} />
          <TextField label="IFSC Code" value={f.ifsc_code ?? ''}
            onChange={(v) => upd('ifsc_code', v.toUpperCase())}
            maxLength={11} placeholder="e.g. HDFC0001234" />
        </Section>

        <Section title="Account Holder — KYC">
          <TextField label="Name of Account Holder *"
            value={f.account_holder_name}
            onChange={(v) => upd('account_holder_name', v)} />
          <TextField label="Mobile No" value={f.kyc_mobile ?? ''}
            onChange={(v) => upd('kyc_mobile', v.replace(/\D/g, ''))}
            maxLength={10} inputMode="tel" placeholder="10-digit mobile" />
          <TextAreaField label="KYC Address" value={f.kyc_address ?? ''}
            onChange={(v) => upd('kyc_address', v)} rows={2} />
        </Section>

        {/* ID document — reuses the /api/v1/uploads/photo endpoint. */}
        <div className="rounded-2xl p-5"
          style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
          <h3 className="text-sm font-bold mb-4 uppercase tracking-wide" style={{ color: 'var(--ksp-red)' }}>ID Document</h3>
          <div className="flex items-center gap-4">
            {f.id_photo_path ? (
              <>
                <img
                  src={`${BASE}/${f.id_photo_path}`}
                  alt="ID document"
                  className="w-24 h-24 rounded-xl object-cover"
                  style={{ border: '2px solid var(--ksp-navy)' }}
                />
                <div className="space-x-2">
                  <label className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg cursor-pointer transition"
                    style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)', border: '2px solid rgba(0,0,0,0.25)' }}>
                    <Upload className="w-3.5 h-3.5" /> Replace
                    <input type="file" accept="image/*" className="hidden"
                      disabled={uploading}
                      onChange={(e) => { const file = e.target.files?.[0]; if (file) handlePhotoUpload(file); }} />
                  </label>
                  <button type="button"
                    onClick={() => upd('id_photo_path', null)}
                    className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold rounded-lg"
                    style={{ background: 'rgba(177,0,0,0.08)', color: 'var(--ksp-red)', border: '1px solid rgba(177,0,0,0.2)' }}>
                    <X className="w-3.5 h-3.5" /> Remove
                  </button>
                </div>
              </>
            ) : (
              <label className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-xl cursor-pointer transition"
                style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)', border: '2px solid rgba(0,0,0,0.25)' }}>
                <Upload className="w-4 h-4" /> {uploading ? 'Uploading…' : 'Upload ID Photo'}
                <input type="file" accept="image/*" className="hidden"
                  disabled={uploading}
                  onChange={(e) => { const file = e.target.files?.[0]; if (file) handlePhotoUpload(file); }} />
              </label>
            )}
          </div>
        </div>

        <TypeRadio value={f.account_type}
          onChange={(v) => {
            upd('account_type', v);
            if (v === 'Victim') upd('mule_herders', []);
          }} />

        {/* Mule Herders (only when type = 'Mule'). */}
        {f.account_type === 'Mule' && (
          <div className="space-y-5">
            {f.mule_herders.map((h, hi) => (
              <div key={hi} className="rounded-2xl p-5 space-y-4"
                style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-bold uppercase tracking-wide" style={{ color: 'var(--ksp-red)' }}>Mule Herder #{hi + 1}</h3>
                  <RemBtn onClick={() =>
                    setF((p) => ({ ...p, mule_herders: p.mule_herders.filter((_, i) => i !== hi) }))
                  } />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  <TextField label="Name *" value={h.name}
                    onChange={(v) => {
                      const arr = [...f.mule_herders]; arr[hi] = { ...arr[hi], name: v };
                      setF((p) => ({ ...p, mule_herders: arr }));
                    }} />
                  <TextField label="Mobile No" value={h.mobile_no ?? ''}
                    onChange={(v) => {
                      const arr = [...f.mule_herders];
                      arr[hi] = { ...arr[hi], mobile_no: v.replace(/\D/g, '') };
                      setF((p) => ({ ...p, mule_herders: arr }));
                    }}
                    maxLength={10} inputMode="tel" />
                  <TextAreaField label="Address" value={h.address ?? ''}
                    onChange={(v) => {
                      const arr = [...f.mule_herders]; arr[hi] = { ...arr[hi], address: v };
                      setF((p) => ({ ...p, mule_herders: arr }));
                    }} rows={2} />
                </div>
              </div>
            ))}
            <AddBtn label="Add Mule Herder"
              onClick={() => setF((p) => ({ ...p, mule_herders: [...p.mule_herders, emptyHerder()] }))} />
          </div>
        )}

        {/* Save + Cancel */}
        <div className="flex items-center justify-end gap-3">
          <button type="button" onClick={handleCancel}
            className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-xl transition"
            style={{ background: 'rgba(177,0,0,0.08)', color: 'var(--ksp-red)', border: '2px solid rgba(177,0,0,0.3)' }}>
            <X className="w-4 h-4" /> {isEdit ? 'Delete' : 'Cancel'}
          </button>
          <button type="button" onClick={handleSave} disabled={saving}
            className="flex items-center gap-2 px-6 py-2.5 font-bold rounded-xl transition disabled:opacity-50"
            style={{ background: 'var(--ksp-yellow)', color: '#000', border: '2px solid rgba(0,0,0,0.25)' }}>
            <Save className="w-4 h-4" />
            {saving ? 'Saving…' : (isEdit ? 'Update Account' : 'Save Account')}
          </button>
        </div>
      </div>
    </div>
  );
}
