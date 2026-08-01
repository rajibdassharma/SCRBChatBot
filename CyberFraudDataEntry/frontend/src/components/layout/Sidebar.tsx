import { NavLink, useLocation } from 'react-router';
import { useAuthStore } from '../../lib/stores/auth-store';
import { useState, useEffect } from 'react';
import { CalendarOff, Home, LogOut } from 'lucide-react';
import { toast } from 'sonner';
import { declareNil, getNilToday } from '../../lib/api/nil';
import { getFeatures } from '../../lib/api/features';
import { getCurrentModule, LINK_GROUPS } from '../../lib/utils/modules';
import type { NilDeclaration } from '../../types';
import kspLogo from '../../assets/ksp_logo.png';

/** Contextual sidebar. Shows only the links belonging to the module
 *  the current URL falls in. Home link at the top takes the operator
 *  back to the tile-grid landing (`/`). On the landing itself the
 *  navigation area collapses to just user info + Sign Out — the
 *  tiles ARE the navigation there. */

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-semibold transition ${
    isActive
      ? 'bg-[#0b2c4a] text-[#ffd400]'
      : 'text-[#0b2c4a] hover:bg-[rgba(11,44,74,0.1)]'
  }`;

/** The Sign Out button's red. Section headings borrow it, so pulling it
 *  into one constant keeps "same colour as Sign Out" true if either is
 *  ever restyled, instead of leaving two hex literals to drift apart. */
const SIGNOUT_RED = '#c62828';

/** Same row, indented under a section heading. Extra left padding only
 *  — the pill keeps its full width so the active highlight still reads
 *  as one block rather than a ragged edge. */
const indentedLinkClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-3 pl-7 pr-4 py-2 rounded-xl text-sm font-semibold transition ${
    isActive
      ? 'bg-[#0b2c4a] text-[#ffd400]'
      : 'text-[#0b2c4a] hover:bg-[rgba(11,44,74,0.1)]'
  }`;

export function Sidebar() {
  const { user, logout } = useAuthStore();
  const location = useLocation();
  const currentModule = getCurrentModule(location.pathname);

  const isAdmin = user?.role === 'admin' || user?.role === 'super_admin';
  const isSuperAdmin = user?.role === 'super_admin';

  // Chat feature flag — some links in modules.ts (e.g. Admin > Ask the
  // Data) hide until the server reports chat_enabled=true.
  const [chatEnabled, setChatEnabled] = useState(false);
  useEffect(() => {
    let cancelled = false;
    getFeatures()
      .then((f) => { if (!cancelled) setChatEnabled(f.chat_enabled); })
      .catch(() => { /* fail closed — keep chat-only links hidden */ });
    return () => { cancelled = true; };
  }, []);

  return (
    <aside className="w-[280px] flex flex-col min-h-screen p-4 gap-3"
      style={{ background: 'var(--ksp-yellow-soft)', borderRight: '2px solid var(--ksp-yellow-border)' }}>
      {/* KSP Logo */}
      <div className="flex justify-center items-center">
        <div className="p-2 rounded-xl" style={{ background: 'rgba(255,255,255,0.45)', boxShadow: 'inset 0 0 0 1px rgba(0,0,0,0.18)' }}>
          <img src={kspLogo} alt="KSP Logo" className="w-[180px] h-[140px] object-contain" />
        </div>
      </div>

      {/* App title */}
      <div className="text-center">
        <h2 className="text-lg font-bold" style={{ color: 'var(--ksp-navy)' }}>Cyber Fraud Cases</h2>
        <p className="text-xs font-medium" style={{ color: 'var(--ksp-red)' }}>Karnataka State Police</p>
      </div>

      {/* Divider */}
      <div className="h-[2px] mx-4" style={{ background: 'linear-gradient(to right, rgba(0,0,0,0), #b10000, rgba(0,0,0,0))' }} />

      {/* Home link — always visible except on the home page itself. */}
      {currentModule && (
        <NavLink to="/" className={linkClass} end>
          <Home className="w-4 h-4" /> Home
        </NavLink>
      )}

      {/* Contextual navigation — module-specific links only. */}
      {currentModule && (
        <nav className="space-y-1">
          <p className="px-4 pt-2 pb-2 text-sm font-extrabold uppercase tracking-wide flex items-center gap-2"
             style={{ color: currentModule.accent }}>
            <currentModule.icon className="w-4 h-4" />
            {currentModule.label}
          </p>
          {(() => {
            // Filter by role FIRST, then group. Doing it the other way
            // renders a "Dashboards" heading with nothing under it for
            // every non-admin, since all dashboard links are gated.
            const visible = currentModule.links.filter((l) => {
              if (l.requiresAdmin && !isAdmin) return false;
              if (l.requiresSuperAdmin && !isSuperAdmin) return false;
              if (l.requiresChat && !chatEnabled) return false;
              return true;
            });

            const row = (l: typeof visible[number], indent: boolean) => {
              const Icon = l.icon;
              return (
                <NavLink key={l.to} to={l.to} className={indent ? indentedLinkClass : linkClass}>
                  <Icon className="w-4 h-4" /> {l.label}
                </NavLink>
              );
            };

            // Modules that don't use groups keep the flat list they had.
            const ungrouped = visible.filter((l) => !l.group);
            if (ungrouped.length === visible.length) {
              return visible.map((l) => row(l, false));
            }

            return (
              <>
                {ungrouped.map((l) => row(l, false))}
                {LINK_GROUPS.map(({ key, label }) => {
                  const inGroup = visible.filter((l) => l.group === key);
                  if (!inGroup.length) return null;
                  return (
                    <div key={key} className="pt-2">
                      <p className="px-4 pb-1 text-sm font-bold uppercase tracking-wider"
                         style={{ color: SIGNOUT_RED }}>
                        {label}
                      </p>
                      <div className="space-y-1">{inGroup.map((l) => row(l, true))}</div>
                    </div>
                  );
                })}
              </>
            );
          })()}
          {/* NIL button — only in the Cases & Petitions module. */}
          {currentModule.hasNilButton && <NilDayButton />}
        </nav>
      )}

      {/* When on the home page itself, the tiles ARE the navigation. */}
      {!currentModule && (
        <div className="px-4 py-3 text-xs opacity-70 italic text-center">
          Choose a module from the tiles →
        </div>
      )}

      {/* Divider — sits right below the last nav link so there's no
           big empty gap in the middle when the contextual sidebar is
           short (which it usually is). */}
      <div className="h-[2px] mx-4 mt-2" style={{ background: 'linear-gradient(to right, rgba(0,0,0,0), #b10000, rgba(0,0,0,0))' }} />

      {/* User info */}
      <div className="px-2">
        <p className="text-sm font-bold" style={{ color: 'var(--ksp-navy)' }}>{user?.unit_name}</p>
        <p className="text-xs font-semibold" style={{ color: 'var(--ksp-red)' }}>
          {user?.role === 'super_admin' ? 'Super Admin' : user?.role === 'admin' ? 'Admin' : 'User'}
        </p>
      </div>

      <button
        onClick={async () => { await logout(); window.location.href = '/login'; }}
        className="flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-semibold rounded-xl transition"
        style={{ background: SIGNOUT_RED, color: '#fff', border: '2px solid rgba(0,0,0,0.25)' }}
      >
        <LogOut className="w-4 h-4" /> Sign Out
      </button>
    </aside>
  );
}


/** Sidebar nav row that lets the operator declare today as NIL for
 *  their PS. Renders the button + the modal that opens on click. Only
 *  shown inside the Cases & Petitions module (see modules.ts). */
function NilDayButton() {
  const [open, setOpen] = useState(false);
  const [existing, setExisting] = useState<NilDeclaration | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getNilToday()
      .then((row) => { if (!cancelled) setExisting(row); })
      .catch(() => { /* silent — not worth toasting on every page mount */ })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const alreadyDeclared = !!existing;
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        disabled={loading}
        className="flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-semibold transition w-full text-left disabled:opacity-50"
        style={{
          background: alreadyDeclared ? 'rgba(10,92,42,0.12)' : 'rgba(11,44,74,0.06)',
          color: alreadyDeclared ? '#0a5c2a' : 'var(--ksp-navy)',
          border: alreadyDeclared ? '1px solid rgba(10,92,42,0.30)' : '1px solid rgba(11,44,74,0.18)',
        }}
        title={alreadyDeclared ? `Declared NIL today by ${existing?.declared_by_name ?? 'someone in this PS'}` : 'Mark today as no-activity for this PS'}
      >
        <CalendarOff className="w-4 h-4" />
        {alreadyDeclared ? '✓ NIL declared today' : 'Mark NIL Today'}
      </button>

      {open && (
        <NilModal
          existing={existing}
          onClose={() => setOpen(false)}
          onDeclared={(row) => { setExisting(row); setOpen(false); }}
        />
      )}
    </>
  );
}

/** Modal body — gathers an optional reason and calls the API. */
function NilModal({ existing, onClose, onDeclared }: {
  existing: NilDeclaration | null;
  onClose: () => void;
  onDeclared: (row: NilDeclaration) => void;
}) {
  const [reason, setReason] = useState(existing?.reason ?? '');
  const [busy, setBusy] = useState(false);

  const handleConfirm = async () => {
    setBusy(true);
    try {
      const row = await declareNil({ reason: reason.trim() || undefined });
      toast.success('NIL declared for today.');
      onDeclared(row);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not declare NIL');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.5)' }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="rounded-2xl p-5 w-full max-w-md space-y-4"
        style={{ background: '#fff', boxShadow: '0 20px 40px rgba(0,0,0,0.30)' }}
      >
        <h2 className="text-lg font-bold" style={{ color: 'var(--ksp-navy)' }}>
          {existing ? 'NIL already declared today' : 'Declare today as NIL?'}
        </h2>
        <p className="text-sm opacity-70">
          {existing
            ? `Declared by ${existing.declared_by_name ?? 'someone in this PS'}. You can update the reason if you like — re-declaring is harmless.`
            : 'Use this when your PS has no cyber-fraud cases to record today. It tells the dashboard that the silence is intentional (not a missed entry).'}
        </p>
        <div>
          <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>
            Reason (optional)
          </label>
          <input
            type="text"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. public holiday, network down"
            maxLength={255}
            className="w-full px-3 py-2 rounded-xl text-sm outline-none"
            style={{ border: '2px solid var(--ksp-navy)', background: '#fff' }}
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="px-4 py-2 rounded-xl text-sm font-semibold"
            style={{ background: 'rgba(11,44,74,0.06)', color: 'var(--ksp-navy)' }}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={busy}
            className="px-4 py-2 rounded-xl text-sm font-bold disabled:opacity-50"
            style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}
          >
            {busy ? 'Saving…' : (existing ? 'Update Reason' : 'Confirm NIL for Today')}
          </button>
        </div>
      </div>
    </div>
  );
}
