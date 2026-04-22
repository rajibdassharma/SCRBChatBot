import { NavLink } from 'react-router';
import { useAuthStore } from '../../lib/stores/auth-store';
import { FilePlus, Search, BarChart3, LogOut, FileText, Upload } from 'lucide-react';
import kspLogo from '../../assets/ksp_logo.png';

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-semibold transition ${
    isActive
      ? 'bg-[#0b2c4a] text-[#ffd400]'
      : 'text-[#0b2c4a] hover:bg-[rgba(11,44,74,0.1)]'
  }`;

export function Sidebar() {
  const { user, logout } = useAuthStore();
  const isAdmin = user?.role === 'admin';

  return (
    <aside className="w-[280px] flex flex-col min-h-screen p-4 gap-3" style={{ background: 'var(--ksp-yellow-soft)', borderRight: '2px solid var(--ksp-yellow-border)' }}>
      {/* KSP Logo */}
      <div className="flex justify-center items-center">
        <div className="p-2 rounded-xl" style={{ background: 'rgba(255,255,255,0.45)', boxShadow: 'inset 0 0 0 1px rgba(0,0,0,0.18)' }}>
          <img src={kspLogo} alt="KSP Logo" className="w-[180px] h-[140px] object-contain" />
        </div>
      </div>

      {/* Title */}
      <div className="text-center">
        <h2 className="text-lg font-bold" style={{ color: 'var(--ksp-navy)' }}>Cyber Fraud Cases</h2>
        <p className="text-xs font-medium" style={{ color: 'var(--ksp-red)' }}>Karnataka State Police</p>
      </div>

      {/* Divider */}
      <div className="h-[2px] mx-4" style={{ background: 'linear-gradient(to right, rgba(0,0,0,0), #b10000, rgba(0,0,0,0))' }} />

      {/* Navigation */}
      <nav className="flex-1 space-y-1">
        {/* Daily Status Report Section */}
        <p className="px-4 pt-2 pb-2 text-sm font-extrabold uppercase tracking-wide" style={{ color: 'var(--ksp-red)' }}>Daily Status Report</p>
        <NavLink to="/cases/new" className={linkClass}>
          <FilePlus className="w-4 h-4" /> New Case
        </NavLink>
        <NavLink to="/cases/update" className={linkClass}>
          <Search className="w-4 h-4" /> Update Case
        </NavLink>
        <NavLink to="/petitions/new" className={linkClass}>
          <FileText className="w-4 h-4" /> New Petition
        </NavLink>
        <NavLink to="/petitions/update" className={linkClass}>
          <Search className="w-4 h-4" /> Update Petition
        </NavLink>

        {/* Divider between sections */}
        <div className="h-[1px] mx-4 my-2" style={{ background: 'rgba(11,44,74,0.15)' }} />

        {/* Mule Accounts Data Section */}
        <p className="px-4 pt-1 pb-2 text-sm font-extrabold uppercase tracking-wide" style={{ color: 'var(--ksp-red)' }}>Mule Accounts Data</p>
        <NavLink to="/mule/new" className={linkClass}>
          <FilePlus className="w-4 h-4" /> New Report
        </NavLink>
        <NavLink to="/mule/update" className={linkClass}>
          <Search className="w-4 h-4" /> Update Report
        </NavLink>
        <NavLink to="/mule/upload" className={linkClass}>
          <Upload className="w-4 h-4" /> Upload Bulk Data
        </NavLink>

        {isAdmin && (
          <>
            <div className="h-[1px] mx-4 my-2" style={{ background: 'rgba(11,44,74,0.15)' }} />
            <NavLink to="/dashboard" className={linkClass}>
              <BarChart3 className="w-4 h-4" /> Dashboard
            </NavLink>
          </>
        )}
      </nav>

      {/* Divider */}
      <div className="h-[2px] mx-4" style={{ background: 'linear-gradient(to right, rgba(0,0,0,0), #b10000, rgba(0,0,0,0))' }} />

      {/* User info */}
      <div className="px-2">
        <p className="text-sm font-bold" style={{ color: 'var(--ksp-navy)' }}>{user?.unit_name}</p>
        <p className="text-xs font-semibold" style={{ color: 'var(--ksp-red)' }}>{user?.role === 'admin' ? 'Admin' : 'User'}</p>
      </div>

      <button
        onClick={async () => { await logout(); window.location.href = '/login'; }}
        className="flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-semibold rounded-xl transition"
        style={{ background: '#c62828', color: '#fff', border: '2px solid rgba(0,0,0,0.25)' }}
      >
        <LogOut className="w-4 h-4" /> Sign Out
      </button>
    </aside>
  );
}
