import { useState } from 'react';
import { useNavigate } from 'react-router';
import { Search } from 'lucide-react';
import { searchCaseByPetition } from '../lib/api/cases';
import { useAuthStore } from '../lib/stores/auth-store';

export function PetitionUpdatePage() {
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const [petitionNo, setPetitionNo] = useState('');
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState('');

  const handleSearch = async () => {
    if (!petitionNo.trim()) return;
    setSearching(true);
    setError('');
    try {
      const result = await searchCaseByPetition(petitionNo.trim());
      if (result && result.id) {
        navigate(`/petitions/${result.id}`);
      } else {
        setError('No case found with this Petition number');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed');
    } finally {
      setSearching(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSearch();
  };

  return (
    <div>
      {/* DSR Header */}
      <div className="rounded-2xl p-4 mb-4" style={{ background: 'var(--ksp-navy)', color: '#fff' }}>
        <h1 className="text-lg font-bold" style={{ color: 'var(--ksp-yellow)' }}>Daily Status Report</h1>
        <div className="flex gap-6 mt-2 text-sm">
          <span><strong>District:</strong> {user?.unit_name}</span>
          <span><strong>CCPS:</strong> {user?.ps_name || 'N/A'}</span>
          <span><strong>User:</strong> {user?.username}</span>
        </div>
      </div>

      <h1 className="text-[22px] font-bold mb-1" style={{ color: 'var(--ksp-navy)' }}>Update Petition</h1>
      <p className="text-sm font-medium mb-6" style={{ color: 'var(--ksp-red)' }}>Search for a petition by number to edit it</p>

      <div className="max-w-xl">
        <div className="rounded-2xl p-6" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
          <label className="block text-xs font-semibold mb-2" style={{ color: 'var(--ksp-navy)' }}>Enter Petition No</label>
          <div className="flex gap-3">
            <input
              type="text"
              value={petitionNo}
              onChange={(e) => setPetitionNo(e.target.value)}
              onKeyDown={handleKeyDown}
              className="flex-1 px-3 py-2 rounded-xl text-sm outline-none"
              style={{ border: '2px solid var(--ksp-navy)', background: '#fff' }}
              placeholder="e.g. PET-2026-001"
            />
            <button
              type="button"
              onClick={handleSearch}
              disabled={searching || !petitionNo.trim()}
              className="flex items-center gap-2 px-5 py-2 text-sm font-semibold rounded-xl transition disabled:opacity-50"
              style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)', border: '2px solid rgba(0,0,0,0.25)' }}
            >
              <Search className="w-4 h-4" /> {searching ? 'Searching...' : 'Search'}
            </button>
          </div>

          {error && (
            <div className="mt-4 px-4 py-3 rounded-xl text-sm font-semibold" style={{ background: 'rgba(177,0,0,0.08)', color: 'var(--ksp-red)', border: '1px solid rgba(177,0,0,0.2)' }}>
              {error}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
