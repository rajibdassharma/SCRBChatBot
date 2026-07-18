import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router';
import { toast } from 'sonner';
import { Save, ChevronRight, ChevronLeft, Plus, Trash2, X, Upload } from 'lucide-react';
import { createMuleReport, updateMuleReport, getMuleReport, deleteMuleReport, parseMuleExcel } from '../lib/api/mule-reports';
import { useAuthStore } from '../lib/stores/auth-store';
import type {
  MuleReport,
  MoneyTransfer,
  OtherTransaction,
  TransactionOnHold,
  OtherLessThan500,
  AepsTransaction,
  AtmWithdrawal,
} from '../types';

/* --- Empty factories --- */

const emptyMoneyTransfer = (): MoneyTransfer => ({
  account_no: '', transaction_id: '', bank: '', layer: 1, dest_account_no: '',
  ifsc_code: '', transaction_date: '', dest_transaction_id: '',
  transaction_amount: 0, disputed_amount: 0, reference_no: '', remarks: '',
  action_taken_by_bank: '', date_of_action: '',
});

const emptyOtherTransaction = (): OtherTransaction => ({
  account_no: '', transaction_id: '', transaction_date: '', transaction_amount: 0,
  reference_no: '', remarks: '', action_taken_by_bank: '', date_of_action: '',
});

const emptyTransactionOnHold = (): TransactionOnHold => ({
  account_no: '', transaction_id: '', hold_date: '', hold_amount: 0,
  action_taken_by_bank: '', date_of_action: '', layer: 1,
});

const emptyOtherLessThan500 = (): OtherLessThan500 => ({
  account_no: '', transaction_id: '', reference_no: '', remarks: '',
  action_taken_by_bank: '', date_of_action: '',
});

const emptyAepsTransaction = (): AepsTransaction => ({
  account_no: '', transaction_id: '', withdrawal_date: '', withdrawal_amount: 0,
  reference_no: '', remarks: '', action_taken_by_bank: '', date_of_action: '', layer: 1,
});

const emptyAtmWithdrawal = (): AtmWithdrawal => ({
  account_no: '', transaction_id: '', withdrawal_datetime: '', withdrawal_amount: 0,
  disputed_amount: 0, atm_id: '', atm_location: '', reference_no: '', remarks: '',
  action_taken_by_bank: '', date_of_action: '',
});

const initialForm = (): MuleReport => ({
  acknowledgement_no: '', fir_no: '',
  money_transfers: [], other_transactions: [], transactions_on_hold: [],
  others_less_than_500: [], aeps_transactions: [], atm_withdrawals: [],
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

function NumField({ label, value, onChange, readOnly = false }: { label: string; value: number; onChange: (v: number) => void; readOnly?: boolean }) {
  return (
    <div>
      <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>{label}</label>
      <input
        type="number"
        min={0}
        value={value || ''}
        onChange={(e) => !readOnly && onChange(Number(e.target.value) || 0)}
        readOnly={readOnly}
        className="w-full px-3 py-2 rounded-xl text-sm outline-none"
        style={{ border: readOnly ? '1px solid rgba(11,44,74,0.15)' : '2px solid var(--ksp-navy)', background: readOnly ? 'rgba(11,44,74,0.04)' : '#fff' }}
        placeholder={readOnly ? '' : '0'}
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

const TABS = ['Money Transfer To', 'Other', 'Transaction On Hold', 'Others < 500', 'AEPS', 'ATM Withdrawal'];

/* --- Helper to update an item in a child array --- */

function updateChild<T>(arr: T[], idx: number, patch: Partial<T>): T[] {
  const copy = [...arr];
  copy[idx] = { ...copy[idx], ...patch };
  return copy;
}

/* --- Main Component --- */

export function MuleReportEntryPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const isEdit = !!id;

  const [tab, setTab] = useState(0);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [f, setF] = useState<MuleReport>(initialForm());
  const [reportId, setReportId] = useState<string | undefined>(id);

  // Upload Excel to populate form
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [parsing, setParsing] = useState(false);
  const [fromExcel, setFromExcel] = useState(false);

  const handleExcelUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;
    const file = files[0];
    if (!file.name.endsWith('.xlsx') && !file.name.endsWith('.xls')) {
      toast.error('Only .xlsx or .xls files are accepted');
      return;
    }
    setParsing(true);
    try {
      const data = await parseMuleExcel(file);
      setF(p => ({
        ...p,
        acknowledgement_no: data.acknowledgement_no || p.acknowledgement_no,
        fir_no: data.fir_no || p.fir_no,
        money_transfers: data.money_transfers || [],
        other_transactions: data.other_transactions || [],
        transactions_on_hold: data.transactions_on_hold || [],
        others_less_than_500: data.others_less_than_500 || [],
        aeps_transactions: data.aeps_transactions || [],
        atm_withdrawals: data.atm_withdrawals || [],
      }));
      setFromExcel(true);
      const total = (data.money_transfers?.length || 0) + (data.other_transactions?.length || 0) +
        (data.transactions_on_hold?.length || 0) + (data.others_less_than_500?.length || 0) +
        (data.aeps_transactions?.length || 0) + (data.atm_withdrawals?.length || 0);
      toast.success(`Populated ${total} transactions from ${file.name}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to parse file');
    } finally {
      setParsing(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setReportId(id);
    getMuleReport(id)
      .then((data) => setF({ ...initialForm(), ...data }))
      .catch((err) => toast.error(`Failed to load report: ${err.message}`))
      .finally(() => setLoading(false));
  }, [id]);

  /* --- Save Draft --- */
  const handleSaveDraft = async () => {
    setSaving(true);
    try {
      const payload = { ...f, status: 'draft' as const };
      if (reportId) {
        await updateMuleReport(reportId, payload);
        toast.success('Draft saved');
      } else {
        const created = await createMuleReport(payload);
        setReportId(created.id);
        toast.success('Draft saved');
        navigate(`/mule/${created.id}`, { replace: true });
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
    if (!f.acknowledgement_no.trim()) { toast.error('Acknowledgement No is required'); return; }
    if (!f.fir_no.trim()) { toast.error('FIR No is required'); return; }
    setSaving(true);
    try {
      const payload = { ...f, status: 'submitted' as const };
      if (reportId) {
        await updateMuleReport(reportId, payload);
        toast.success('Report submitted');
      } else {
        await createMuleReport(payload);
        toast.success('Report submitted');
      }
      navigate('/mule');
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
      if (reportId) {
        await deleteMuleReport(reportId);
      }
      toast.success('Report cancelled');
      navigate('/mule');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Cancel failed');
    }
  };

  if (loading) return <div className="flex items-center justify-center py-20"><span className="text-sm text-slate-400">Loading...</span></div>;

  return (
    <div>
      {/* Header */}
      <div className="rounded-2xl p-4 mb-4" style={{ background: 'var(--ksp-navy)', color: '#fff' }}>
        <h1 className="text-lg font-bold" style={{ color: 'var(--ksp-yellow)' }}>NCRP Data</h1>
        <div className="flex gap-6 mt-2 text-sm">
          <span><strong>District:</strong> {user?.unit_name}</span>
          <span><strong>CCPS:</strong> {user?.ps_name || 'N/A'}</span>
          <span><strong>User:</strong> {user?.username}</span>
        </div>
      </div>

      <h1 className="text-[22px] font-bold mb-1" style={{ color: 'var(--ksp-navy)' }}>
        {isEdit ? 'Edit Mule Report' : 'New Mule Report'}
      </h1>
      <p className="text-sm font-medium mb-6" style={{ color: 'var(--ksp-red)' }}>
        {isEdit ? `Editing ${f.acknowledgement_no}` : 'Enter mule account transactions across all tabs, or upload Excel files'}
      </p>

      {/* Upload Excel button — only on New Report */}
      {!isEdit && (
        <div className="mb-4">
          <button type="button" onClick={() => fileInputRef.current?.click()} disabled={parsing}
            className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold rounded-xl transition disabled:opacity-50"
            style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)', border: '2px solid rgba(0,0,0,0.25)' }}>
            <Upload className="w-4 h-4" /> {parsing ? 'Parsing...' : 'Upload Excel File'}
          </button>
          <input ref={fileInputRef} type="file" accept=".xlsx,.xls" onChange={handleExcelUpload} className="hidden" />
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-5 max-w-5xl">
        {/* Top fields always visible */}
        <Section title="Report Information">
          <TextField
            readOnly={isEdit || fromExcel}
            hint={isEdit ? "Acknowledgement number cannot be changed after creation" : undefined}
            label="Acknowledgement No"
            value={f.acknowledgement_no}
            onChange={(v) => setF(p => ({ ...p, acknowledgement_no: v }))}
            placeholder="e.g. ACK-2026-001"
          />
          <TextField
            readOnly={isEdit || fromExcel}
            hint={isEdit ? "FIR number cannot be changed after creation" : undefined}
            label="FIR No"
            value={f.fir_no}
            onChange={(v) => setF(p => ({ ...p, fir_no: v }))}
            placeholder="e.g. 123/2026"
          />
        </Section>

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

        {/* === TAB 1 -- Money Transfer To === */}
        {tab === 0 && (
          <div className="space-y-5">
            {f.money_transfers.map((mt, i) => (
              <div key={i} className="rounded-2xl p-5" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-bold uppercase tracking-wide" style={{ color: 'var(--ksp-red)' }}>Transfer #{i + 1}</h3>
                  {!fromExcel && <RemBtn onClick={() => setF(p => ({ ...p, money_transfers: p.money_transfers.filter((_, j) => j !== i) }))} />}
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  <TextField readOnly={fromExcel} label="Account No" value={mt.account_no} onChange={(v) => setF(p => ({ ...p, money_transfers: updateChild(p.money_transfers, i, { account_no: v }) }))} />
                  <TextField readOnly={fromExcel} label="Transaction ID" value={mt.transaction_id} onChange={(v) => setF(p => ({ ...p, money_transfers: updateChild(p.money_transfers, i, { transaction_id: v }) }))} />
                  <TextField readOnly={fromExcel} label="Bank" value={mt.bank} onChange={(v) => setF(p => ({ ...p, money_transfers: updateChild(p.money_transfers, i, { bank: v }) }))} />
                  <NumField readOnly={fromExcel} label="Layer" value={mt.layer} onChange={(v) => setF(p => ({ ...p, money_transfers: updateChild(p.money_transfers, i, { layer: v }) }))} />
                  <TextField readOnly={fromExcel} label="Dest Account No" value={mt.dest_account_no} onChange={(v) => setF(p => ({ ...p, money_transfers: updateChild(p.money_transfers, i, { dest_account_no: v }) }))} />
                  <TextField readOnly={fromExcel} label="IFSC Code" value={mt.ifsc_code} onChange={(v) => setF(p => ({ ...p, money_transfers: updateChild(p.money_transfers, i, { ifsc_code: v }) }))} />
                  <TextField readOnly={fromExcel} label="Transaction Date" value={mt.transaction_date} onChange={(v) => setF(p => ({ ...p, money_transfers: updateChild(p.money_transfers, i, { transaction_date: v }) }))} type="date" />
                  <TextField readOnly={fromExcel} label="Dest Transaction ID" value={mt.dest_transaction_id} onChange={(v) => setF(p => ({ ...p, money_transfers: updateChild(p.money_transfers, i, { dest_transaction_id: v }) }))} />
                  <NumField readOnly={fromExcel} label="Transaction Amount" value={mt.transaction_amount} onChange={(v) => setF(p => ({ ...p, money_transfers: updateChild(p.money_transfers, i, { transaction_amount: v }) }))} />
                  <NumField readOnly={fromExcel} label="Disputed Amount" value={mt.disputed_amount} onChange={(v) => setF(p => ({ ...p, money_transfers: updateChild(p.money_transfers, i, { disputed_amount: v }) }))} />
                  <TextField readOnly={fromExcel} label="Reference No" value={mt.reference_no} onChange={(v) => setF(p => ({ ...p, money_transfers: updateChild(p.money_transfers, i, { reference_no: v }) }))} />
                  <TextField readOnly={fromExcel} label="Remarks" value={mt.remarks} onChange={(v) => setF(p => ({ ...p, money_transfers: updateChild(p.money_transfers, i, { remarks: v }) }))} />
                  <TextField readOnly={fromExcel} label="Action Taken By Bank" value={mt.action_taken_by_bank} onChange={(v) => setF(p => ({ ...p, money_transfers: updateChild(p.money_transfers, i, { action_taken_by_bank: v }) }))} />
                  <TextField readOnly={fromExcel} label="Date of Action" value={mt.date_of_action} onChange={(v) => setF(p => ({ ...p, money_transfers: updateChild(p.money_transfers, i, { date_of_action: v }) }))} type="date" />
                </div>
              </div>
            ))}
            {!fromExcel && <AddBtn onClick={() => setF(p => ({ ...p, money_transfers: [...p.money_transfers, emptyMoneyTransfer()] }))} label="Add Transfer" />}
          </div>
        )}

        {/* === TAB 2 -- Other === */}
        {tab === 1 && (
          <div className="space-y-5">
            {f.other_transactions.map((ot, i) => (
              <div key={i} className="rounded-2xl p-5" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-bold uppercase tracking-wide" style={{ color: 'var(--ksp-red)' }}>Other #{i + 1}</h3>
                  {!fromExcel && <RemBtn onClick={() => setF(p => ({ ...p, other_transactions: p.other_transactions.filter((_, j) => j !== i) }))} />}
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  <TextField readOnly={fromExcel} label="Account No" value={ot.account_no} onChange={(v) => setF(p => ({ ...p, other_transactions: updateChild(p.other_transactions, i, { account_no: v }) }))} />
                  <TextField readOnly={fromExcel} label="Transaction ID" value={ot.transaction_id} onChange={(v) => setF(p => ({ ...p, other_transactions: updateChild(p.other_transactions, i, { transaction_id: v }) }))} />
                  <TextField readOnly={fromExcel} label="Transaction Date" value={ot.transaction_date} onChange={(v) => setF(p => ({ ...p, other_transactions: updateChild(p.other_transactions, i, { transaction_date: v }) }))} type="date" />
                  <NumField readOnly={fromExcel} label="Transaction Amount" value={ot.transaction_amount} onChange={(v) => setF(p => ({ ...p, other_transactions: updateChild(p.other_transactions, i, { transaction_amount: v }) }))} />
                  <TextField readOnly={fromExcel} label="Reference No" value={ot.reference_no} onChange={(v) => setF(p => ({ ...p, other_transactions: updateChild(p.other_transactions, i, { reference_no: v }) }))} />
                  <TextField readOnly={fromExcel} label="Remarks" value={ot.remarks} onChange={(v) => setF(p => ({ ...p, other_transactions: updateChild(p.other_transactions, i, { remarks: v }) }))} />
                  <TextField readOnly={fromExcel} label="Action Taken By Bank" value={ot.action_taken_by_bank} onChange={(v) => setF(p => ({ ...p, other_transactions: updateChild(p.other_transactions, i, { action_taken_by_bank: v }) }))} />
                  <TextField readOnly={fromExcel} label="Date of Action" value={ot.date_of_action} onChange={(v) => setF(p => ({ ...p, other_transactions: updateChild(p.other_transactions, i, { date_of_action: v }) }))} type="date" />
                </div>
              </div>
            ))}
            {!fromExcel && <AddBtn onClick={() => setF(p => ({ ...p, other_transactions: [...p.other_transactions, emptyOtherTransaction()] }))} label="Add Other Transaction" />}
          </div>
        )}

        {/* === TAB 3 -- Transaction Put on Hold === */}
        {tab === 2 && (
          <div className="space-y-5">
            {f.transactions_on_hold.map((th, i) => (
              <div key={i} className="rounded-2xl p-5" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-bold uppercase tracking-wide" style={{ color: 'var(--ksp-red)' }}>Hold #{i + 1}</h3>
                  {!fromExcel && <RemBtn onClick={() => setF(p => ({ ...p, transactions_on_hold: p.transactions_on_hold.filter((_, j) => j !== i) }))} />}
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  <TextField readOnly={fromExcel} label="Account No" value={th.account_no} onChange={(v) => setF(p => ({ ...p, transactions_on_hold: updateChild(p.transactions_on_hold, i, { account_no: v }) }))} />
                  <TextField readOnly={fromExcel} label="Transaction ID" value={th.transaction_id} onChange={(v) => setF(p => ({ ...p, transactions_on_hold: updateChild(p.transactions_on_hold, i, { transaction_id: v }) }))} />
                  <TextField readOnly={fromExcel} label="Hold Date" value={th.hold_date} onChange={(v) => setF(p => ({ ...p, transactions_on_hold: updateChild(p.transactions_on_hold, i, { hold_date: v }) }))} type="date" />
                  <NumField readOnly={fromExcel} label="Hold Amount" value={th.hold_amount} onChange={(v) => setF(p => ({ ...p, transactions_on_hold: updateChild(p.transactions_on_hold, i, { hold_amount: v }) }))} />
                  <TextField readOnly={fromExcel} label="Action Taken By Bank" value={th.action_taken_by_bank} onChange={(v) => setF(p => ({ ...p, transactions_on_hold: updateChild(p.transactions_on_hold, i, { action_taken_by_bank: v }) }))} />
                  <TextField readOnly={fromExcel} label="Date of Action" value={th.date_of_action} onChange={(v) => setF(p => ({ ...p, transactions_on_hold: updateChild(p.transactions_on_hold, i, { date_of_action: v }) }))} type="date" />
                  <NumField readOnly={fromExcel} label="Layer" value={th.layer} onChange={(v) => setF(p => ({ ...p, transactions_on_hold: updateChild(p.transactions_on_hold, i, { layer: v }) }))} />
                </div>
              </div>
            ))}
            {!fromExcel && <AddBtn onClick={() => setF(p => ({ ...p, transactions_on_hold: [...p.transactions_on_hold, emptyTransactionOnHold()] }))} label="Add Hold" />}
          </div>
        )}

        {/* === TAB 4 -- Others Less Than 500 === */}
        {tab === 3 && (
          <div className="space-y-5">
            {f.others_less_than_500.map((ol, i) => (
              <div key={i} className="rounded-2xl p-5" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-bold uppercase tracking-wide" style={{ color: 'var(--ksp-red)' }}>Entry #{i + 1}</h3>
                  {!fromExcel && <RemBtn onClick={() => setF(p => ({ ...p, others_less_than_500: p.others_less_than_500.filter((_, j) => j !== i) }))} />}
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  <TextField readOnly={fromExcel} label="Account No" value={ol.account_no} onChange={(v) => setF(p => ({ ...p, others_less_than_500: updateChild(p.others_less_than_500, i, { account_no: v }) }))} />
                  <TextField readOnly={fromExcel} label="Transaction ID" value={ol.transaction_id} onChange={(v) => setF(p => ({ ...p, others_less_than_500: updateChild(p.others_less_than_500, i, { transaction_id: v }) }))} />
                  <TextField readOnly={fromExcel} label="Reference No" value={ol.reference_no} onChange={(v) => setF(p => ({ ...p, others_less_than_500: updateChild(p.others_less_than_500, i, { reference_no: v }) }))} />
                  <TextField readOnly={fromExcel} label="Remarks" value={ol.remarks} onChange={(v) => setF(p => ({ ...p, others_less_than_500: updateChild(p.others_less_than_500, i, { remarks: v }) }))} />
                  <TextField readOnly={fromExcel} label="Action Taken By Bank" value={ol.action_taken_by_bank} onChange={(v) => setF(p => ({ ...p, others_less_than_500: updateChild(p.others_less_than_500, i, { action_taken_by_bank: v }) }))} />
                  <TextField readOnly={fromExcel} label="Date of Action" value={ol.date_of_action} onChange={(v) => setF(p => ({ ...p, others_less_than_500: updateChild(p.others_less_than_500, i, { date_of_action: v }) }))} type="date" />
                </div>
              </div>
            ))}
            {!fromExcel && <AddBtn onClick={() => setF(p => ({ ...p, others_less_than_500: [...p.others_less_than_500, emptyOtherLessThan500()] }))} label="Add Entry" />}
          </div>
        )}

        {/* === TAB 5 -- AEPS === */}
        {tab === 4 && (
          <div className="space-y-5">
            {f.aeps_transactions.map((ae, i) => (
              <div key={i} className="rounded-2xl p-5" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-bold uppercase tracking-wide" style={{ color: 'var(--ksp-red)' }}>AEPS #{i + 1}</h3>
                  {!fromExcel && <RemBtn onClick={() => setF(p => ({ ...p, aeps_transactions: p.aeps_transactions.filter((_, j) => j !== i) }))} />}
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  <TextField readOnly={fromExcel} label="Account No" value={ae.account_no} onChange={(v) => setF(p => ({ ...p, aeps_transactions: updateChild(p.aeps_transactions, i, { account_no: v }) }))} />
                  <TextField readOnly={fromExcel} label="Transaction ID" value={ae.transaction_id} onChange={(v) => setF(p => ({ ...p, aeps_transactions: updateChild(p.aeps_transactions, i, { transaction_id: v }) }))} />
                  <TextField readOnly={fromExcel} label="Withdrawal Date" value={ae.withdrawal_date} onChange={(v) => setF(p => ({ ...p, aeps_transactions: updateChild(p.aeps_transactions, i, { withdrawal_date: v }) }))} type="date" />
                  <NumField readOnly={fromExcel} label="Withdrawal Amount" value={ae.withdrawal_amount} onChange={(v) => setF(p => ({ ...p, aeps_transactions: updateChild(p.aeps_transactions, i, { withdrawal_amount: v }) }))} />
                  <TextField readOnly={fromExcel} label="Reference No" value={ae.reference_no} onChange={(v) => setF(p => ({ ...p, aeps_transactions: updateChild(p.aeps_transactions, i, { reference_no: v }) }))} />
                  <TextField readOnly={fromExcel} label="Remarks" value={ae.remarks} onChange={(v) => setF(p => ({ ...p, aeps_transactions: updateChild(p.aeps_transactions, i, { remarks: v }) }))} />
                  <TextField readOnly={fromExcel} label="Action Taken By Bank" value={ae.action_taken_by_bank} onChange={(v) => setF(p => ({ ...p, aeps_transactions: updateChild(p.aeps_transactions, i, { action_taken_by_bank: v }) }))} />
                  <TextField readOnly={fromExcel} label="Date of Action" value={ae.date_of_action} onChange={(v) => setF(p => ({ ...p, aeps_transactions: updateChild(p.aeps_transactions, i, { date_of_action: v }) }))} type="date" />
                  <NumField readOnly={fromExcel} label="Layer" value={ae.layer} onChange={(v) => setF(p => ({ ...p, aeps_transactions: updateChild(p.aeps_transactions, i, { layer: v }) }))} />
                </div>
              </div>
            ))}
            {!fromExcel && <AddBtn onClick={() => setF(p => ({ ...p, aeps_transactions: [...p.aeps_transactions, emptyAepsTransaction()] }))} label="Add AEPS" />}
          </div>
        )}

        {/* === TAB 6 -- ATM Withdrawal === */}
        {tab === 5 && (
          <div className="space-y-5">
            {f.atm_withdrawals.map((aw, i) => (
              <div key={i} className="rounded-2xl p-5" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-bold uppercase tracking-wide" style={{ color: 'var(--ksp-red)' }}>ATM #{i + 1}</h3>
                  {!fromExcel && <RemBtn onClick={() => setF(p => ({ ...p, atm_withdrawals: p.atm_withdrawals.filter((_, j) => j !== i) }))} />}
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  <TextField readOnly={fromExcel} label="Account No" value={aw.account_no} onChange={(v) => setF(p => ({ ...p, atm_withdrawals: updateChild(p.atm_withdrawals, i, { account_no: v }) }))} />
                  <TextField readOnly={fromExcel} label="Transaction ID" value={aw.transaction_id} onChange={(v) => setF(p => ({ ...p, atm_withdrawals: updateChild(p.atm_withdrawals, i, { transaction_id: v }) }))} />
                  <TextField readOnly={fromExcel} label="Date/Time" value={aw.withdrawal_datetime} onChange={(v) => setF(p => ({ ...p, atm_withdrawals: updateChild(p.atm_withdrawals, i, { withdrawal_datetime: v }) }))} type="datetime-local" />
                  <NumField readOnly={fromExcel} label="Withdrawal Amount" value={aw.withdrawal_amount} onChange={(v) => setF(p => ({ ...p, atm_withdrawals: updateChild(p.atm_withdrawals, i, { withdrawal_amount: v }) }))} />
                  <NumField readOnly={fromExcel} label="Disputed Amount" value={aw.disputed_amount} onChange={(v) => setF(p => ({ ...p, atm_withdrawals: updateChild(p.atm_withdrawals, i, { disputed_amount: v }) }))} />
                  <TextField readOnly={fromExcel} label="ATM ID" value={aw.atm_id} onChange={(v) => setF(p => ({ ...p, atm_withdrawals: updateChild(p.atm_withdrawals, i, { atm_id: v }) }))} />
                  <TextField readOnly={fromExcel} label="ATM Location" value={aw.atm_location} onChange={(v) => setF(p => ({ ...p, atm_withdrawals: updateChild(p.atm_withdrawals, i, { atm_location: v }) }))} />
                  <TextField readOnly={fromExcel} label="Reference No" value={aw.reference_no} onChange={(v) => setF(p => ({ ...p, atm_withdrawals: updateChild(p.atm_withdrawals, i, { reference_no: v }) }))} />
                  <TextField readOnly={fromExcel} label="Remarks" value={aw.remarks} onChange={(v) => setF(p => ({ ...p, atm_withdrawals: updateChild(p.atm_withdrawals, i, { remarks: v }) }))} />
                  <TextField readOnly={fromExcel} label="Action Taken By Bank" value={aw.action_taken_by_bank} onChange={(v) => setF(p => ({ ...p, atm_withdrawals: updateChild(p.atm_withdrawals, i, { action_taken_by_bank: v }) }))} />
                  <TextField readOnly={fromExcel} label="Date of Action" value={aw.date_of_action} onChange={(v) => setF(p => ({ ...p, atm_withdrawals: updateChild(p.atm_withdrawals, i, { date_of_action: v }) }))} type="date" />
                </div>
              </div>
            ))}
            {!fromExcel && <AddBtn onClick={() => setF(p => ({ ...p, atm_withdrawals: [...p.atm_withdrawals, emptyAtmWithdrawal()] }))} label="Add ATM Withdrawal" />}
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
                  <Save className="w-4 h-4" /> {saving ? 'Saving...' : 'Submit Report'}
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
