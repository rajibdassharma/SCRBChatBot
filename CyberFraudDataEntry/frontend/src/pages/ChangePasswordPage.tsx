import { useState } from 'react';
import { useNavigate } from 'react-router';
import { changePassword } from '../lib/api/auth';
import { useAuthStore } from '../lib/stores/auth-store';
import kspLogo from '../assets/ksp_logo.png';

export function ChangePasswordPage() {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!currentPassword) { setError('Please enter your current password'); return; }
    if (!newPassword) { setError('Please enter a new password'); return; }
    if (newPassword.length < 8) { setError('New password must be at least 8 characters'); return; }
    if (newPassword === currentPassword) { setError('New password must be different from current password'); return; }
    if (newPassword !== confirmPassword) { setError('Passwords do not match'); return; }

    setLoading(true);
    try {
      await changePassword(currentPassword, newPassword);
      // Password changed — force re-login with new password
      logout();
      navigate('/login');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to change password');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4" style={{ background: 'var(--ksp-navy)' }}>
      <div className="rounded-2xl shadow-2xl p-8 w-full max-w-md" style={{ background: '#fff', border: '3px solid var(--ksp-yellow)' }}>
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center mb-3">
            <div className="p-2 rounded-xl" style={{ background: 'rgba(255,243,176,0.5)', boxShadow: 'inset 0 0 0 1px rgba(0,0,0,0.1)' }}>
              <img src={kspLogo} alt="KSP Logo" className="w-[120px] h-[100px] object-contain" />
            </div>
          </div>
          <h1 className="text-2xl font-bold" style={{ color: 'var(--ksp-navy)' }}>Change Password</h1>
          <p className="text-sm mt-1" style={{ color: 'var(--ksp-red)' }}>
            You must change your default password before continuing.
          </p>
          {user && (
            <p className="text-xs mt-2" style={{ color: '#666' }}>
              Logged in as: <strong>{user.username}</strong>
            </p>
          )}
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="px-4 py-3 rounded-xl text-sm font-semibold" style={{ background: 'rgba(177,0,0,0.08)', color: 'var(--ksp-red)', border: '1px solid rgba(177,0,0,0.2)' }}>
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>Current Password</label>
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
              className="w-full px-4 py-2.5 rounded-xl text-sm outline-none transition"
              style={{ border: '2px solid var(--ksp-navy)' }}
              placeholder="Enter your current password"
            />
          </div>

          <div>
            <label className="block text-sm font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>New Password</label>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              className="w-full px-4 py-2.5 rounded-xl text-sm outline-none transition"
              style={{ border: '2px solid var(--ksp-navy)' }}
              placeholder="At least 8 characters"
            />
          </div>

          <div>
            <label className="block text-sm font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>Confirm New Password</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              className="w-full px-4 py-2.5 rounded-xl text-sm outline-none transition"
              style={{ border: '2px solid var(--ksp-navy)' }}
              placeholder="Re-enter new password"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 font-bold rounded-xl transition disabled:opacity-50 text-sm"
            style={{ background: 'var(--ksp-yellow)', color: '#000', border: '2px solid rgba(0,0,0,0.25)' }}
          >
            {loading ? 'Changing...' : 'Change Password'}
          </button>
        </form>
      </div>
    </div>
  );
}
