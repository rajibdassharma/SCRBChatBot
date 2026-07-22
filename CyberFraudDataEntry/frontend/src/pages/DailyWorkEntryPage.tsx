import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { toast } from 'sonner';
import { Save, Trash2 } from 'lucide-react';
import {
  deleteDailyWork, getDailyWorkById, getOwnDailyWork, upsertDailyWork,
} from '../lib/api/daily-work';
import { FIR_NO_PLACEHOLDER, validateFirNo } from '../lib/utils/fir-no';
import { todayISO } from '../lib/utils/format';
import type {
  DailyWorkEntry, DailyWorkFinalReport, DailyWorkWritePayload,
} from '../types';

/** Daily-Work-Done entry — single page, three colour-coded sections
 *  matching the paper form's header colours:
 *
 *    Red    → Notices (35(3)/41A + 91/92/94 broken down by recipient)
 *    Yellow → Lien / Unlien (counts + total amounts)
 *    Green  → Investigation outcomes (arrests, statements, final report)
 *
 *  Uniqueness: one row per (PS, FIR, date). The backend upserts on that
 *  key, so re-saving the same combo overwrites the row in place — no
 *  duplicate rows from an operator hitting Save twice.
 *
 *  Two entry paths:
 *    - `/daily-work/new`  → blank form (FIR + date open, everything else 0)
 *    - `/daily-work/:id`  → loads the existing row by id (used from the
 *                           update / history table).
 */

const POS_INT_RE = /^\d+$/;
const AMOUNT_RE = /^\d+(\.\d{0,2})?$/;

function emptyForm(): DailyWorkWritePayload {
  return {
    report_date: todayISO(),
    fir_no: '',
    notices_35_41a_count: 0,
    notices_91_92_94_banks: 0,
    notices_91_92_94_intermediary: 0,
    notices_91_92_94_account_holder: 0,
    notices_91_92_94_cdr_ipdr: 0,
    lien_requests_count: 0,
    freeze_requests_count: 0,
    total_lien_amount: 0,
    unlien_requests_count: 0,
    defreeze_requests_count: 0,
    total_unlien_amount: 0,
    arrests_count: 0,
    statements_count: 0,
    final_report: null,
  };
}

// ── Field primitives ─────────────────────────────────────────
// Kept inline so the Investigation Log module doesn't drag in
// the whole PortalsDsr NumField (which owns tab-sync state we
// don't need here).

/** Positive integer input. Empty means 0. Invalid input keeps the
 *  raw text visible with a red border + inline error, and does NOT
 *  propagate the bad value — the parent form keeps the last valid
 *  count so the payload stays well-formed. */
function IntField({
  label, value, onChange,
}: { label: string; value: number; onChange: (v: number) => void }) {
  const [raw, setRaw] = useState<string>(value === 0 ? '' : String(value));
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    const asStr = value === 0 ? '' : String(value);
    setRaw((prev) => (Number(prev || '0') === value ? prev : asStr));
    setErr(null);
  }, [value]);
  const handle = (s: string) => {
    setRaw(s);
    if (s === '') { setErr(null); onChange(0); return; }
    if (!POS_INT_RE.test(s)) { setErr('Positive whole numbers only'); return; }
    setErr(null); onChange(Number(s));
  };
  return (
    <div>
      <label className="block text-xs font-semibold mb-1"
        style={{ color: 'var(--ksp-navy)' }}>{label}</label>
      <input
        type="text" inputMode="numeric" value={raw}
        onChange={(e) => handle(e.target.value)}
        placeholder="0"
        className="w-full px-3 py-2 rounded-xl text-sm outline-none"
        style={{
          border: `2px solid ${err ? 'var(--ksp-red)' : 'var(--ksp-navy)'}`,
          background: '#fff',
        }} />
      {err && <p className="text-xs mt-1" style={{ color: 'var(--ksp-red)' }}>{err}</p>}
    </div>
  );
}

/** Rupee amount input — accepts decimals up to 2 places. Empty = 0.
 *  Same "keep-last-valid" strategy as IntField. */
function AmountField({
  label, value, onChange,
}: { label: string; value: number; onChange: (v: number) => void }) {
  const [raw, setRaw] = useState<string>(value === 0 ? '' : String(value));
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    const asStr = value === 0 ? '' : String(value);
    setRaw((prev) => (Number(prev || '0') === value ? prev : asStr));
    setErr(null);
  }, [value]);
  const handle = (s: string) => {
    setRaw(s);
    if (s === '') { setErr(null); onChange(0); return; }
    if (!AMOUNT_RE.test(s)) { setErr('Amount format: 12345 or 12345.67'); return; }
    setErr(null); onChange(Number(s));
  };
  return (
    <div>
      <label className="block text-xs font-semibold mb-1"
        style={{ color: 'var(--ksp-navy)' }}>{label}</label>
      <div className="relative">
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm font-semibold"
          style={{ color: 'rgba(11,44,74,0.6)' }}>₹</span>
        <input
          type="text" inputMode="decimal" value={raw}
          onChange={(e) => handle(e.target.value)}
          placeholder="0.00"
          className="w-full pl-7 pr-3 py-2 rounded-xl text-sm outline-none"
          style={{
            border: `2px solid ${err ? 'var(--ksp-red)' : 'var(--ksp-navy)'}`,
            background: '#fff',
          }} />
      </div>
      {err && <p className="text-xs mt-1" style={{ color: 'var(--ksp-red)' }}>{err}</p>}
    </div>
  );
}

/** Section container. Accent bar left-edge in the section colour
 *  (red / yellow / green) so the operator's eye lands on the group
 *  header before the field labels. */
function Section({
  title, accent, children,
}: { title: string; accent: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl overflow-hidden"
      style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
      <div className="px-5 py-3 text-sm font-bold uppercase tracking-wide"
        style={{ background: accent, color: '#fff' }}>{title}</div>
      <div className="p-5 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {children}
      </div>
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────

export function DailyWorkEntryPage() {
  const { id } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const isEdit = !!id;

  const [f, setF] = useState<DailyWorkWritePayload>(emptyForm());
  const [entryId, setEntryId] = useState<number | null>(null);
  const [loading, setLoading] = useState(isEdit);
  const [saving, setSaving] = useState(false);

  // Update-mode load: fetch the row by id and hydrate.
  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getDailyWorkById(Number(id))
      .then((row) => { setEntryId(row.id); setF(rowToForm(row)); })
      .catch((e) => toast.error(e instanceof Error ? e.message : 'Failed to load entry'))
      .finally(() => setLoading(false));
  }, [id]);

  // New-mode helper: if the operator types an existing FIR + date that
  // already has a row, prefill the counts. Debounced by React's normal
  // render cycle — a quick sequence of keystrokes only fires the final
  // combo. Silent no-op on 404 / null.
  useEffect(() => {
    if (isEdit) return;
    if (!f.fir_no || !f.report_date) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      getOwnDailyWork(f.fir_no, f.report_date)
        .then((row) => {
          if (cancelled || !row) return;
          setEntryId(row.id);
          setF(rowToForm(row));
          toast.info(`Loaded existing entry for FIR ${row.fir_no} on ${row.report_date}`);
        })
        .catch(() => { /* silent — new row is fine */ });
    }, 500);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [f.fir_no, f.report_date, isEdit]);

  const set = <K extends keyof DailyWorkWritePayload>(k: K, v: DailyWorkWritePayload[K]) =>
    setF((p) => ({ ...p, [k]: v }));

  // Format-only error — non-empty invalid inputs surface a red hint;
  // empty is handled by the required-check on Save.
  const firNoError = validateFirNo(f.fir_no);

  const handleSave = async () => {
    if (!f.fir_no.trim()) { toast.error('FIR No. is required.'); return; }
    if (firNoError) { toast.error(firNoError); return; }
    setSaving(true);
    try {
      const row = await upsertDailyWork({ ...f, fir_no: f.fir_no.trim() });
      setEntryId(row.id);
      setF(rowToForm(row));
      toast.success(entryId ? 'Entry updated' : 'Entry saved');
      if (!isEdit) navigate(`/daily-work/${row.id}`, { replace: true });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!entryId) return;
    if (!confirm('Delete this daily-work entry? This cannot be undone.')) return;
    try {
      await deleteDailyWork(entryId);
      toast.success('Entry deleted');
      navigate('/daily-work/update');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Delete failed');
    }
  };

  if (loading) return <div className="text-center py-10 italic">Loading…</div>;

  return (
    <div>
      <h1 className="text-[22px] font-bold mb-1"
        style={{ color: 'var(--ksp-navy)', letterSpacing: '-0.02em' }}>
        Investigations — Daily Work Done
      </h1>
      <p className="text-sm font-medium mb-6" style={{ color: 'var(--ksp-red)' }}>
        Log today's investigation activity on a specific FIR — notices served, lien / unlien
        requests, arrests, statements, and (when closed) the final report letter.
      </p>

      {/* Key fields — FIR + date drive the upsert. */}
      <div className="rounded-2xl p-5 mb-5"
        style={{ background: 'var(--ksp-navy)', color: '#fff' }}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold mb-1"
              style={{ color: 'var(--ksp-yellow)' }}>FIR No.</label>
            <input
              type="text" value={f.fir_no}
              onChange={(e) => set('fir_no', e.target.value)}
              placeholder={FIR_NO_PLACEHOLDER}
              maxLength={50}
              className="w-full px-3 py-2 rounded-xl text-sm outline-none font-semibold"
              style={{
                background: '#fff', color: 'var(--ksp-navy)',
                // Red border when the format's wrong so the operator
                // sees it against the navy strip.
                border: `2px solid ${firNoError ? '#ff6b6b' : 'var(--ksp-yellow)'}`,
              }} />
            {firNoError && (
              <p className="text-xs mt-1 font-semibold" style={{ color: '#ffb3b3' }}>{firNoError}</p>
            )}
          </div>
          <div>
            <label className="block text-xs font-semibold mb-1"
              style={{ color: 'var(--ksp-yellow)' }}>Report Date</label>
            <input
              type="date" value={f.report_date}
              onChange={(e) => set('report_date', e.target.value)}
              className="w-full px-3 py-2 rounded-xl text-sm outline-none font-semibold"
              style={{ background: '#fff', color: 'var(--ksp-navy)', border: '2px solid var(--ksp-yellow)' }} />
          </div>
        </div>
      </div>

      <div className="space-y-5">
        {/* ── RED · Notices ─────────────────────────────────── */}
        <Section title="Notices" accent="#b10000">
          <IntField label="35(3) / 41A Notices"
            value={f.notices_35_41a_count}
            onChange={(v) => set('notices_35_41a_count', v)} />
          <IntField label="91 / 92 / 94 Notices — Banks"
            value={f.notices_91_92_94_banks}
            onChange={(v) => set('notices_91_92_94_banks', v)} />
          <IntField label="91 / 92 / 94 Notices — Intermediary"
            value={f.notices_91_92_94_intermediary}
            onChange={(v) => set('notices_91_92_94_intermediary', v)} />
          <IntField label="91 / 92 / 94 Notices — Account Holder"
            value={f.notices_91_92_94_account_holder}
            onChange={(v) => set('notices_91_92_94_account_holder', v)} />
          <IntField label="91 / 92 / 94 Notices — CDR / IPDR"
            value={f.notices_91_92_94_cdr_ipdr}
            onChange={(v) => set('notices_91_92_94_cdr_ipdr', v)} />
        </Section>

        {/* ── YELLOW · Lien / Unlien ────────────────────────── */}
        <Section title="Lien / Unlien Requests" accent="#c49500">
          <IntField label="Lien Requests"
            value={f.lien_requests_count}
            onChange={(v) => set('lien_requests_count', v)} />
          <IntField label="Freeze Requests"
            value={f.freeze_requests_count}
            onChange={(v) => set('freeze_requests_count', v)} />
          <AmountField label="Total Amount of Lien"
            value={f.total_lien_amount}
            onChange={(v) => set('total_lien_amount', v)} />
          <IntField label="Unlien Requests"
            value={f.unlien_requests_count}
            onChange={(v) => set('unlien_requests_count', v)} />
          <IntField label="Defreeze Requests"
            value={f.defreeze_requests_count}
            onChange={(v) => set('defreeze_requests_count', v)} />
          <AmountField label="Total Amount of Unlien"
            value={f.total_unlien_amount}
            onChange={(v) => set('total_unlien_amount', v)} />
        </Section>

        {/* ── GREEN · Investigation Outcomes ────────────────── */}
        <Section title="Investigation Outcomes" accent="#0a6b28">
          <IntField label="Arrests"
            value={f.arrests_count}
            onChange={(v) => set('arrests_count', v)} />
          <IntField label="Accused / Witness Statements"
            value={f.statements_count}
            onChange={(v) => set('statements_count', v)} />
          <div>
            <label className="block text-xs font-semibold mb-1"
              style={{ color: 'var(--ksp-navy)' }}>Final Report</label>
            <select
              value={f.final_report ?? ''}
              onChange={(e) => set('final_report',
                e.target.value === '' ? null : e.target.value as DailyWorkFinalReport)}
              className="w-full px-3 py-2 rounded-xl text-sm font-semibold outline-none"
              style={{ border: '2px solid var(--ksp-navy)', background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}>
              <option value="">— Not yet filed —</option>
              <option value="A">A — Chargesheeted</option>
              <option value="B">B — False</option>
              <option value="C">C — Undetected</option>
            </select>
          </div>
        </Section>
      </div>

      {/* Save / Delete bar */}
      <div className="flex items-center justify-end gap-3 mt-6">
        {entryId && (
          <button type="button" onClick={handleDelete}
            className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-xl"
            style={{ background: '#fff', color: 'var(--ksp-red)', border: '2px solid var(--ksp-red)' }}>
            <Trash2 className="w-4 h-4" /> Delete
          </button>
        )}
        <button type="button" onClick={handleSave}
          disabled={saving || !!firNoError}
          title={firNoError ?? undefined}
          className="flex items-center gap-1.5 px-4 py-2 text-sm font-bold rounded-xl transition disabled:opacity-50"
          style={{ background: 'var(--ksp-yellow)', color: '#000', border: '2px solid rgba(0,0,0,0.25)' }}>
          <Save className="w-4 h-4" />
          {saving ? 'Saving…' : entryId ? 'Update Entry' : 'Save Entry'}
        </button>
      </div>
    </div>
  );
}

// Response rows use Decimal-string amounts; the form uses numbers.
// This helper does the one-shot conversion on load.
function rowToForm(row: DailyWorkEntry): DailyWorkWritePayload {
  return {
    report_date: row.report_date,
    fir_no: row.fir_no,
    notices_35_41a_count: row.notices_35_41a_count,
    notices_91_92_94_banks: row.notices_91_92_94_banks,
    notices_91_92_94_intermediary: row.notices_91_92_94_intermediary,
    notices_91_92_94_account_holder: row.notices_91_92_94_account_holder,
    notices_91_92_94_cdr_ipdr: row.notices_91_92_94_cdr_ipdr,
    lien_requests_count: row.lien_requests_count,
    freeze_requests_count: row.freeze_requests_count,
    total_lien_amount: Number(row.total_lien_amount),
    unlien_requests_count: row.unlien_requests_count,
    defreeze_requests_count: row.defreeze_requests_count,
    total_unlien_amount: Number(row.total_unlien_amount),
    arrests_count: row.arrests_count,
    statements_count: row.statements_count,
    final_report: row.final_report,
  };
}
