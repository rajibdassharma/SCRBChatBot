import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router';
import { listCases, deleteCase } from '../lib/api/cases';
import { useAuthStore } from '../lib/stores/auth-store';
import type { CaseListItem } from '../types';
import { toast } from 'sonner';
import { Briefcase, Plus, Pencil, Trash2 } from 'lucide-react';

export function CaseListPage() {
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const [cases, setCases] = useState<CaseListItem[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchCases = () => {
    setLoading(true);
    listCases()
      .then(setCases)
      .catch(() => toast.error('Failed to load cases'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchCases(); }, []);

  const handleDelete = async (id: number, firNo: string) => {
    if (!window.confirm(`Delete case ${firNo}? This action cannot be undone.`)) return;
    try {
      await deleteCase(id);
      toast.success(`Case ${firNo} deleted`);
      setCases((prev) => prev.filter((c) => c.id !== id));
    } catch {
      toast.error('Failed to delete case');
    }
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

      <div className="flex items-center justify-between mb-1">
        <h1 className="text-[22px] font-bold flex items-center gap-2" style={{ color: 'var(--ksp-navy)' }}>
          <Briefcase className="w-6 h-6" /> Cases
        </h1>
        <button
          onClick={() => navigate('/cases/new')}
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-semibold transition"
          style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)', border: '2px solid rgba(0,0,0,0.2)' }}
        >
          <Plus className="w-4 h-4" /> New Case
        </button>
      </div>
      <p className="text-sm font-medium mb-6" style={{ color: 'var(--ksp-red)' }}>Manage cases for your unit</p>

      {loading ? (
        <div className="text-sm py-8 text-center" style={{ color: 'var(--ksp-navy)' }}>Loading...</div>
      ) : cases.length === 0 ? (
        <div className="rounded-2xl py-16 text-center" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
          <Briefcase className="w-10 h-10 mx-auto mb-3 opacity-30" />
          <p className="text-sm opacity-50">No cases found. Click "New Case" to create one.</p>
        </div>
      ) : (
        <div className="rounded-2xl overflow-x-auto" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
          <table className="w-full text-sm text-left">
            <thead style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}>
              <tr>
                <th className="px-4 py-3 text-xs uppercase font-bold">FIR No</th>
                <th className="px-4 py-3 text-xs uppercase font-bold">Date</th>
                <th className="px-4 py-3 text-xs uppercase font-bold">Case Type</th>
                <th className="px-4 py-3 text-xs uppercase font-bold">Crime Type</th>
                <th className="px-4 py-3 text-xs uppercase font-bold">Status</th>
                <th className="px-4 py-3 text-xs uppercase font-bold">Arrests</th>
                <th className="px-4 py-3 text-xs uppercase font-bold text-center">Actions</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr key={c.id} className="border-t hover:bg-[#fff3b0]/30" style={{ borderColor: 'rgba(0,0,0,0.06)' }}>
                  <td className="px-4 py-3 font-semibold" style={{ color: 'var(--ksp-navy)' }}>{c.fir_no}</td>
                  <td className="px-4 py-3">{c.registration_date}</td>
                  <td className="px-4 py-3">{c.case_type}</td>
                  <td className="px-4 py-3">{c.crime_type}</td>
                  <td className="px-4 py-3">
                    <span
                      className="inline-block px-2.5 py-1 text-xs font-bold rounded-full"
                      style={
                        c.status === 'submitted'
                          ? { background: '#dcfce7', color: '#166534' }
                          : { background: '#fef9c3', color: '#854d0e' }
                      }
                    >
                      {c.status === 'submitted' ? 'Submitted' : 'Draft'}
                    </span>
                  </td>
                  <td className="px-4 py-3">{c.arrest_count}</td>
                  <td className="px-4 py-3 text-center">
                    <div className="flex items-center justify-center gap-2">
                      <button
                        onClick={() => navigate(`/cases/${c.id}`)}
                        className="p-1.5 rounded-lg transition hover:bg-[#0b2c4a]/10"
                        title="Edit"
                      >
                        <Pencil className="w-4 h-4" style={{ color: 'var(--ksp-navy)' }} />
                      </button>
                      <button
                        onClick={() => handleDelete(c.id, c.fir_no)}
                        className="p-1.5 rounded-lg transition hover:bg-red-50"
                        title="Delete"
                      >
                        <Trash2 className="w-4 h-4" style={{ color: 'var(--ksp-red)' }} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
