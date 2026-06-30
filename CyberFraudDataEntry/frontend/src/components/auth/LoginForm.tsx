import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router';
import { login, getDistrictsPublic, getPoliceStationsPublic, getUsersForPSPublic } from '../../lib/api/auth';
import { useAuthStore } from '../../lib/stores/auth-store';
import { PasswordInput } from '../ui/PasswordInput';
import kspLogo from '../../assets/ksp_logo.png';

const ROLE_LABEL: Record<string, string> = {
  super_admin: 'Super Admin',
  admin: 'Admin',
  unit_user: 'User',
};

export function LoginForm() {
  const [districts, setDistricts] = useState<{name: string}[]>([]);
  const [selectedDistrict, setSelectedDistrict] = useState('');
  const [policeStations, setPoliceStations] = useState<{id: number, district_name: string, station_name: string, has_super_admin: boolean}[]>([]);
  const [selectedPS, setSelectedPS] = useState('');
  const [users, setUsers] = useState<{username: string; role: string}[]>([]);
  const [selectedUsername, setSelectedUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { setAuth } = useAuthStore();
  const navigate = useNavigate();

  // The picked PS row — used to look up its id for the users fetch.
  const selectedPSRow = policeStations.find(ps => ps.station_name === selectedPS);

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

  // When PS changes, fetch the active users at that PS. Pre-select the
  // single user if there's only one, otherwise leave empty so the
  // operator picks from the dropdown.
  useEffect(() => {
    setSelectedUsername('');
    setUsers([]);
    if (!selectedPSRow) return;
    let cancelled = false;
    getUsersForPSPublic(selectedPSRow.id)
      .then((rows) => {
        if (cancelled) return;
        setUsers(rows);
        if (rows.length === 1) setSelectedUsername(rows[0].username);
      })
      .catch(() => { if (!cancelled) setUsers([]); });
    return () => { cancelled = true; };
  }, [selectedPSRow]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!selectedDistrict) { setError('Please select a district'); return; }
    if (!selectedPS) { setError('Please select a police station'); return; }
    if (!selectedUsername) { setError('Please select a User ID'); return; }
    if (!password) { setError('Please enter password'); return; }

    setLoading(true);
    try {
      const res = await login(selectedUsername, password);

      setAuth(res.token, {
        id: 0,
        username: selectedUsername,
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

          {/* User ID — server tells us which users live at the selected PS.
              For PSes with multiple users (the common case — admin + user
              from seed.py, and now multi-officer PSes like CID), this is
              a dropdown. With a single user it auto-selects and reads as
              a regular dropdown with one option. Role is shown inline so
              the operator knows which entry is theirs. */}
          <div>
            <label className="block text-sm font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>User ID</label>
            <select
              value={selectedUsername}
              onChange={(e) => setSelectedUsername(e.target.value)}
              required
              disabled={!selectedPS || users.length === 0}
              className="w-full px-4 py-2.5 rounded-xl text-sm font-medium outline-none transition disabled:cursor-not-allowed disabled:bg-gray-100"
              style={{ border: '2px solid var(--ksp-navy)', background: '#fff', color: 'var(--ksp-navy)' }}
            >
              <option value="">
                {!selectedPS
                  ? '-- Select a police station first --'
                  : users.length === 0
                    ? '-- No active users at this station --'
                    : '-- Select your User ID --'}
              </option>
              {users.map((u) => (
                <option key={u.username} value={u.username}>
                  {u.username} — {ROLE_LABEL[u.role] ?? u.role}
                </option>
              ))}
            </select>
          </div>

          {/* Password */}
          <div>
            <label className="block text-sm font-semibold mb-1" style={{ color: 'var(--ksp-navy)' }}>Password</label>
            <PasswordInput
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              placeholder="Enter password"
            />
          </div>

          <button
            type="submit"
            disabled={loading || !selectedUsername}
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
