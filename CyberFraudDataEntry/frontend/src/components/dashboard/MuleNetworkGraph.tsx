/** Mule Network — node/edge diagram (2026-08-06).
 *
 *  WHY THIS IS AN EGO-NETWORK AND NOT THE WHOLE GRAPH
 *  --------------------------------------------------
 *  The network is 940 accounts and 1,309 links. Drawing all of it
 *  force-directed produces a hairball: technically a picture of the
 *  data, useless as a picture of anything an officer can act on. So it
 *  works the way the Neo4j browser actually gets used — one node at the
 *  centre, its direct links around it, and you expand outward by
 *  clicking. What is on screen is always a claim someone can check.
 *
 *  WHY RADIAL AND NOT FORCE-DIRECTED
 *  ---------------------------------
 *  A force simulation settles somewhere different on every run. For
 *  police work that is a real cost: a screenshot taken today should
 *  match the one taken tomorrow, and an officer describing "the node on
 *  the left" should still be right after a refresh. A radial layout is
 *  deterministic — same data, same picture, every time — and for a
 *  one-hop neighbourhood it is also simply easier to read.
 *
 *  NO NEW DEPENDENCY
 *  -----------------
 *  Hand-drawn SVG. d3-force or react-force-graph would each add weight
 *  to a bundle already at 1.9 MB, to solve a layout problem that a ring
 *  solves exactly. The existing Graphical Analysis view is hand-rolled
 *  the same way, so this matches what is here rather than importing a
 *  second idiom.
 *
 *  WHAT THE PICTURE ENCODES
 *  ------------------------
 *    node size    number of accounts that account is linked to
 *    node colour  red = a different FIR from the centre (the finding),
 *                 navy = same FIR (the case file restating itself)
 *    edge arrow   direction money actually moved
 *    edge width   transaction count, NOT amount — amounts are still
 *                 unvalidated until the balance-chain work lands, and
 *                 a graph that draws its thickest line from a misparsed
 *                 ₹44 billion row would be worse than one drawing none.
 */
import { useMemo, useState } from 'react';
import { Waypoints, ArrowLeft, List } from 'lucide-react';
import type { MuleNetworkRow, MuleLinkPeer } from '../../types';

const C_NAVY = '#0b2c4a';
const C_RED = '#8b1919';
const C_GREEN = '#0a6b28';

/** Neighbours drawn at once. Beyond this a ring stops being readable —
 *  the top account has 101 links, which at 360° is one node every 3.5
 *  degrees. The rest are reachable through the table, and the caption
 *  says how many are not shown rather than quietly dropping them. */
const MAX_RING = 40;

const W = 900;
const H = 620;
const CX = W / 2;
const CY = H / 2;

function short(s: string | null | undefined, n = 18): string {
  const t = (s || '—').trim();
  return t.length > n ? t.slice(0, n - 1) + '…' : t;
}

function rupeesShort(v: number): string {
  if (Math.abs(v) >= 1e7) return `₹${(v / 1e7).toFixed(1)}Cr`;
  if (Math.abs(v) >= 1e5) return `₹${(v / 1e5).toFixed(1)}L`;
  if (Math.abs(v) >= 1e3) return `₹${(v / 1e3).toFixed(0)}k`;
  return `₹${Math.round(v)}`;
}

export function MuleNetworkGraph({ centre, allRows, onRecentre, onClose }: {
  centre: MuleNetworkRow;
  allRows: MuleNetworkRow[];
  onRecentre: (accountId: string) => void;
  onClose: () => void;
}) {
  const [hover, setHover] = useState<{ p: MuleLinkPeer; x: number; y: number } | null>(null);
  const [history, setHistory] = useState<string[]>([]);

  // Cross-FIR peers first, then by transaction count. When the ring has
  // to be truncated the links that get dropped are the least
  // interesting ones, not an arbitrary slice.
  const peers = useMemo(() => {
    const seen = new Map<string, MuleLinkPeer>();
    for (const p of centre.peers) {
      const prev = seen.get(p.account_id);
      // An account can appear twice — paid AND received. Keep the
      // larger leg so the ring has one node per account, and mark it
      // two-way in the tooltip rather than drawing overlapping nodes.
      if (!prev || p.txns > prev.txns) seen.set(p.account_id, p);
    }
    return [...seen.values()].sort(
      (a, b) => Number(b.cross_fir) - Number(a.cross_fir) || b.txns - a.txns,
    );
  }, [centre]);

  const shown = peers.slice(0, MAX_RING);
  const hidden = peers.length - shown.length;
  const rowById = useMemo(
    () => new Map(allRows.map((r) => [r.account_id, r])), [allRows]);

  const maxTxns = Math.max(1, ...shown.map((p) => p.txns));
  // Radius grows with the count so a dense ring does not overlap, but
  // is capped to stay inside the viewport.
  const R = Math.min(250, 120 + shown.length * 3.2);

  const nodes = shown.map((p, i) => {
    const angle = (i / shown.length) * Math.PI * 2 - Math.PI / 2;
    return {
      p,
      x: CX + R * Math.cos(angle),
      y: CY + R * Math.sin(angle),
      r: 7 + Math.min(9, (rowById.get(p.account_id)?.connected ?? 1) * 0.6),
    };
  });

  function recentre(id: string) {
    if (!rowById.has(id)) return;
    setHistory((h) => [...h, centre.account_id]);
    onRecentre(id);
  }
  function back() {
    setHistory((h) => {
      const prev = h[h.length - 1];
      if (prev) onRecentre(prev);
      return h.slice(0, -1);
    });
  }

  return (
    <div className="rounded-2xl overflow-hidden"
      style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)',
               boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}>
      <div className="px-5 py-3 flex items-center justify-between gap-3 flex-wrap"
        style={{ borderBottom: '3px solid var(--ksp-yellow)' }}>
        <div>
          <h3 className="text-sm font-bold flex items-center gap-1.5" style={{ color: C_NAVY }}>
            <Waypoints className="w-4 h-4" />
            {short(centre.account_holder_name, 40)} — {peers.length} linked account
            {peers.length === 1 ? '' : 's'}
          </h3>
          <p className="text-xs opacity-60 mt-0.5">
            FIR {centre.fir_no || '—'} · {centre.ps_name || '—'} ·{' '}
            <span style={{ color: C_RED }}>red = different FIR</span>, navy = same FIR.
            Arrow shows which way the money went; line thickness is transaction
            count, not amount.
            {hidden > 0 && (
              <> <b style={{ color: C_RED }}> {hidden} further link
                {hidden === 1 ? '' : 's'} not drawn</b> — the ring is capped at{' '}
                {MAX_RING} to stay readable; all of them are in the table.</>
            )}
          </p>
        </div>
        <div className="flex gap-2">
          {history.length > 0 && (
            <button type="button" onClick={back}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-semibold"
              style={{ background: '#fff', color: C_NAVY, border: `1px solid ${C_NAVY}` }}>
              <ArrowLeft className="w-4 h-4" /> Back
            </button>
          )}
          {/* The only way back to the list, so it is a primary button
              and it says where it goes rather than just "Close". */}
          <button type="button" onClick={onClose}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-semibold"
            style={{ background: C_NAVY, color: '#fff' }}>
            <List className="w-4 h-4" /> Back to list
          </button>
        </div>
      </div>

      <div className="overflow-x-auto" style={{ background: '#fbfcfe' }}>
        <svg width={W} height={H} role="img"
          aria-label={`Network diagram for ${centre.account_holder_name ?? 'account'}`}>
          <defs>
            <marker id="arrow-out" viewBox="0 0 10 10" refX="9" refY="5"
              markerWidth="5" markerHeight="5" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill={C_RED} />
            </marker>
            <marker id="arrow-in" viewBox="0 0 10 10" refX="9" refY="5"
              markerWidth="5" markerHeight="5" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill={C_GREEN} />
            </marker>
          </defs>

          {/* Edges first so nodes sit on top of them. */}
          {nodes.map(({ p, x, y }) => {
            const out = p.direction === 'out';
            // Trim the line to the node edge so the arrowhead lands on
            // the circle rather than under it.
            const dx = x - CX, dy = y - CY;
            const len = Math.hypot(dx, dy) || 1;
            const pad = 26;
            const x1 = CX + (dx / len) * 30, y1 = CY + (dy / len) * 30;
            const x2 = x - (dx / len) * pad, y2 = y - (dy / len) * pad;
            return (
              <line key={`e-${p.account_id}`}
                x1={out ? x1 : x2} y1={out ? y1 : y2}
                x2={out ? x2 : x1} y2={out ? y2 : y1}
                stroke={out ? C_RED : C_GREEN}
                strokeOpacity={0.45}
                strokeWidth={1 + (p.txns / maxTxns) * 4}
                markerEnd={out ? 'url(#arrow-out)' : 'url(#arrow-in)'} />
            );
          })}

          {/* Centre */}
          <circle cx={CX} cy={CY} r={26} fill={C_NAVY} />
          <text x={CX} y={CY + 4} textAnchor="middle" fill="var(--ksp-yellow)"
            fontSize="11" fontWeight="700">
            {centre.connected}
          </text>
          <text x={CX} y={CY + 46} textAnchor="middle" fill={C_NAVY}
            fontSize="11" fontWeight="700">
            {short(centre.account_holder_name, 26)}
          </text>

          {/* Neighbours */}
          {nodes.map(({ p, x, y, r }) => {
            const known = rowById.has(p.account_id);
            return (
              <g key={`n-${p.account_id}`}
                style={{ cursor: known ? 'pointer' : 'default' }}
                onClick={() => recentre(p.account_id)}
                onMouseMove={(e) => setHover({ p, x: e.clientX, y: e.clientY })}
                onMouseLeave={() => setHover(null)}>
                <circle cx={x} cy={y} r={r}
                  fill={p.cross_fir ? C_RED : C_NAVY}
                  fillOpacity={known ? 1 : 0.45}
                  stroke="#fff" strokeWidth={2} />
                <text x={x} y={y - r - 5} textAnchor="middle"
                  fontSize="9.5" fill={C_NAVY} fontWeight="600">
                  {short(p.account_holder_name, 16)}
                </text>
                <text x={x} y={y + r + 11} textAnchor="middle"
                  fontSize="8.5" fill="#6b7280">
                  {p.fir_no || '—'}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Fixed-position tooltip: an absolutely-positioned one gets
          clipped by the horizontal scroll container above. */}
      {hover && (
        <div className="fixed z-50 rounded-lg px-3 py-2 text-xs pointer-events-none"
          style={{ left: hover.x + 14, top: hover.y + 14, background: '#fff',
                   border: `1px solid ${C_NAVY}`, boxShadow: '0 4px 14px rgba(0,0,0,0.18)',
                   maxWidth: 300 }}>
          <p className="font-bold" style={{ color: C_NAVY }}>
            {hover.p.account_holder_name || '—'}
          </p>
          <p className="font-mono text-[11px]">{hover.p.account_no || '—'}</p>
          <p className="opacity-70">{hover.p.bank_name || '—'}</p>
          <p className="mt-1">
            FIR {hover.p.fir_no || '—'}
            {hover.p.cross_fir && (
              <span className="ml-1 font-bold" style={{ color: C_RED }}>· different FIR</span>
            )}
          </p>
          <p className="opacity-70">{hover.p.ps_name || '—'}</p>
          <p className="mt-1 font-semibold"
            style={{ color: hover.p.direction === 'out' ? C_RED : C_GREEN }}>
            {hover.p.direction === 'out' ? 'received from centre' : 'paid to centre'}
            {' · '}{hover.p.txns.toLocaleString('en-IN')} txn
            {' · '}{rupeesShort(hover.p.amount)}
          </p>
          {!rowById.has(hover.p.account_id) && (
            <p className="mt-1 italic opacity-60">
              Not expandable — this account has no cross-FIR links of its own,
              or is outside the current filters.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
