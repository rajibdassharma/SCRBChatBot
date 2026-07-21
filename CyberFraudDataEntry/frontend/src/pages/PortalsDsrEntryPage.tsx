import { useEffect, useMemo, useState } from 'react';
// Positive whole numbers only: one-or-more decimal digits, nothing else.
// Empty string is accepted separately (means "0" in the payload).
const POS_INT_RE = /^\d+$/;
import { useNavigate, useParams } from 'react-router';
import { toast } from 'sonner';
import { ChevronLeft, ChevronRight, Save, Send, X } from 'lucide-react';
import {
  createPortalsDsr, deletePortalsDsr, getPortalsDsr, updatePortalsDsr,
} from '../lib/api/portals-dsr';
import { useAuthStore } from '../lib/stores/auth-store';
import { emptyMetrics, PORTAL_TABS } from '../lib/utils/portals-tabs';
import { todayISO } from '../lib/utils/format';
import type {
  PortalsDsrEntry, PortalsDsrMetrics, PortalsDsrWritePayload,
} from '../types';

/** Portals DSR entry — 8 tabs, one per portal. Every tab has Save
 *  Draft; only the last tab (NCMEC) shows the Submit button. Matches
 *  the "one tab per portal" layout of the paper form. */

function emptyForm(): PortalsDsrWritePayload {
  return {
    report_date: todayISO(),
    status: 'draft',
    ...emptyMetrics(),
  };
}

/** Numeric input — positive whole numbers only.
 *
 *  Validation fires on every keystroke (not on submit):
 *    - Empty string is treated as 0 (no error).
 *    - Anything not matching /^\d+$/ shows an inline red error and
 *      the invalid text stays in the box so the operator can see
 *      what they typed. The parent form does NOT receive the invalid
 *      value — it keeps the last valid one, so the payload stays
 *      well-formed even if the user hits Save while a field is red.
 *    - Backend Pydantic (int, ge=0) is the second line of defence.
 *
 *  We use type="text" + inputMode="numeric" instead of type="number"
 *  so pasted junk ("5.5", "abc", "-5") shows the actual text plus
 *  the error message rather than being silently swallowed by the
 *  browser's number widget. */
function NumField({
  label, value, onChange,
}: { label: string; value: number; onChange: (v: number) => void }) {
  const [raw, setRaw] = useState<string>(value === 0 ? '' : String(value));
  const [error, setError] = useState<string | null>(null);

  // Re-sync from parent when the value changes upstream (edit-load,
  // form reset after save). Skips when the parent value already
  // matches the string we last committed, so typing doesn't ping-pong.
  useEffect(() => {
    const asStr = value === 0 ? '' : String(value);
    setRaw((prev) => (Number(prev || '0') === value ? prev : asStr));
    setError(null);
  }, [value]);

  const handle = (s: string) => {
    setRaw(s);
    if (s === '') {
      setError(null);
      onChange(0);
      return;
    }
    if (!POS_INT_RE.test(s)) {
      setError('Only positive whole numbers allowed');
      // Don't propagate — parent keeps its last valid value.
      return;
    }
    setError(null);
    onChange(Number(s));
  };

  const border = error ? 'var(--ksp-red)' : 'var(--ksp-navy)';
  return (
    <div>
      <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>
        {label}
      </label>
      <input
        type="text"
        inputMode="numeric"
        value={raw}
        placeholder="0"
        onChange={(e) => handle(e.target.value)}
        aria-invalid={!!error}
        className="w-full px-3 py-2 rounded-xl text-sm outline-none text-right font-mono"
        style={{ border: `2px solid ${border}`, background: '#fff' }}
      />
      {error && (
        <p className="text-xs mt-1" style={{ color: 'var(--ksp-red)' }}>
          {error}
        </p>
      )}
    </div>
  );
}

function Section({ title, accent, children }: {
  title: string; accent: string; children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl p-5" style={{
      background: '#fff',
      border: '1px solid rgba(0,0,0,0.06)',
      boxShadow: '0 6px 16px rgba(0,0,0,0.08)',
      borderTop: `4px solid ${accent}`,
    }}>
      <h3 className="text-sm font-bold mb-4 uppercase tracking-wide" style={{ color: accent }}>
        {title}
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {children}
      </div>
    </div>
  );
}

export function PortalsDsrEntryPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const isEdit = !!id;

  const [tab, setTab] = useState(0);
  const [f, setF] = useState<PortalsDsrWritePayload>(emptyForm());
  const [existing, setExisting] = useState<PortalsDsrEntry | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getPortalsDsr(id)
      .then((data) => {
        setExisting(data);
        setF({
          report_date: data.report_date,
          status: data.status,
          // Copy every metric field verbatim.
          ...(Object.fromEntries(
            Object.entries(data).filter(([k]) =>
              k !== 'id' && k !== 'unit_id' && k !== 'ps_id' &&
              k !== 'report_date' && k !== 'status' &&
              k !== 'submitted_by' && k !== 'created_at' && k !== 'updated_at'
            )
          ) as PortalsDsrMetrics),
        });
      })
      .catch((err) => toast.error(`Failed to load entry: ${err.message}`))
      .finally(() => setLoading(false));
  }, [id]);

  const setMetric = (key: keyof PortalsDsrMetrics, v: number) =>
    setF((p) => ({ ...p, [key]: v }));

  const tabTotals = useMemo(() => {
    // Sum-per-tab so the tab button can badge non-zero tabs at a glance.
    return PORTAL_TABS.map((t) =>
      t.metrics.reduce((s, m) => s + (f[m.key] || 0), 0)
    );
  }, [f]);

  const grandTotal = useMemo(
    () => tabTotals.reduce((s, n) => s + n, 0),
    [tabTotals],
  );

  const persist = async (status: 'draft' | 'submitted') => {
    setBusy(true);
    try {
      const payload: PortalsDsrWritePayload = { ...f, status };
      if (isEdit) {
        await updatePortalsDsr(id!, payload);
        toast.success(status === 'submitted' ? 'Entry submitted' : 'Draft saved');
      } else {
        const created = await createPortalsDsr(payload);
        toast.success(status === 'submitted' ? 'Entry submitted' : 'Draft saved');
        // After creating a NEW draft, hop into edit mode so subsequent
        // Save-Draft clicks update the same row (not create a new one).
        if (status === 'draft') {
          navigate(`/portals-dsr/${created.id}`, { replace: true });
        } else {
          navigate('/portals-dsr/update');
        }
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  };

  const handleCancel = async () => {
    if (!isEdit) {
      navigate('/portals-dsr/update');
      return;
    }
    if (!window.confirm('Delete this entry? This cannot be undone.')) return;
    try {
      await deletePortalsDsr(id!);
      toast.success('Entry deleted');
      navigate('/portals-dsr/update');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Delete failed');
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center py-20"><span className="text-sm text-slate-400">Loading...</span></div>;
  }

  const activeTab = PORTAL_TABS[tab];
  const isLastTab = tab === PORTAL_TABS.length - 1;

  return (
    <div>
      {/* Header — navy strip matching Case + Petition + All Accounts. */}
      <div className="rounded-2xl p-4 mb-4" style={{ background: 'var(--ksp-navy)', color: '#fff' }}>
        <h1 className="text-lg font-bold" style={{ color: 'var(--ksp-yellow)' }}>Portals DSR</h1>
        <div className="flex gap-6 mt-2 text-sm flex-wrap">
          <span><strong>District:</strong> {user?.unit_name}</span>
          <span><strong>CCPS:</strong> {user?.ps_name || 'N/A'}</span>
          <span><strong>User:</strong> {user?.username}</span>
          {existing && <span><strong>Status:</strong> {existing.status}</span>}
        </div>
      </div>

      <div className="flex items-start justify-between mb-4 gap-4 flex-wrap">
        <div>
          <h1 className="text-[22px] font-bold mb-1" style={{ color: 'var(--ksp-navy)' }}>
            {isEdit ? 'Edit Portals DSR Entry' : 'New Portals DSR Entry'}
          </h1>
          <p className="text-sm font-medium" style={{ color: 'var(--ksp-red)' }}>
            Enter counters tab-by-tab. Save Draft any time; hit Submit on the last tab when done. Grand total: <span className="font-mono">{grandTotal}</span>.
          </p>
        </div>
        <label className="text-sm flex items-center gap-2">
          <span className="font-semibold" style={{ color: 'var(--ksp-navy)' }}>Report date:</span>
          <input type="date" value={f.report_date}
            onChange={(e) => setF((p) => ({ ...p, report_date: e.target.value }))}
            className="px-3 py-1.5 rounded-lg text-sm bg-white"
            style={{ border: '2px solid var(--ksp-navy)' }} />
        </label>
      </div>

      {/* Tab bar */}
      <div className="flex flex-wrap gap-2 mb-5">
        {PORTAL_TABS.map((t, i) => {
          const active = i === tab;
          const filled = tabTotals[i] > 0;
          return (
            <button key={t.key} type="button" onClick={() => setTab(i)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-xl text-sm font-bold transition"
              style={{
                background: active ? t.accent : '#fff',
                color: active ? '#fff' : t.accent,
                border: `2px solid ${t.accent}`,
                boxShadow: active ? '0 4px 10px rgba(0,0,0,0.15)' : 'none',
              }}>
              <span className="inline-flex items-center justify-center w-5 h-5 rounded-full text-[10px]"
                style={{
                  background: active ? '#fff' : t.accent,
                  color: active ? t.accent : '#fff',
                }}>
                {i + 1}
              </span>
              {t.label}
              {filled && (
                <span className="text-[10px] font-mono opacity-80">({tabTotals[i]})</span>
              )}
            </button>
          );
        })}
      </div>

      {/* Active tab content */}
      <Section title={activeTab.label} accent={activeTab.accent}>
        {activeTab.metrics.map((m) => (
          <NumField key={m.key}
            label={m.label}
            value={f[m.key]}
            onChange={(v) => setMetric(m.key, v)} />
        ))}
      </Section>

      {/* Nav row: Previous | Save Draft | (Next OR Submit) | Cancel */}
      <div className="flex items-center justify-between mt-5 flex-wrap gap-2">
        <button type="button" onClick={() => setTab((t) => Math.max(0, t - 1))} disabled={tab === 0 || busy}
          className="flex items-center gap-1 px-4 py-2 text-sm font-semibold rounded-xl transition disabled:opacity-30"
          style={{ background: 'var(--ksp-yellow)', color: '#000', border: '2px solid rgba(0,0,0,0.25)' }}>
          <ChevronLeft className="w-4 h-4" /> Previous
        </button>

        <div className="flex items-center gap-2 flex-wrap">
          <button type="button" onClick={() => persist('draft')} disabled={busy}
            className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-xl transition"
            style={{ background: '#fff', color: 'var(--ksp-navy)', border: '2px solid var(--ksp-navy)' }}>
            <Save className="w-4 h-4" /> Save Draft
          </button>

          {isLastTab ? (
            <button type="button" onClick={() => persist('submitted')} disabled={busy}
              className="flex items-center gap-1.5 px-5 py-2 text-sm font-bold rounded-xl transition"
              style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)', border: '2px solid rgba(0,0,0,0.25)' }}>
              <Send className="w-4 h-4" /> Submit Entry
            </button>
          ) : (
            <button type="button" onClick={() => setTab((t) => Math.min(PORTAL_TABS.length - 1, t + 1))} disabled={busy}
              className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-xl transition"
              style={{ background: 'var(--ksp-yellow)', color: '#000', border: '2px solid rgba(0,0,0,0.25)' }}>
              Next <ChevronRight className="w-4 h-4" />
            </button>
          )}

          <button type="button" onClick={handleCancel} disabled={busy}
            className="flex items-center gap-1 px-3 py-2 text-sm font-semibold rounded-xl"
            style={{ background: 'rgba(177,0,0,0.08)', color: 'var(--ksp-red)', border: '1px solid rgba(177,0,0,0.2)' }}>
            <X className="w-4 h-4" /> {isEdit ? 'Delete' : 'Cancel'}
          </button>
        </div>
      </div>
    </div>
  );
}
