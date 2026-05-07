import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router';
import { login, getDistrictsPublic, getPoliceStationsPublic } from '../../lib/api/auth';
import { useAuthStore } from '../../lib/stores/auth-store';
import kspLogo from '../../assets/ksp_logo.png';

/**
 * Mirrors the backend `seed._to_code` — used to derive the username
 * deterministically from the selected police station + role.
 * If this formula is ever changed, seed.py and this function must move
 * together.
 */
function toCode(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

export function LoginForm() {
  const [districts, setDistricts] = useState<{name: string}[]>([]);
  const [selectedDistrict, setSelectedDistrict] = useState('');
  const [policeStations, setPoliceStations] = useState<{id: number, district_name: string, station_name: string, has_super_admin: boolean}[]>([]);
  const [selectedPS, setSelectedPS] = useState('');
  const [role, setRole] = useState<'user' | 'admin' | 'super'>('user');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { setAuth } = useAuthStore();
  const navigate = useNavigate();

  // Derived username — always matches what seed.py wrote to the DB
  const derivedUsername = selectedPS ? `${toCode(selectedPS)}_${role}` : '';

  // Only the one PS that has a Senior Officer seeded shows the Super option.
  const selectedPSRow = policeStations.find(ps => ps.station_name === selectedPS);
  const superAvailable = !!selectedPSRow?.has_super_admin;

  // Load districts on mount
  useEffect(() => {
    getDistrictsPublic()
      .then(setDistricts)
      .catch(() => setError('Failed to load districts'));
  }, []);

  // When district changes, fetch police stations and reset PS selection
  useEffect(() => {
    if (!selectedDistrict) {
      setPoliceStations([]);
      setSelectedPS('');
      return;
    }
    setSelectedPS('');
    getPoliceStationsPublic(selectedDistrict)
      .then(setPoliceStations)
      .catch(() => setPoliceStations([]));
  }, [selectedDistrict]);

  // If the selected PS doesn't have a super user, snap the role back to admin.
  useEffect(() => {
    if (role === 'super' && !superAvailable) setRole('admin');
  }, [role, superAvailable]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!selectedDistrict) { setError('Please select a district'); return; }
    if (!selectedPS) { setError('Please select a police station'); return; }
    if (!derivedUsername) { setError('Could not derive user ID'); return; }
    if (!password) { setError('Please enter password'); return; }

    setLoading(true);
    try {
      const res = await login(derivedUsername, password);

      setAuth(res.token, {
        id: 0,
        username: derivedUsername,
        full_name: null,
        role: res.role as 'admin' | 'unit_user' | 'super_admin',
        unit_id: res.unit_id,
        unit_name: res.unit_name ?? selectedDistrict,
        ps_name: res.ps_name ?? selectedPS,
      });

      if (res.must_change_password) {
        navigate('/change-password');
      } else {
        // admin + super_admin land on the dashboard, unit_user goes to cases.
        navigate(res.role === 'unit_user' ? '/cases' : '/dashboard');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4" style={{ background: 'var(--ksp-navy)' }}>
      <div className="rounded-2xl shadow-2xl p-8 w-full max-w-md" style={{ background: '#fff', border: '3px solid var(--ksp-yellow)' }}>
        {/* KSP Logo + Title */}
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center mb-3">
            <div className="p-2 rounded-xl" style={{ background: 'rgba(255,243,176,0.5)', boxShadow: 'inset 0 0 0 1px rgba(0,0,0,0.1)' }}>
              <img src={kspLogo} alt="KSP Logo" className="w-[120px] h-[100px] object-contain" />
            </div>
          </div>
          <h1 className="text-2xl font-bold" style={{ color: 'var(--ksp-navy)' }}>Cyber Fraud DSR</h1>
          <p className="text-sm font-semibold italic" style={{ color: 'var(--ksp-red)' }}>Karnataka State Police</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="px-4 py-3 rounded-xl text-sm font-semibold" style={{ background: 'rgba(177,0,0,0.08)', color: 'var(--ksp-red)', border: '1px solid rgba(177,0,0,0.2)' }}>
              {error}
            </div>
          )}

          {/* District dropdown */}
          <div>
            <label className="block text-sm font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>District</label>
            <select
              value={selectedDistrict}
              onChange={(e) => setSelectedDistrict(e.target.value)}
              required
              className="w-full px-4 py-2.5 rounded-xl text-sm font-medium outline-none transition"
              style={{ border: '2px solid var(--ksp-navy)', background: '#fff', color: 'var(--ksp-navy)' }}
            >
              <option value="">-- Select your district --</option>
              {districts.map((d) => (
                <option key={d.name} value={d.name}>{d.name}</option>
              ))}
            </select>
          </div>

          {/* Cyber Command Police Station dropdown */}
          <div>
            <label className="block text-sm font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>Cyber Command Police Station</label>
            <select
              value={selectedPS}
              onChange={(e) => setSelectedPS(e.target.value)}
              required
              className="w-full px-4 py-2.5 rounded-xl text-sm font-medium outline-none transition"
              style={{ border: '2px solid var(--ksp-navy)', background: '#fff', color: 'var(--ksp-navy)' }}
            >
              <option value="">{selectedDistrict ? '-- Select cyber command police station --' : '-- Select a district first --'}</option>
              {policeStations.map((ps) => (
                <option key={ps.id} value={ps.station_name}>{ps.station_name}</option>
              ))}
            </select>
          </div>

          {/* Role cycle — User → Admin → (Super) → User. The Super option
              only appears when the selected PS has the Senior Officer
              account anchored to it. For every other PS the toggle is
              binary (User / Admin). */}
          <div className="flex items-center justify-between text-xs">
            <span className="font-semibold" style={{ color: 'var(--ksp-navy)' }}>
              Signing in as: <span style={{ color: 'var(--ksp-red)' }}>
                {role === 'admin' ? 'Admin' : role === 'super' ? 'Super Admin' : 'User'}
              </span>
            </span>
            <button
              type="button"
              onClick={() => {
                if (superAvailable) {
                  setRole(role === 'user' ? 'admin' : role === 'admin' ? 'super' : 'user');
                } else {
                  setRole(role === 'admin' ? 'user' : 'admin');
                }
              }}
              className="font-semibold underline"
              style={{ color: 'var(--ksp-navy)' }}
            >
              Switch role
            </button>
          </div>

          {/* Derived User ID — read-only, shown for confirmation */}
          <div>
            <label className="block text-sm font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>User ID</label>
            <input
              type="text"
              value={derivedUsername}
              readOnly
              tabIndex={-1}
              className="w-full px-4 py-2.5 rounded-xl text-sm outline-none transition cursor-not-allowed"
              style={{ border: '2px solid var(--ksp-navy)', background: '#f3f4f6', color: '#374151' }}
              placeholder="Auto-filled after selecting a station"
            />
          </div>

          {/* Password */}
          <div>
            <label className="block text-sm font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              className="w-full px-4 py-2.5 rounded-xl text-sm outline-none transition"
              style={{ border: '2px solid var(--ksp-navy)' }}
              placeholder="Enter password"
            />
          </div>

          <button
            type="submit"
            disabled={loading || !derivedUsername}
            className="w-full py-2.5 font-bold rounded-xl transition disabled:opacity-50 text-sm"
            style={{ background: 'var(--ksp-yellow)', color: '#000', border: '2px solid rgba(0,0,0,0.25)' }}
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  );
}
