import {
  BarChart3, Briefcase, Building2, ClipboardList, FileDown, FilePlus,
  FileText, Globe, MessageSquare, Search, Settings, Upload, Users, Wallet,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

/** Central definition of the 5 top-level modules and every sidebar
 *  link inside each. Drives BOTH the tile-grid landing page and the
 *  contextual sidebar (which shows only the current module's links).
 *
 *  Adding a new module = one entry here. The sidebar + HomePage pick
 *  it up automatically, so we never end up with sidebar sprawl again. */

export type ModuleKey = 'cases' | 'ncrp' | 'accounts' | 'dsr' | 'admin';

export type ModuleLink = {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Show this link only to admin / super_admin. */
  requiresAdmin?: boolean;
  /** Show this link only if the server's chat feature flag is on. */
  requiresChat?: boolean;
};

export type ModuleDef = {
  key: ModuleKey;
  label: string;
  /** One-line description shown under the tile title on the landing page. */
  tagline: string;
  /** Icon shown BIG on the tile + small next to sidebar title. */
  icon: LucideIcon;
  /** Accent colour for tile + sidebar highlight. */
  accent: string;
  /** URL prefixes that "belong" to this module — the sidebar uses these
   *  to decide which module the current URL falls in. Both exact matches
   *  and `<prefix>/rest` matches count. */
  urlPrefixes: string[];
  /** Gate the tile itself. e.g. only admins see the Admin tile. */
  requiresPsAdmin?: boolean;
  /** If set, only users whose `ps_name` is in this list see the tile.
   *  super_admin bypasses (cross-PS oversight). Exact-string match
   *  against the users.ps_name value stored in the DB. */
  visibleForPsNames?: string[];
  /** Should this module's sidebar include the "Mark NIL Today" button? */
  hasNilButton?: boolean;
  /** URL to land on when the tile is clicked (usually the first link). */
  landingUrl: string;
  links: ModuleLink[];
};

export const MODULES: ModuleDef[] = [
  {
    key: 'cases',
    label: 'Cases & Petitions',
    tagline: 'Daily case + petition entry, NIL declaration, DSR reports and dashboard.',
    icon: Briefcase,
    accent: '#0b2c4a',   // navy
    urlPrefixes: ['/cases', '/petitions', '/dashboard', '/reports'],
    hasNilButton: true,
    landingUrl: '/cases/new',
    links: [
      { to: '/cases/new',        label: 'New Case',        icon: FilePlus },
      { to: '/cases/update',     label: 'Update Case',     icon: Search },
      { to: '/petitions/new',    label: 'New Petition',    icon: FileText },
      { to: '/petitions/update', label: 'Update Petition', icon: Search },
      { to: '/reports',          label: 'Reports',         icon: FileDown },
      { to: '/dashboard',        label: 'Cases & Petitions Dashboard', icon: BarChart3, requiresAdmin: true },
    ],
  },
  {
    key: 'ncrp',
    label: 'NCRP Data',
    tagline: 'Mule report entry, bulk Excel upload, and NCRP investigation records.',
    icon: Building2,
    accent: '#8b1919',   // red
    urlPrefixes: ['/mule'],
    // NCRP data entry is a CID-only workflow; other PSes don't touch
    // this. Test PS kept so the dev / QA account can still exercise
    // the flow. super_admin bypasses this gate.
    visibleForPsNames: ['CID', 'Test PS'],
    landingUrl: '/mule/new',
    links: [
      { to: '/mule/new',    label: 'New Report',       icon: FilePlus },
      { to: '/mule/update', label: 'Update Report',    icon: Search },
      { to: '/mule/upload', label: 'Upload Bulk Data', icon: Upload },
    ],
  },
  {
    key: 'accounts',
    label: 'All Accounts',
    tagline: 'Victim, Mule, and Non-Mule account records with drill-down dashboard.',
    icon: Wallet,
    accent: '#0a6b28',   // green
    urlPrefixes: ['/all-accounts', '/accounts-dashboard'],
    landingUrl: '/all-accounts/new',
    links: [
      { to: '/all-accounts/new',    label: 'New Account',    icon: FilePlus },
      { to: '/all-accounts/update', label: 'Update Account', icon: Search },
      { to: '/accounts-dashboard',  label: 'Account Details Dashboard', icon: BarChart3, requiresAdmin: true },
    ],
  },
  {
    key: 'dsr',
    label: 'DSR',
    tagline: 'Daily reporting — new FIR, per-FIR investigation activity, and portal counters.',
    icon: ClipboardList,
    accent: '#6a1b9a',   // purple — inherited from the retired Portals module.
    // /dsr owns the "New FIR" link that mounts CaseEntryPage under this
    // module. /daily-work + /portals-dsr keep their existing URLs so the
    // rest of the app + deep links keep working; the sidebar just treats
    // them all as part of this single module.
    urlPrefixes: ['/dsr', '/daily-work', '/portals-dsr'],
    landingUrl: '/dsr/new-fir',
    links: [
      // 3 primary entry points (New FIR, Investigation, Portals) as spec'd
      // 2026-07-22. Update / History links were dropped from the sidebar
      // per the same spec — pages remain reachable at their old URLs.
      { to: '/dsr/new-fir',           label: 'New FIR',                    icon: FilePlus },
      { to: '/daily-work/new',        label: 'Investigation',              icon: ClipboardList },
      { to: '/daily-work/report',     label: 'Daily Work Done Report',     icon: FileDown, requiresAdmin: true },
      { to: '/portals-dsr/new',       label: 'Portals',                    icon: Globe },
      { to: '/portals-dsr/report',    label: 'Portals DSR Report',         icon: FileDown, requiresAdmin: true },
      { to: '/dsr/fir-dashboard',     label: 'FIR Dashboard',              icon: BarChart3, requiresAdmin: true },
      { to: '/portals-dsr/dashboard', label: 'Portals DSR Dashboard',      icon: BarChart3, requiresAdmin: true },
      { to: '/daily-work/dashboard',  label: 'Daily Work Done Dashboard',  icon: BarChart3, requiresAdmin: true },
    ],
  },
  {
    key: 'admin',
    label: 'Admin',
    tagline: 'User management and "Ask the Data" chat interface.',
    icon: Settings,
    accent: '#5b6b7a',   // slate
    urlPrefixes: ['/users', '/chat'],
    requiresPsAdmin: true,
    landingUrl: '/users',
    links: [
      { to: '/users', label: 'User Management', icon: Users },
      { to: '/chat',  label: 'Ask the Data',    icon: MessageSquare, requiresChat: true },
    ],
  },
];

/** Return the module the given pathname belongs to, or null if it's
 *  the home page / an unrecognised URL. */
export function getCurrentModule(pathname: string): ModuleDef | null {
  for (const m of MODULES) {
    if (m.urlPrefixes.some((p) => pathname === p || pathname.startsWith(p + '/'))) {
      return m;
    }
  }
  return null;
}

/** Should the given user see the given module tile on the landing
 *  page? Combines every gate the ModuleDef exposes:
 *    - requiresPsAdmin: admin or super_admin role
 *    - visibleForPsNames: user's ps_name is in the allow-list
 *      (super_admin bypasses so HQ officers see everything)
 *  A module with no gates set is visible to everyone. */
export function isModuleVisibleForUser(
  m: ModuleDef,
  user: { role?: string | null; ps_name?: string | null } | null,
): boolean {
  if (m.requiresPsAdmin) {
    if (user?.role !== 'admin' && user?.role !== 'super_admin') return false;
  }
  if (m.visibleForPsNames && m.visibleForPsNames.length > 0) {
    if (user?.role === 'super_admin') return true;
    if (!user?.ps_name || !m.visibleForPsNames.includes(user.ps_name)) return false;
  }
  return true;
}
