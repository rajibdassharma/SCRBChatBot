import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { UserPlus, Pencil, KeyRound, ShieldOff, ShieldCheck, X, Copy, Users } from 'lucide-react';
import {
  listUsers,
  createUser,
  updateUser,
  deactivateUser,
  activateUser,
  resetPassword,
  getUserCount,
} from '../lib/api/users';
import { PasswordInput } from '../components/ui/PasswordInput';
import { useAuthStore } from '../lib/stores/auth-store';
import type { ManagedUser } from '../types';

/**
 * User Management page — visible only to per-PS admins (gated in App.tsx
 * route + Sidebar link). Mirrors the operations available via the
 * `/api/v1/users` routes: list, create (auto-suffix username), edit,
 * deactivate / re-activate, reset password.
 *
 * The freshly generated temp passwords from create + reset-password are
 * shown ONCE in a modal with a copy button and a Show/Hide toggle —
 * the server will not return them again.
 */
export function UserManagementPage() {
  const { user: me } = useAuthStore();
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [count, setCount] = useState<{ total: number; active: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Modal state — only one is open at a time
  type CredsModal = { username: string; password: string; mode: 'created' | 'reset' };
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<ManagedUser | null>(null);
  const [credsModal, setCredsModal] = useState<CredsModal | null>(null);

  async function refresh() {
    setLoading(true);
    setError('');
    try {
      const [list, c] = await Promise.all([listUsers(), getUserCount()]);
      setUsers(list);
      setCount(c);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load users');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh(); }, []);

  async function handleDeactivate(u: ManagedUser) {
    if (!window.confirm(`Deactivate ${u.username}? They will be unable to log in until re-activated.`)) return;
    try {
      await deactivateUser(u.id);
      toast.success(`${u.username} deactivated`);
      refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to deactivate');
    }
  }

  async function handleActivate(u: ManagedUser) {
    try {
      await activateUser(u.id);
      toast.success(`${u.username} re-activated`);
      refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to activate');
    }
  }

  async function handleReset(u: ManagedUser) {
    if (!window.confirm(`Generate a new temporary password for ${u.username}? They will be forced to change it on next login.`)) return;
    try {
      const res = await resetPassword(u.id);
      setCredsModal({ username: res.username, password: res.generated_password, mode: 'reset' });
      refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to reset password');
    }
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2" style={{ color: 'var(--ksp-navy)' }}>
            <Users className="w-6 h-6" />
            User Management
          </h1>
          <p className="text-sm mt-1" style={{ color: 'var(--ksp-red)' }}>
            {me?.ps_name ?? me?.unit_name ?? 'Your Police Station'}
          </p>
        </div>
        <button
          onClick={() => setCreateOpen(true)}
          className="flex items-center gap-2 px-4 py-2.5 font-bold rounded-xl text-sm"
          style={{ background: 'var(--ksp-yellow)', color: '#000', border: '2px solid rgba(0,0,0,0.25)' }}
        >
          <UserPlus className="w-4 h-4" /> Create New User
        </button>
      </div>

      {/* Stats card */}
      {count && (
        <div className="grid grid-cols-2 gap-4 mb-6">
          <StatCard label="Total Unit Users" value={count.total} />
          <StatCard label="Active Unit Users" value={count.active} />
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div className="mb-4 px-4 py-3 rounded-xl text-sm font-semibold"
             style={{ background: 'rgba(177,0,0,0.08)', color: 'var(--ksp-red)', border: '1px solid rgba(177,0,0,0.2)' }}>
          {error}
        </div>
      )}

      {/* Users table */}
      <div className="rounded-2xl overflow-hidden bg-white shadow" style={{ border: '2px solid var(--ksp-navy)' }}>
        <table className="w-full text-sm">
          <thead style={{ background: 'var(--ksp-navy)', color: '#fff' }}>
            <tr>
              <th className="px-4 py-3 text-left">Username</th>
              <th className="px-4 py-3 text-left">Full Name</th>
              <th className="px-4 py-3 text-left">Email</th>
              <th className="px-4 py-3 text-left">Mobile</th>
              <th className="px-4 py-3 text-left">Role</th>
              <th className="px-4 py-3 text-left">Status</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={7} className="p-8 text-center text-gray-500">Loading…</td></tr>
            )}
            {!loading && users.length === 0 && (
              <tr><td colSpan={7} className="p-8 text-center text-gray-500">No users found.</td></tr>
            )}
            {!loading && users.map(u => {
              // Compare on username — the auth store hardcodes id=0 in the
              // user object after login, so id-based comparison would always
              // be false. Username is the stable, server-issued identifier.
              const isSelf = u.username === me?.username;
              const isUnitUser = u.role === 'unit_user';
              return (
                <tr key={u.id} className="border-t" style={{ borderColor: 'rgba(11,44,74,0.1)' }}>
                  <td className="px-4 py-3 font-mono text-xs">{u.username}</td>
                  <td className="px-4 py-3">{u.full_name ?? <em className="text-gray-400">—</em>}</td>
                  <td className="px-4 py-3">{u.email ?? <em className="text-gray-400">—</em>}</td>
                  <td className="px-4 py-3">{u.mobile ?? <em className="text-gray-400">—</em>}</td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-0.5 rounded text-xs font-semibold"
                          style={{ background: u.role === 'admin' ? 'var(--ksp-yellow)' : '#e5e7eb', color: '#0b2c4a' }}>
                      {u.role}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-xs font-bold" style={{ color: u.is_active ? '#126636' : 'var(--ksp-red)' }}>
                      {u.is_active ? 'ACTIVE' : 'DEACTIVATED'}
                    </span>
                    {u.must_change_password && u.is_active && (
                      <span className="block text-[10px] text-gray-500">must change pwd</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {isUnitUser && !isSelf ? (
                      <div className="flex justify-end gap-1">
                        <IconBtn title="Edit" onClick={() => setEditTarget(u)} disabled={!u.is_active}>
                          <Pencil className="w-4 h-4" />
                        </IconBtn>
                        <IconBtn title="Reset password" onClick={() => handleReset(u)} disabled={!u.is_active}>
                          <KeyRound className="w-4 h-4" />
                        </IconBtn>
                        {u.is_active ? (
                          <IconBtn title="Deactivate" onClick={() => handleDeactivate(u)} variant="danger">
                            <ShieldOff className="w-4 h-4" />
                          </IconBtn>
                        ) : (
                          <IconBtn title="Re-activate" onClick={() => handleActivate(u)} variant="success">
                            <ShieldCheck className="w-4 h-4" />
                          </IconBtn>
                        )}
                      </div>
                    ) : (
                      <span className="text-xs text-gray-400 italic">{isSelf ? 'you' : 'no actions'}</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Modals */}
      {createOpen && (
        <CreateUserModal
          onClose={() => setCreateOpen(false)}
          onSuccess={(username, password) => {
            setCreateOpen(false);
            setCredsModal({ username, password, mode: 'created' });
            refresh();
          }}
        />
      )}

      {editTarget && (
        <EditUserModal
          target={editTarget}
          onClose={() => setEditTarget(null)}
          onSaved={() => { setEditTarget(null); refresh(); }}
        />
      )}

      {credsModal && (
        <CredentialsModal
          username={credsModal.username}
          password={credsModal.password}
          mode={credsModal.mode}
          onClose={() => setCredsModal(null)}
        />
      )}
    </div>
  );
}


// ── Sub-components ────────────────────────────────────────────────────

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl p-4 bg-white shadow" style={{ border: '2px solid var(--ksp-navy)' }}>
      <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--ksp-red)' }}>{label}</p>
      <p className="text-3xl font-extrabold mt-1" style={{ color: 'var(--ksp-navy)' }}>{value}</p>
    </div>
  );
}

function IconBtn({
  children, onClick, title, disabled, variant,
}: {
  children: React.ReactNode;
  onClick: () => void;
  title: string;
  disabled?: boolean;
  variant?: 'danger' | 'success';
}) {
  const colors =
    variant === 'danger' ? { bg: 'rgba(177,0,0,0.08)', fg: 'var(--ksp-red)' } :
    variant === 'success' ? { bg: 'rgba(18,102,54,0.08)', fg: '#126636' } :
    { bg: 'rgba(11,44,74,0.08)', fg: 'var(--ksp-navy)' };
  return (
    <button
      onClick={onClick}
      title={title}
      disabled={disabled}
      className="p-2 rounded-md hover:opacity-80 transition disabled:opacity-30 disabled:cursor-not-allowed"
      style={{ background: colors.bg, color: colors.fg }}
    >
      {children}
    </button>
  );
}

function ModalShell({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.5)' }}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6" style={{ border: '3px solid var(--ksp-yellow)' }}>
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-bold" style={{ color: 'var(--ksp-navy)' }}>{title}</h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-gray-100"><X className="w-5 h-5" /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

function CreateUserModal({
  onClose, onSuccess,
}: {
  onClose: () => void;
  onSuccess: (username: string, password: string) => void;
}) {
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [mobile, setMobile] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState('');

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr('');
    if (!fullName.trim() || !email.trim() || !mobile.trim()) {
      setErr('All fields are required');
      return;
    }
    setSubmitting(true);
    try {
      const res = await createUser({ full_name: fullName.trim(), email: email.trim(), mobile: mobile.trim() });
      onSuccess(res.user.username, res.generated_password);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to create user');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ModalShell title="Create New User" onClose={onClose}>
      <p className="text-xs text-gray-600 mb-4">
        Username and a temporary password will be generated automatically. The user will be required to change the password on first login.
      </p>
      {err && (
        <div className="mb-3 px-3 py-2 rounded-lg text-xs font-semibold"
             style={{ background: 'rgba(177,0,0,0.08)', color: 'var(--ksp-red)' }}>{err}</div>
      )}
      <form onSubmit={submit} className="space-y-3">
        <Field label="Full Name">
          <input type="text" required value={fullName} onChange={e => setFullName(e.target.value)}
                 className="w-full px-3 py-2 rounded-lg text-sm outline-none" style={{ border: '2px solid var(--ksp-navy)' }} />
        </Field>
        <Field label="Email Address">
          <input type="email" required value={email} onChange={e => setEmail(e.target.value)}
                 className="w-full px-3 py-2 rounded-lg text-sm outline-none" style={{ border: '2px solid var(--ksp-navy)' }} />
        </Field>
        <Field label="Mobile Number">
          <input type="tel" required value={mobile} onChange={e => setMobile(e.target.value)}
                 placeholder="10 digits" className="w-full px-3 py-2 rounded-lg text-sm outline-none" style={{ border: '2px solid var(--ksp-navy)' }} />
        </Field>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 rounded-lg text-sm font-semibold" style={{ background: '#e5e7eb' }}>Cancel</button>
          <button type="submit" disabled={submitting} className="px-4 py-2 rounded-lg text-sm font-bold disabled:opacity-50"
                  style={{ background: 'var(--ksp-yellow)', color: '#000', border: '2px solid rgba(0,0,0,0.25)' }}>
            {submitting ? 'Creating…' : 'Create User'}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}

function EditUserModal({
  target, onClose, onSaved,
}: {
  target: ManagedUser;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [fullName, setFullName] = useState(target.full_name ?? '');
  const [email, setEmail] = useState(target.email ?? '');
  const [mobile, setMobile] = useState(target.mobile ?? '');
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState('');

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr('');
    setSubmitting(true);
    try {
      await updateUser(target.id, {
        full_name: fullName.trim() || undefined,
        email: email.trim() || undefined,
        mobile: mobile.trim() || undefined,
      });
      toast.success(`${target.username} updated`);
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to update');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ModalShell title={`Edit ${target.username}`} onClose={onClose}>
      {err && (
        <div className="mb-3 px-3 py-2 rounded-lg text-xs font-semibold"
             style={{ background: 'rgba(177,0,0,0.08)', color: 'var(--ksp-red)' }}>{err}</div>
      )}
      <form onSubmit={submit} className="space-y-3">
        <Field label="Full Name">
          <input type="text" value={fullName} onChange={e => setFullName(e.target.value)}
                 className="w-full px-3 py-2 rounded-lg text-sm outline-none" style={{ border: '2px solid var(--ksp-navy)' }} />
        </Field>
        <Field label="Email Address">
          <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                 className="w-full px-3 py-2 rounded-lg text-sm outline-none" style={{ border: '2px solid var(--ksp-navy)' }} />
        </Field>
        <Field label="Mobile Number">
          <input type="tel" value={mobile} onChange={e => setMobile(e.target.value)}
                 className="w-full px-3 py-2 rounded-lg text-sm outline-none" style={{ border: '2px solid var(--ksp-navy)' }} />
        </Field>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 rounded-lg text-sm font-semibold" style={{ background: '#e5e7eb' }}>Cancel</button>
          <button type="submit" disabled={submitting} className="px-4 py-2 rounded-lg text-sm font-bold disabled:opacity-50"
                  style={{ background: 'var(--ksp-yellow)', color: '#000', border: '2px solid rgba(0,0,0,0.25)' }}>
            {submitting ? 'Saving…' : 'Save Changes'}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}

function CredentialsModal({
  username, password, mode, onClose,
}: {
  username: string;
  password: string;
  mode: 'created' | 'reset';
  onClose: () => void;
}) {
  const heading = mode === 'created' ? 'User Created' : 'Password Reset';
  const lead =
    mode === 'created'
      ? 'Hand these credentials to the user. They will be forced to change the password on first login.'
      : 'A new temporary password has been generated. The user must change it on next login.';

  function copyAll() {
    const text = `Username: ${username}\nTemporary Password: ${password}`;
    navigator.clipboard.writeText(text).then(
      () => toast.success('Copied to clipboard'),
      () => toast.error('Copy failed — please write it down')
    );
  }

  return (
    <ModalShell title={heading} onClose={onClose}>
      <p className="text-xs text-gray-700 mb-4">{lead}</p>
      <div className="space-y-3 mb-4">
        <Field label="Username">
          <div className="px-3 py-2 rounded-lg text-sm font-mono bg-gray-50" style={{ border: '2px solid var(--ksp-navy)' }}>
            {username}
          </div>
        </Field>
        <Field label="Temporary Password">
          <PasswordInput value={password} readOnly toggleLabel="Show password" />
        </Field>
      </div>
      <div className="px-3 py-2 rounded-lg text-xs font-semibold mb-4"
           style={{ background: 'rgba(255,212,0,0.2)', color: 'var(--ksp-navy)', border: '1px solid var(--ksp-yellow-border)' }}>
        ⚠ This password will not be shown again. Copy or write it down now.
      </div>
      <div className="flex justify-end gap-2">
        <button onClick={copyAll} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold"
                style={{ background: 'rgba(11,44,74,0.08)', color: 'var(--ksp-navy)' }}>
          <Copy className="w-4 h-4" /> Copy
        </button>
        <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm font-bold"
                style={{ background: 'var(--ksp-yellow)', color: '#000', border: '2px solid rgba(0,0,0,0.25)' }}>
          Done
        </button>
      </div>
    </ModalShell>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>{label}</label>
      {children}
    </div>
  );
}
