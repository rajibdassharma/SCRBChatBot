import { useState, useEffect } from 'react';
import { useAuthStore } from '../../lib/stores/auth-store';
import { upsertMule, getOwnMule } from '../../lib/api/mule';
import { todayISO } from '../../lib/utils/format';
import { Save, CheckCircle, ChevronRight, ChevronLeft } from 'lucide-react';

interface FieldDef {
  key: string;
  label: string;
  rows: number;
}

const TAB1_FIELDS: FieldDef[] = [
  { key: 'accounts_most_liens', label: 'Which Accounts have most Liens defined? (Decreasing order)', rows: 4 },
  { key: 'recruiters_for_lien_accounts', label: 'Regarding the above Accounts, who are the Recruiters?', rows: 4 },
  { key: 'accounts_max_money_routed', label: 'Through which accounts the maximum money has been routed? (Decreasing order)', rows: 4 },
  { key: 'accounts_max_transactions', label: 'Which accounts have the maximum number of Transactions? (Decreasing order)', rows: 4 },
];

const TAB2_FIELDS: FieldDef[] = [
  { key: 'recency_atm_transactions', label: 'Recency of mule transaction — ATM transactions, Mule account wise? (Amounts withdrawn, Decreasing order)', rows: 4 },
  { key: 'cash_withdrawals_mule_wise', label: 'How many cash withdrawals, Mule Accounts wise? (Amounts withdrawn, Decreasing order)', rows: 4 },
  { key: 'atm_geo_identification', label: 'ATM ID geographical/bank wise Identification & geo location on map for hot spot analysis', rows: 4 },
  { key: 'atm_table_by_transactions', label: 'Table of ATMs with bank & geo locations (ATM-ID / Bank / Location / No. of Withdrawals, Decreasing)', rows: 6 },
];

const TAB3_FIELDS: FieldDef[] = [
  { key: 'cheque_withdrawal_branches', label: 'Cheque withdrawal Branches (Branch / Bank / Location / No. of Withdrawals)', rows: 6 },
  { key: 'money_left_system_stats', label: 'Detailed Statistics on money left the system — ATM / Cheque / Crypto / Foreign Banks (Indian & Foreign ATMs)', rows: 6 },
  { key: 'crypto_mule_accounts', label: 'How many mule accounts have Cryptocurrency transactions? (Make a repository of wallets)', rows: 4 },
];

const ALL_FIELDS = [...TAB1_FIELDS, ...TAB2_FIELDS, ...TAB3_FIELDS];
const FIELD_TABS = [TAB1_FIELDS, TAB2_FIELDS, TAB3_FIELDS];

const TABS = [
  { label: 'Accounts & Liens' },
  { label: 'ATM & Withdrawals' },
  { label: 'Cheque & Crypto' },
];

// Column letter for display (C through M)
const COL_LETTERS: Record<string, string> = {};
ALL_FIELDS.forEach((f, i) => { COL_LETTERS[f.key] = String.fromCharCode(67 + i); });

export function MuleForm() {
  const { user } = useAuthStore();
  const [date, setDate] = useState(todayISO());
  const [tab, setTab] = useState(0);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const [loaded, setLoaded] = useState(false);

  const empty: Record<string, string> = {};
  ALL_FIELDS.forEach((f) => { empty[f.key] = ''; });
  const [form, setForm] = useState(empty);

  useEffect(() => {
    setLoaded(false);
    setSaved(false);
    getOwnMule(date).then((entry) => {
      if (entry) {
        const loaded: Record<string, string> = {};
        ALL_FIELDS.forEach((f) => { loaded[f.key] = (entry as unknown as Record<string, unknown>)[f.key] as string ?? ''; });
        setForm(loaded);
      } else {
        const clean: Record<string, string> = {};
        ALL_FIELDS.forEach((f) => { clean[f.key] = ''; });
        setForm(clean);
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
      await upsertMule({ report_date: date, ...form });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const currentFields = FIELD_TABS[tab];

  return (
    <form onSubmit={handleSubmit} className="space-y-5 max-w-4xl">
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
          <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>Unit</label>
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
            key={i}
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

      {/* Current tab's fields */}
      <div className="space-y-4">
        {currentFields.map((field) => (
          <div key={field.key} className="rounded-2xl p-5" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
            <label className="block text-sm font-semibold mb-2" style={{ color: 'var(--ksp-navy)' }}>
              <span className="font-bold mr-1" style={{ color: 'var(--ksp-red)' }}>{COL_LETTERS[field.key]}.</span>
              {field.label}
            </label>
            <textarea
              rows={field.rows}
              value={form[field.key]}
              onChange={(e) => setForm((p) => ({ ...p, [field.key]: e.target.value }))}
              className="w-full px-3 py-2 rounded-xl text-sm outline-none resize-y"
              style={{ border: '2px solid var(--ksp-navy)', lineHeight: '1.5' }}
              placeholder="Enter details..."
            />
          </div>
        ))}
      </div>

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
              {saving ? 'Saving...' : 'Submit Mule Accounts'}
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
