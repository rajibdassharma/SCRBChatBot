import { useNavigate } from 'react-router';
import { useAuthStore } from '../lib/stores/auth-store';
import { MODULES, type ModuleDef } from '../lib/utils/modules';

/** Tile-grid landing page — the post-login home. One tile per top-
 *  level module (Cases / NCRP / All Accounts / Portals DSR / Admin).
 *
 *  Compact solid-colour tiles: each shows just its icon + module name,
 *  no tagline or previews. Full-bleed accent colour keeps the modules
 *  visually distinct at a glance so operators pick by colour + shape,
 *  not by reading. Clicking a tile navigates to its landingUrl and the
 *  Sidebar switches to that module's contextual link list. */

function Tile({ module, onEnter }: { module: ModuleDef; onEnter: () => void }) {
  const Icon = module.icon;
  return (
    <button
      type="button"
      onClick={onEnter}
      className="flex flex-col items-center justify-center gap-3 rounded-2xl p-4 aspect-square min-h-[140px] transition hover:-translate-y-0.5 hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-offset-2"
      style={{
        background: module.accent,
        color: '#fff',
        boxShadow: `0 4px 12px ${module.accent}40`,
      }}
    >
      <Icon className="w-9 h-9" strokeWidth={1.75} />
      <span className="text-sm font-bold text-center leading-tight">
        {module.label}
      </span>
    </button>
  );
}

export function HomePage() {
  const navigate = useNavigate();
  const { user } = useAuthStore();

  // Gate the Admin tile — same rule as the current sidebar.
  const isPsAdmin = user?.role === 'admin' || user?.role === 'super_admin';
  const visible = MODULES.filter((m) => !m.requiresPsAdmin || isPsAdmin);

  return (
    <div>
      {/* Header banner — matches the navy strip used across entry pages. */}
      <div className="rounded-2xl p-5 mb-6" style={{ background: 'var(--ksp-navy)', color: '#fff' }}>
        <h1 className="text-xl font-bold" style={{ color: 'var(--ksp-yellow)' }}>
          Welcome, {user?.username}
        </h1>
        <div className="flex gap-6 mt-2 text-sm flex-wrap">
          <span><strong>District:</strong> {user?.unit_name}</span>
          <span><strong>CCPS:</strong> {user?.ps_name || 'N/A'}</span>
          <span><strong>Role:</strong> {user?.role === 'super_admin' ? 'Super Admin' : user?.role === 'admin' ? 'Admin' : 'User'}</span>
        </div>
      </div>

      <div className="mb-5">
        <h2 className="text-[22px] font-bold" style={{ color: 'var(--ksp-navy)' }}>
          Choose a module
        </h2>
        <p className="text-sm font-medium" style={{ color: 'var(--ksp-red)' }}>
          Click a tile to open its workspace. You can come back here any time via the Home link in the sidebar.
        </p>
      </div>

      {/* Responsive tile grid — 2 on phone, 3 tablet, 5 on desktop (fits
           all 5 tiles in a single row for admins). */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 max-w-4xl">
        {visible.map((m) => (
          <Tile key={m.key} module={m} onEnter={() => navigate(m.landingUrl)} />
        ))}
      </div>
    </div>
  );
}
