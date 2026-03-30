import { Outlet } from 'react-router';
import { Sidebar } from './Sidebar';

export function AppShell() {
  return (
    <div className="flex min-h-screen" style={{ background: 'var(--ksp-bg)' }}>
      <Sidebar />
      <main className="flex-1 overflow-auto" style={{ padding: '28px 32px 36px', maxWidth: '1300px' }}>
        <Outlet />
      </main>
    </div>
  );
}
