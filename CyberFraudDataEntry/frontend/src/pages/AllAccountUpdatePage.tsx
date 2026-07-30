import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { toast } from 'sonner';
import { Plus, Search } from 'lucide-react';
import { listAllAccounts } from '../lib/api/all-accounts';
import { getAllPoliceStationsPublic } from '../lib/api/auth';
import { useAuthStore } from '../lib/stores/auth-store';
import type { AccountType, AllAccountListItem } from '../types';

/** Chip colour per account type — green for Victim (positive
 *  identification of a wronged party), red for Mule (confirmed
 *  fraudster account), slate for Non-Mule (under review or
 *  cleared). */
const TYPE_CHIP: Record<AccountType, { bg: string; fg: string }> = {
  Victim:     { bg: 'rgba(10,107,40,0.12)', fg: '#0a6b28' },
  Mule:       { bg: 'rgba(177,0,0,0.10)',   fg: '#8b1919' },
  'Non-Mule': { bg: 'rgba(11,44,74,0.08)',  fg: '#0b2c4a' },
};

/** Update Account — FIR-scoped inbox.
 *
 *  Design intent (2026-07-30):
 *  - Only input is FIR No; the table lists every account this PS
 *    has registered against that FIR.
 *  - unit_user / admin: PS is implicit (backend pins to their JWT),
 *    Account No is a blue hyperlink -> edit page.
 *  - super_admin: read-only cross-PS oversight; must pick a PS
 *    from the dropdown alongside the FIR because FIR Nos are only
 *    unique per (unit_id, ps_id).
 *  - Table is 5 columns wide (Serial / Account No / Bank / Holder
 *    / Type) so it fits within the content width without a
 *    horizontal scrollbar on typical laptop screens.
 */
export function AllAccountUpdatePage() {
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const isSuperAdmin = user?.role === 'super_admin';

  // Search state is mirrored into the URL as ?ps=&fir= so that the
  // "Back to list" button on the entry page (navigate(-1)) restores
  // the search view instead of remounting empty. Seeding from the
  // URL lets refreshes and deep links land on the same results.
  const [searchParams] = useSearchParams();
  const initialFir = searchParams.get('fir') ?? '';
  const initialPsRaw = searchParams.get('ps');
  const initialPs = initialPsRaw && !Number.isNaN(Number(initialPsRaw))
    ? Number(initialPsRaw)
    : '' as '' | number;

  const [firInput, setFirInput] = useState(initialFir);
  const [firSubmitted, setFirSubmitted] = useState('');
  const [rows, setRows] = useState<AllAccountListItem[]>([]);
  const [busy, setBusy] = useState(false);

  // PS dropdown -- only used for super_admin. Loaded lazily on
  // first render so admin/unit_user don't pay the round-trip.
  const [psList, setPsList] = useState<{id: number, district_name: string, station_name: string}[]>([]);
  const [selectedPsId, setSelectedPsId] = useState<number | ''>(initialPs);

  useEffect(() => {
    if (!isSuperAdmin) return;
    let alive = true;
    getAllPoliceStationsPublic()
      .then((r) => {
        if (!alive) return;
        setPsList([...r].sort((a, b) =>
          a.district_name.localeCompare(b.district_name) ||
          a.station_name.localeCompare(b.station_name)));
      })
      .catch((e) => toast.error(e instanceof Error ? e.message : 'Failed to load PS list'));
    return () => { alive = false; };
  }, [isSuperAdmin]);

  const psByDistrict = useMemo(() => {
    const map = new Map<string, {id: number, station_name: string}[]>();
    for (const p of psList) {
      const arr = map.get(p.district_name) ?? [];
      arr.push({ id: p.id, station_name: p.station_name });
      map.set(p.district_name, arr);
    }
    return Array.from(map.entries()).map(([district, stations]) => ({ district, stations }));
  }, [psList]);

  const runSearch = (opts: { silent?: boolean } = {}) => {
    const fir = firInput.trim();
    if (!fir) {
      if (!opts.silent) toast.error('Enter an FIR No to search.');
      return;
    }
    if (isSuperAdmin && selectedPsId === '') {
      if (!opts.silent) toast.error('Pick a Police Station -- FIR Nos are only unique per PS.');
      return;
    }
    setFirSubmitted(fir);
    setBusy(true);
    // Mirror the query to the URL so the entry page's Back button
    // (navigate(-1)) restores this exact view. replace=true so we
    // don't stack a history entry per keystroke-triggered search.
    const params = new URLSearchParams({ fir });
    if (isSuperAdmin && selectedPsId !== '') params.set('ps', String(selectedPsId));
    navigate({ pathname: '/all-accounts/update', search: `?${params.toString()}` }, { replace: true });
    listAllAccounts({
      firNo: fir,
      psId: isSuperAdmin && selectedPsId !== '' ? selectedPsId : undefined,
      limit: 200,
    })
      .then(setRows)
      .catch((e) => {
        setRows([]);
        toast.error(e instanceof Error ? e.message : 'Search failed');
      })
      .finally(() => setBusy(false));
  };

  // Auto-run search on mount if the URL brought us here with search
  // params (typically via the entry page's Back button). Fires once
  // per mount; user interactions after that go through runSearch.
  useEffect(() => {
    if (!initialFir) return;
    if (isSuperAdmin && initialPs === '') return;
    runSearch({ silent: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const summary = useMemo(() => {
    const victims = rows.filter((r) => r.account_type === 'Victim').length;
    const mules = rows.filter((r) => r.account_type === 'Mule').length;
    const nonMules = rows.filter((r) => r.account_type === 'Non-Mule').length;
    return { victims, mules, nonMules };
  }, [rows]);

  return (
    <div>
      {/* Header */}
      <div className="rounded-2xl p-4 mb-4" style={{ background: 'var(--ksp-navy)', color: '#fff' }}>
        <h1 className="text-lg font-bold" style={{ color: 'var(--ksp-yellow)' }}>All Accounts</h1>
        <div className="flex gap-6 mt-2 text-sm">
          <span><strong>District:</strong> {user?.unit_name}</span>
          <span><strong>CCPS:</strong> {user?.ps_name || 'N/A'}</span>
          <span><strong>User:</strong> {user?.username}</span>
        </div>
      </div>

      <div className="flex items-center justify-between mb-4 gap-4 flex-wrap">
        <div>
          <h1 className="text-[22px] font-bold mb-1" style={{ color: 'var(--ksp-navy)' }}>
            Update Account
          </h1>
          <p className="text-sm font-medium" style={{ color: 'var(--ksp-red)' }}>
            {isSuperAdmin
              ? 'Pick a Police Station and enter an FIR No to list its accounts. Click an Account No to open the entry page for edit.'
              : 'Enter an FIR No to list the accounts your PS has registered against it. Click an Account No to edit.'}
          </p>
        </div>
        {!isSuperAdmin && (
          <Link to="/all-accounts/new"
            className="flex items-center gap-1.5 px-4 py-2 text-sm font-bold rounded-xl transition"
            style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)', border: '2px solid rgba(0,0,0,0.25)' }}>
            <Plus className="w-4 h-4" /> New Account
          </Link>
        )}
      </div>

      {/* Filter bar: PS dropdown (super_admin only) + FIR input + Search button. */}
      <div className="rounded-2xl p-4 mb-4 flex items-center gap-3 flex-wrap"
        style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
        {isSuperAdmin && (
          <label className="flex items-center gap-2 min-w-[260px]">
            <span className="text-xs font-semibold" style={{ color: 'var(--ksp-navy)' }}>PS:</span>
            <select
              value={selectedPsId === '' ? '' : String(selectedPsId)}
              onChange={(e) => setSelectedPsId(e.target.value === '' ? '' : Number(e.target.value))}
              className="flex-1 px-3 py-2 rounded-lg text-sm outline-none bg-white"
              style={{ border: '2px solid var(--ksp-navy)' }}>
              <option value="">— pick a Police Station —</option>
              {psByDistrict.map(({ district, stations }) => (
                <optgroup key={district} label={district}>
                  {stations.map((s) => (
                    <option key={s.id} value={String(s.id)}>{s.station_name}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
        )}
        <div className="relative flex-1 min-w-[240px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 opacity-40" />
          <input type="text" value={firInput}
            onChange={(e) => setFirInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') runSearch(); }}
            placeholder="FIR No (e.g. 0042/2026) — press Enter to search"
            className="w-full pl-9 pr-3 py-2 rounded-xl text-sm outline-none"
            style={{ border: '2px solid var(--ksp-navy)', background: '#fff' }} />
        </div>
        <button type="button" onClick={() => runSearch()} disabled={busy}
          className="px-4 py-2 text-sm font-bold rounded-xl disabled:opacity-50"
          style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)' }}>
          {busy ? 'Searching…' : 'Search'}
        </button>
      </div>

      {/* Results summary -- only after a search has run. */}
      {firSubmitted && !busy && (
        <p className="text-sm mb-2 opacity-80" style={{ color: 'var(--ksp-navy)' }}>
          <strong>FIR {firSubmitted}:</strong> {rows.length} record{rows.length === 1 ? '' : 's'}
          {rows.length > 0 && (
            <> · {summary.victims} victim · {summary.mules} mule · {summary.nonMules} non-mule</>
          )}
        </p>
      )}

      {/* Table -- 5 cols, table-fixed so widths stick and content
           truncates rather than blowing the layout. */}
      <div className="rounded-2xl overflow-hidden shadow-sm bg-white">
        <table className="w-full text-sm" style={{ tableLayout: 'fixed' }}>
          <colgroup>
            <col style={{ width: '10%' }} />
            <col style={{ width: '22%' }} />
            <col style={{ width: '25%' }} />
            <col style={{ width: '28%' }} />
            <col style={{ width: '15%' }} />
          </colgroup>
          <thead style={{ background: 'var(--ksp-navy)', color: '#fff' }}>
            <tr>
              <th className="px-3 py-2 text-left">#</th>
              <th className="px-3 py-2 text-left">Account No</th>
              <th className="px-3 py-2 text-left">Bank</th>
              <th className="px-3 py-2 text-left">Holder</th>
              <th className="px-3 py-2 text-left">Type</th>
            </tr>
          </thead>
          <tbody>
            {!firSubmitted && (
              <tr><td colSpan={5} className="px-3 py-10 text-center italic opacity-60">
                Enter an FIR No above and press Search to list its accounts.
              </td></tr>
            )}
            {busy && (
              <tr><td colSpan={5} className="px-3 py-8 text-center italic opacity-60">Loading…</td></tr>
            )}
            {firSubmitted && !busy && rows.length === 0 && (
              <tr><td colSpan={5} className="px-3 py-8 text-center italic opacity-60">
                No accounts registered against FIR {firSubmitted}
                {isSuperAdmin ? ' at the selected PS.' : ' at your PS.'}
              </td></tr>
            )}
            {!busy && rows.map((r, i) => (
              <tr key={r.id} className="border-t border-slate-100 hover:bg-slate-50">
                {/* Row-position counter (1..N), not the DB serial_no. */}
                <td className="px-3 py-2 font-mono truncate">{i + 1}</td>
                <td className="px-3 py-2 font-mono truncate">
                  {/* Blue hyperlink for every role -- super_admin now
                       also opens the entry page for edit (2026-07-30
                       update to the earlier display-only decision). */}
                  <button
                    type="button"
                    onClick={() => navigate(`/all-accounts/${r.id}`)}
                    className="text-left underline hover:no-underline"
                    style={{ color: '#1d4ed8' }}
                    title="Open in Update Account"
                  >
                    {r.account_no}
                  </button>
                </td>
                <td className="px-3 py-2 truncate" title={r.bank_name}>{r.bank_name}</td>
                <td className="px-3 py-2 truncate" title={r.account_holder_name}>{r.account_holder_name}</td>
                <td className="px-3 py-2">
                  <span className="px-2 py-0.5 rounded-full text-xs font-semibold whitespace-nowrap"
                    style={{
                      background: TYPE_CHIP[r.account_type].bg,
                      color:      TYPE_CHIP[r.account_type].fg,
                    }}>
                    {r.account_type}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
