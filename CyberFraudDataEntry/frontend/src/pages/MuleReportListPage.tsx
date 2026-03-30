import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router';
import { listMuleReports, deleteMuleReport } from '../lib/api/mule-reports';
import type { MuleReportListItem } from '../types';
import { toast } from 'sonner';
import { Landmark, Plus, Pencil, Trash2 } from 'lucide-react';

export function MuleReportListPage() {
  const navigate = useNavigate();
  const [reports, setReports] = useState<MuleReportListItem[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchReports = () => {
    setLoading(true);
    listMuleReports()
      .then(setReports)
      .catch(() => toast.error('Failed to load mule reports'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchReports(); }, []);

  const handleDelete = async (id: number, ackNo: string) => {
    if (!window.confirm(`Delete report ${ackNo}? This action cannot be undone.`)) return;
    try {
      await deleteMuleReport(id);
      toast.success(`Report ${ackNo} deleted`);
      setReports((prev) => prev.filter((r) => r.id !== id));
    } catch {
      toast.error('Failed to delete report');
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <h1 className="text-[22px] font-bold flex items-center gap-2" style={{ color: 'var(--ksp-navy)' }}>
          <Landmark className="w-6 h-6" /> Mule Reports
        </h1>
        <button
          onClick={() => navigate('/mule/new')}
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-semibold transition"
          style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)', border: '2px solid rgba(0,0,0,0.2)' }}
        >
          <Plus className="w-4 h-4" /> New Report
        </button>
      </div>
      <p className="text-sm font-medium mb-6" style={{ color: 'var(--ksp-red)' }}>Manage mule account reports for your unit</p>

      {loading ? (
        <div className="text-sm py-8 text-center" style={{ color: 'var(--ksp-navy)' }}>Loading...</div>
      ) : reports.length === 0 ? (
        <div className="rounded-2xl py-16 text-center" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
          <Landmark className="w-10 h-10 mx-auto mb-3 opacity-30" />
          <p className="text-sm opacity-50">No mule reports found. Click "New Report" to create one.</p>
        </div>
      ) : (
        <div className="rounded-2xl overflow-x-auto" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
          <table className="w-full text-sm text-left">
            <thead style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}>
              <tr>
                <th className="px-4 py-3 text-xs uppercase font-bold">Ack No</th>
                <th className="px-4 py-3 text-xs uppercase font-bold">FIR No</th>
                <th className="px-4 py-3 text-xs uppercase font-bold">Status</th>
                <th className="px-4 py-3 text-xs uppercase font-bold text-center">Transfers</th>
                <th className="px-4 py-3 text-xs uppercase font-bold text-center">Others</th>
                <th className="px-4 py-3 text-xs uppercase font-bold text-center">On Hold</th>
                <th className="px-4 py-3 text-xs uppercase font-bold text-center">&lt;500</th>
                <th className="px-4 py-3 text-xs uppercase font-bold text-center">AEPS</th>
                <th className="px-4 py-3 text-xs uppercase font-bold text-center">ATM</th>
                <th className="px-4 py-3 text-xs uppercase font-bold text-center">Actions</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((r) => (
                <tr key={r.id} className="border-t hover:bg-[#fff3b0]/30" style={{ borderColor: 'rgba(0,0,0,0.06)' }}>
                  <td className="px-4 py-3 font-semibold" style={{ color: 'var(--ksp-navy)' }}>{r.acknowledgement_no}</td>
                  <td className="px-4 py-3">{r.fir_no}</td>
                  <td className="px-4 py-3">
                    <span
                      className="inline-block px-2.5 py-1 text-xs font-bold rounded-full"
                      style={
                        r.status === 'submitted'
                          ? { background: '#dcfce7', color: '#166534' }
                          : { background: '#fef9c3', color: '#854d0e' }
                      }
                    >
                      {r.status === 'submitted' ? 'Submitted' : 'Draft'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">{r.money_transfer_count}</td>
                  <td className="px-4 py-3 text-center">{r.other_count}</td>
                  <td className="px-4 py-3 text-center">{r.hold_count}</td>
                  <td className="px-4 py-3 text-center">{r.less_500_count}</td>
                  <td className="px-4 py-3 text-center">{r.aeps_count}</td>
                  <td className="px-4 py-3 text-center">{r.atm_count}</td>
                  <td className="px-4 py-3 text-center">
                    <div className="flex items-center justify-center gap-2">
                      <button
                        onClick={() => navigate(`/mule/${r.id}`)}
                        className="p-1.5 rounded-lg transition hover:bg-[#0b2c4a]/10"
                        title="Edit"
                      >
                        <Pencil className="w-4 h-4" style={{ color: 'var(--ksp-navy)' }} />
                      </button>
                      <button
                        onClick={() => handleDelete(r.id, r.acknowledgement_no)}
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
