/** Mule Network -> whole-network view.
 *
 *  Every mule-to-mule transfer at once: nodes are the ACCOUNT HOLDERS,
 *  edges are transfers, arrows point from payer to payee.
 *
 *  NODES ARE PARTIES, NOT RAILS.
 *  A payment aggregator is a mode of transfer, not a person, and putting
 *  one on the canvas invents connections that do not exist. "Google
 *  India Digital Services" is tagged Mule in all_accounts and carries 80
 *  links; PayU carries 40. Left in, those two alone weld unrelated rings
 *  into one blob and an officer reads a conspiracy off a payments
 *  gateway. They are excluded here -- see RAILS.
 *
 *  Companies are NOT excluded. A shell company receiving proceeds is a
 *  party to the transfer and usually the most interesting node on the
 *  screen; only the pipes come out.
 *
 *  COLOUR IS LAYER, NOT STATUS.
 *  Layer is money-trail depth: 1 is the account the victim paid, and
 *  each step up is another hop away from the crime. Colouring by it
 *  turns the picture into a direction of travel -- money enters at the
 *  dark end and leaves at the pale one -- which is the question an
 *  investigator actually has. Accounts with no layer recorded are grey
 *  and stay visible; a missing layer is a gap in the data, not a
 *  reason to hide an account.
 *
 *  TWO LAYOUTS, NOT ONE.
 *  The network is ~338 disconnected components: one of 259 nodes, one of
 *  74, and a long tail of which 226 are a single pair. A single force
 *  simulation over all 1,313 nodes is both slow (O(n^2) per iteration)
 *  and unreadable -- everything repels everything, so the rings smear
 *  into a disc. The master view therefore lays out each ring on its own
 *  and PACKS the rings into a grid, largest first. Each cluster keeps
 *  its shape, and the eye can move between rings instead of through a
 *  cloud.
 *
 *  WHY THE LAYOUT IS SEEDED
 *  A force simulation from a random start draws a different picture
 *  every time. Fine for exploring, wrong for evidence: a diagram in a
 *  case file has to be the same diagram when somebody opens it again.
 *  Positions are seeded from the account id, so a ring always lays out
 *  identically.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Maximize2, Minimize2, X, Waypoints, ZoomIn, ZoomOut, Crosshair,
} from 'lucide-react';

import { formatINR, formatNumber } from '../../lib/utils/format';
import type { MuleNetworkRow } from '../../types';

const C_NAVY = '#0b2c4a';
const C_RED = '#8b1919';
const C_GREY = '#8a94a0';

/** Layer palette — a fixed, named code, not a ramp.
 *
 *  A dark-to-pale ramp was tried first and reads well on large shapes,
 *  but these circles are 8-20px and adjacent ramp steps are almost
 *  indistinguishable at that size. Distinct hues with names an officer
 *  can say out loud ("the blue ones are layer 2") survive both a small
 *  circle and a printed page.
 *
 *  Order is fixed so the code means the same thing on every screen and
 *  in every exported diagram. Do not reorder to "improve" the palette:
 *  a case file drawn last month must still read the same way. */
const LAYER_CODE: { layer: number; name: string; fill: string }[] = [
  { layer: 1, name: 'Red',    fill: '#d81f26' },
  { layer: 2, name: 'Blue',   fill: '#1565c0' },
  { layer: 3, name: 'Black',  fill: '#1a1a1a' },
  { layer: 4, name: 'Yellow', fill: '#f2c200' },
  { layer: 5, name: 'Green',  fill: '#0a8f3c' },
  { layer: 6, name: 'Purple', fill: '#7b1fa2' },
  { layer: 7, name: 'Orange', fill: '#ef6c00' },
  { layer: 8, name: 'Cyan',   fill: '#00acc1' },
  { layer: 9, name: 'Pink',   fill: '#e91e8c' },
];
const LAYER_UNKNOWN = { name: 'Grey — not recorded', fill: '#9aa5b1' };

function layerColour(layer: number | null | undefined): string {
  if (layer === null || layer === undefined || layer < 1) return LAYER_UNKNOWN.fill;
  const e = LAYER_CODE[Math.min(layer, LAYER_CODE.length) - 1];
  return e ? e.fill : LAYER_UNKNOWN.fill;
}

function layerName(layer: number | null | undefined): string {
  if (layer === null || layer === undefined || layer < 1) return LAYER_UNKNOWN.name;
  const e = LAYER_CODE[Math.min(layer, LAYER_CODE.length) - 1];
  return e ? e.name : LAYER_UNKNOWN.name;
}

/** Payment rails, aggregators and telcos: a MODE of transfer, never a
 *  party. Deliberately narrow — ordinary companies stay in, because a
 *  shell company receiving proceeds IS a party. */
const RAILS = /\b(google|payu|razorpay|phonepe|paytm|billdesk|cashfree|ccavenue|npci|nsdl|bbps|amazon\s*pay|bharatpe|mobikwik|worldline|pine\s*labs)\b/i;

interface GraphNode {
  id: string; label: string;
  fir: string | null; ps: string | null; bank: string | null;
  layer: number | null;
  degree: number; crossFir: number;
  x: number; y: number;
  /** True when this account is NOT in the filtered result set — a peer
   *  reached from one that is.
   *
   *  Under a state filter the server returns only accounts in that
   *  state, but their counterparties are wherever they are. Drawing
   *  only the returned accounts severed almost every edge: of 389 links
   *  touching a Karnataka account, just 30 have BOTH ends in Karnataka.
   *  71 of 111 Karnataka accounts had no in-state peer at all, became
   *  isolated nodes, and were then dropped from the master view along
   *  with every other ring of two or fewer. Selecting a state showed
   *  almost nothing.
   *
   *  A state filter says WHICH ACCOUNTS I AM INVESTIGATING. It cannot
   *  mean "pretend the money stopped at the border" — for mule networks
   *  the out-of-state hop is usually the whole point. */
  outside: boolean;
}
interface GraphEdge {
  from: string; to: string; txns: number; amount: number; crossFir: boolean;
}

/** Deterministic [0,1) from a string — the seed for initial placement. */
function hash01(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return ((h >>> 0) % 100000) / 100000;
}

function components(nodes: string[], edges: GraphEdge[]): string[][] {
  const par = new Map<string, string>();
  const find = (x: string): string => {
    if (!par.has(x)) par.set(x, x);
    let r = x;
    while (par.get(r) !== r) r = par.get(r)!;
    while (par.get(x) !== r) { const n = par.get(x)!; par.set(x, r); x = n; }
    return r;
  };
  nodes.forEach(find);
  edges.forEach((e) => { const a = find(e.from), b = find(e.to); if (a !== b) par.set(a, b); });
  const out = new Map<string, string[]>();
  nodes.forEach((n) => {
    const r = find(n);
    if (!out.has(r)) out.set(r, []);
    out.get(r)!.push(n);
  });
  return [...out.values()].sort((a, b) => b.length - a.length);
}

/** Force layout inside a w×h box, origin at (0,0). Seeded, finite,
 *  synchronous — it runs once and stops. */
function layout(nodes: GraphNode[], edges: GraphEdge[], w: number, h: number) {
  const n = nodes.length;
  if (n === 0) return;
  if (n === 1) { nodes[0].x = w / 2; nodes[0].y = h / 2; return; }
  if (n === 2) {
    nodes[0].x = w * 0.3; nodes[0].y = h / 2;
    nodes[1].x = w * 0.7; nodes[1].y = h / 2;
    return;
  }
  const idx = new Map(nodes.map((d, i) => [d.id, i]));
  const cx = w / 2, cy = h / 2;
  nodes.forEach((d, i) => {
    const a = hash01(d.id) * Math.PI * 2;
    const r = Math.min(w, h) * (0.18 + 0.26 * hash01(d.id + 'r'));
    d.x = cx + Math.cos(a) * r + (i % 7) * 0.4;
    d.y = cy + Math.sin(a) * r + (i % 5) * 0.4;
  });

  const k = Math.sqrt((w * h) / n) * 0.55;
  // Iterations fall as the ring grows: the O(n^2) inner loop is what
  // costs, and big rings converge to a readable shape sooner because
  // there is more structure pinning them.
  const ITER = n > 200 ? 160 : n > 60 ? 240 : 320;
  const dx = new Float64Array(n), dy = new Float64Array(n);

  for (let it = 0; it < ITER; it++) {
    dx.fill(0); dy.fill(0);
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let ax = nodes[i].x - nodes[j].x, ay = nodes[i].y - nodes[j].y;
        let d2 = ax * ax + ay * ay;
        if (d2 < 0.01) { ax = (i - j) * 0.01 + 0.01; ay = 0.01; d2 = ax * ax + ay * ay; }
        const f = (k * k) / d2;
        const fx = ax * f, fy = ay * f;
        dx[i] += fx; dy[i] += fy; dx[j] -= fx; dy[j] -= fy;
      }
    }
    for (const e of edges) {
      const i = idx.get(e.from), j = idx.get(e.to);
      if (i === undefined || j === undefined) continue;
      const ax = nodes[i].x - nodes[j].x, ay = nodes[i].y - nodes[j].y;
      const d = Math.sqrt(ax * ax + ay * ay) || 0.01;
      const f = d / k;
      const fx = ax * f, fy = ay * f;
      dx[i] -= fx; dy[i] -= fy; dx[j] += fx; dy[j] += fy;
    }
    const t = k * (1 - it / ITER) * 0.9 + 0.4;
    for (let i = 0; i < n; i++) {
      const d = Math.sqrt(dx[i] * dx[i] + dy[i] * dy[i]) || 1;
      nodes[i].x += (dx[i] / d) * Math.min(d, t);
      nodes[i].y += (dy[i] / d) * Math.min(d, t);
      nodes[i].x += (cx - nodes[i].x) * 0.008;
      nodes[i].y += (cy - nodes[i].y) * 0.008;
      nodes[i].x = Math.max(18, Math.min(w - 18, nodes[i].x));
      nodes[i].y = Math.max(18, Math.min(h - 18, nodes[i].y));
    }
  }
}

/** Node radius in SCREEN pixels, before the zoom transform is undone.
 *
 *  Deliberately small. These rings pack 30-260 nodes into a cell a few
 *  hundred pixels wide, and a radius that reads well on a 6-node ring
 *  turns a 60-node ring into a solid mass of overlapping discs. The
 *  range below keeps the smallest node a visible dot and the biggest
 *  hub about three times its area -- enough to rank hubs by eye without
 *  letting them swallow their neighbours. */
const R_MIN = 2.5;
const R_SPAN = 5;

/** Everything drawn is divided by the zoom factor.
 *
 *  The scene transform scales POSITIONS, which is the point of zooming:
 *  crowded nodes move apart. If it scaled the ink as well, the circles
 *  would grow at exactly the rate the gaps did and a crowded ring would
 *  look identically crowded at every zoom level -- magnified, but no
 *  more readable. Dividing radii and stroke widths by the zoom keeps
 *  every mark the same size on screen, so zooming in genuinely
 *  separates the picture. */
function nodeRadius(degree: number, maxDeg: number, zoom: number): number {
  return (R_MIN + R_SPAN * Math.sqrt(degree / maxDeg)) / zoom;
}

export function MuleNetworkFull({ rows, onOpenAccount }: {
  rows: MuleNetworkRow[];
  onOpenAccount: (accountId: string) => void;
}) {
  // 'all' — the master view — NOT ring 0.
  //
  // It defaulted to the first ring, so opening this screen showed one
  // arbitrary cluster out of hundreds and looked like the whole network.
  // On a case with one big ring and a tail of pairs, the pair won: an
  // officer tracing an FIR landed on "2 accounts, 1 transfer" and
  // reasonably concluded that was the case's network.
  //
  // Master first, then narrow to a ring by choice. A view that shows
  // everything is honest when it is wrong; a view that silently shows
  // 1/300th of the data is not.
  const [ring, setRing] = useState<string>('all');
  const [full, setFull] = useState(false);
  const [showPairs, setShowPairs] = useState(false);
  const [hover, setHover] = useState<GraphNode | null>(null);
  const [hoverEdge, setHoverEdge] = useState<GraphEdge | null>(null);
  // Viewport transform for zoom/pan. Kept as scale + translate rather
  // than mutating the layout, so zooming never reflows the diagram —
  // the picture stays the same picture, just nearer.
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number; px: number; py: number } | null>(null);

  const { nodes: allNodes, edges: allEdges, railsDropped, outsideCount } = useMemo(() => {
    const keep = rows.filter((r) => !RAILS.test(r.account_holder_name || ''));
    const byId = new Map(keep.map((r) => [r.account_id, r]));
    const nodes: GraphNode[] = keep.map((r) => ({
      id: r.account_id,
      label: r.account_holder_name || r.account_no || '—',
      fir: r.fir_no, ps: r.ps_name, bank: r.bank_name, layer: r.layer,
      degree: r.connected, crossFir: r.cross_fir, x: 0, y: 0,
      outside: false,
    }));

    // Peers that the filter excluded still get drawn, marked as
    // outside it. Everything needed is already in the payload -- the
    // server sends each peer's name, account number, bank, FIR and
    // station -- so this costs no extra request.
    //
    // Rails stay out at BOTH ends. A payment gateway is a mode of
    // transfer, not a party, and re-admitting it as a peer would weld
    // unrelated rings together through PayU exactly as it would have
    // as a row.
    const peerNode = new Map<string, GraphNode>();
    for (const r of keep) {
      for (const p of r.peers) {
        if (byId.has(p.account_id) || peerNode.has(p.account_id)) continue;
        if (RAILS.test(p.account_holder_name || '')) continue;
        peerNode.set(p.account_id, {
          id: p.account_id,
          label: p.account_holder_name || p.account_no || '—',
          fir: p.fir_no, ps: p.ps_name, bank: p.bank_name,
          // The peer payload carries no layer, and grey is already the
          // established meaning of "no layer recorded" on this canvas.
          layer: null,
          // Degree is not known for a node the server did not rank; it
          // is filled in below from the edges actually drawn, so the
          // size of a peer reflects what is on screen rather than a
          // number this view cannot see.
          degree: 0, crossFir: 0, x: 0, y: 0,
          outside: true,
        });
      }
    }
    for (const n of peerNode.values()) nodes.push(n);

    const drawable = new Set(nodes.map((n) => n.id));
    const byKey = new Map<string, GraphEdge>();
    for (const r of keep) {
      for (const p of r.peers) {
        if (!drawable.has(p.account_id)) continue;
        const out = (p.direction || '').toLowerCase().startsWith('out');
        const from = out ? r.account_id : p.account_id;
        const to = out ? p.account_id : r.account_id;
        const key = `${from}>${to}`;
        const prev = byKey.get(key);
        if (prev) {
          // Both ends reported this transfer -- once from the payer's
          // statement and once from the payee's. They should agree;
          // where they do not, one side's statement parsed only
          // partially, so the larger figure is the more complete one.
          // MAX, never sum: these are two readings of one transfer,
          // not two transfers.
          prev.txns = Math.max(prev.txns, p.txns);
          prev.amount = Math.max(prev.amount, p.amount || 0);
          prev.crossFir = prev.crossFir || p.cross_fir;
          continue;
        }
        byKey.set(key, {
          from, to, txns: p.txns, amount: p.amount || 0, crossFir: p.cross_fir,
        });
      }
    }
    const edges = [...byKey.values()];

    // Degree for the peers, counted from the edges actually drawn. A
    // node the server did not rank has no `connected` figure, and
    // leaving it at 0 would draw every out-of-filter account at the
    // minimum size regardless of how much of the picture it carries.
    const deg = new Map<string, number>();
    for (const e of edges) {
      deg.set(e.from, (deg.get(e.from) ?? 0) + 1);
      deg.set(e.to, (deg.get(e.to) ?? 0) + 1);
    }
    for (const n of nodes) if (n.outside) n.degree = deg.get(n.id) ?? 0;

    return {
      nodes, edges, railsDropped: rows.length - keep.length,
      outsideCount: nodes.filter((n) => n.outside).length,
    };
  }, [rows]);

  const rings = useMemo(() => {
    const comps = components(allNodes.map((n) => n.id), allEdges);
    return comps.map((ids) => {
      const set = new Set(ids);
      return { ids, size: ids.length, links: allEdges.filter((e) => set.has(e.from)).length };
    });
  }, [allNodes, allEdges]);

  const isMaster = ring === 'all';

  /** Laid-out nodes + the canvas they need.
   *
   *  Master view packs each ring into its own cell, largest first, so
   *  clusters keep their shape instead of smearing together. */
  const { laid, edges: shownEdges, W } = useMemo(() => {
    const nodeById = new Map(allNodes.map((n) => [n.id, n]));

    if (!isMaster) {
      const r = rings[Number(ring) || 0];
      const ids = new Set(r ? r.ids : []);
      const ns = allNodes.filter((n) => ids.has(n.id)).map((n) => ({ ...n }));
      const es = allEdges.filter((e) => ids.has(e.from) && ids.has(e.to));
      const w = full ? 1500 : 1040, h = full ? 820 : 600;
      layout(ns, es, w, h);
      return { laid: ns, edges: es, W: w, H: h };
    }

    const use = showPairs ? rings : rings.filter((r) => r.size > 2);
    // Cell size scales with ring size so a 259-node ring gets room and a
    // 3-node one does not waste a screen.
    const cells = use.map((r) => {
      const side = Math.max(150, Math.min(760, 58 * Math.sqrt(r.size)));
      return { r, w: side, h: side };
    });
    const MAXW = 2200;
    let cx = 0, cy = 0, rowH = 0;
    const out: GraphNode[] = [];
    const es: GraphEdge[] = [];
    for (const c of cells) {
      if (cx > 0 && cx + c.w > MAXW) { cx = 0; cy += rowH + 40; rowH = 0; }
      const ids = new Set(c.r.ids);
      const ns = c.r.ids.map((id) => ({ ...nodeById.get(id)! })).filter(Boolean);
      const ringEdges = allEdges.filter((e) => ids.has(e.from) && ids.has(e.to));
      layout(ns, ringEdges, c.w, c.h);
      ns.forEach((n) => { n.x += cx; n.y += cy; });
      out.push(...ns);
      es.push(...ringEdges);
      cx += c.w + 40;
      rowH = Math.max(rowH, c.h);
    }
    return { laid: out, edges: es, W: MAXW, H: cy + rowH + 40 };
  }, [ring, rings, allNodes, allEdges, showPairs, full, isMaster]);

  // Reset the viewport whenever the picture changes — leaving a zoom
  // from the previous ring applied to a new one is disorienting.
  useEffect(() => { setZoom(1); setPan({ x: 0, y: 0 }); }, [ring, showPairs, full]);

  const pos = useMemo(() => new Map(laid.map((n) => [n.id, n])), [laid]);
  const maxDeg = Math.max(1, ...laid.map((n) => n.degree));
  const layersSeen = useMemo(() => {
    const s = new Set<number | null>();
    laid.forEach((n) => s.add(n.layer ?? null));
    return [...s].sort((a, b) => (a ?? 99) - (b ?? 99));
  }, [laid]);

  const VW = full ? 1500 : 1040;
  const VH = full ? 780 : 560;

  // No wheel zoom on purpose. The canvas lives inside a scrolling page,
  // so a wheel bound to zoom swallows the scroll and traps the pointer
  // whenever it crosses the diagram. Zoom is the +/- buttons only.
  function onDown(e: React.MouseEvent) {
    drag.current = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y };
  }
  function onMove(e: React.MouseEvent) {
    if (!drag.current) return;
    setPan({
      x: drag.current.px + (e.clientX - drag.current.x),
      y: drag.current.py + (e.clientY - drag.current.y),
    });
  }
  const endDrag = () => { drag.current = null; };

  const body = (
    <div className="rounded-2xl overflow-hidden"
      style={{ background: '#fff', border: '1px solid rgba(11,44,74,0.12)' }}>
      <div className="px-4 py-3 flex items-center gap-3 flex-wrap"
        style={{ borderBottom: '3px solid var(--ksp-yellow)' }}>
        <h3 className="text-sm font-bold flex items-center gap-1.5" style={{ color: C_NAVY }}>
          <Waypoints className="w-4 h-4" /> Transfer network
        </h3>

        <select value={ring} onChange={(e) => setRing(e.target.value)}
          aria-label="Choose a ring"
          className="px-2 py-1 rounded-lg text-xs font-semibold bg-white"
          style={{ border: `2px solid ${C_NAVY}`, color: C_NAVY }}>
          <option value="all">
            Master — all {formatNumber(rings.filter((r) => r.size > 2).length)} rings
          </option>
          {rings.slice(0, 60).map((r, i) => (
            <option key={i} value={String(i)}>
              Ring {i + 1} — {r.size} accounts, {r.links} transfers
            </option>
          ))}
        </select>

        {isMaster && (
          <label className="text-[11px] flex items-center gap-1.5 font-semibold"
            style={{ color: C_NAVY }}>
            <input type="checkbox" checked={showPairs}
              onChange={(e) => setShowPairs(e.target.checked)} />
            include {formatNumber(rings.filter((r) => r.size === 2).length)} pairs
          </label>
        )}

        <div className="flex items-center gap-1 ml-auto">
          <button type="button" onClick={() => setZoom((z) => Math.min(6, z * 1.25))}
            title="Zoom in" className="p-1.5 rounded-lg"
            style={{ border: `1px solid ${C_NAVY}`, color: C_NAVY }}>
            <ZoomIn className="w-3.5 h-3.5" />
          </button>
          <button type="button" onClick={() => setZoom((z) => Math.max(0.15, z / 1.25))}
            title="Zoom out" className="p-1.5 rounded-lg"
            style={{ border: `1px solid ${C_NAVY}`, color: C_NAVY }}>
            <ZoomOut className="w-3.5 h-3.5" />
          </button>
          <button type="button" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}
            title="Reset view" className="p-1.5 rounded-lg"
            style={{ border: `1px solid ${C_NAVY}`, color: C_NAVY }}>
            <Crosshair className="w-3.5 h-3.5" />
          </button>
          <span className="text-[10px] tabular-nums opacity-60 w-10 text-right">
            {Math.round(zoom * 100)}%
          </span>
          <button type="button" onClick={() => setFull((v) => !v)}
            title={full ? 'Exit full screen' : 'Full screen'}
            className="p-1.5 rounded-lg ml-1"
            style={{ border: `1px solid ${C_NAVY}`, color: C_NAVY }}>
            {full ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      <div className="px-4 py-1.5 text-[11px] opacity-70" style={{ color: C_NAVY }}>
        {formatNumber(laid.length)} accounts · {formatNumber(shownEdges.length)} transfers
        {railsDropped > 0 && ` · ${railsDropped} payment rail${railsDropped === 1 ? '' : 's'} excluded`}
        {/* Say it plainly. An officer reading this diagram under a state
            filter needs to know that the hollow nodes are real accounts
            outside the filter, not artefacts -- and for Karnataka they
            are most of the picture. */}
        {outsideCount > 0 && (
          <> · <b>{formatNumber(outsideCount)}</b> outside the current
            filter, drawn hollow — their links are why the network is
            connected at all</>
        )}
        {' · '}drag to pan, +/- to zoom, hover a node for the name or a line for the amount, click to open
      </div>

      <div className="relative overflow-hidden"
        style={{ background: '#fbfcfd', height: VH, cursor: drag.current ? 'grabbing' : 'grab' }}
        onMouseDown={onDown} onMouseMove={onMove}
        onMouseUp={endDrag} onMouseLeave={endDrag}>
        <svg width={VW} height={VH} className="block mx-auto select-none">
          <defs>
            <marker id="mn-arrow" viewBox="0 0 10 10" refX="9" refY="5"
              markerWidth="5" markerHeight="5" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill={C_GREY} />
            </marker>
          </defs>
          {/* One transform for the whole scene: zoom and pan never touch
              the layout, so the diagram stays reproducible. */}
          <g transform={`translate(${pan.x},${pan.y}) scale(${zoom}) translate(${(VW - W * 1) / 2},${20})`}>
            {shownEdges.map((e, i) => {
              const a = pos.get(e.from), b = pos.get(e.to);
              if (!a || !b) return null;
              const r = nodeRadius(b.degree, maxDeg, zoom);
              const vx = b.x - a.x, vy = b.y - a.y;
              const len = Math.sqrt(vx * vx + vy * vy) || 1;
              // Gap between arrowhead and node also in screen pixels,
              // or the arrow detaches from its target as you zoom.
              const gap = r + 2 / zoom;
              const x2 = b.x - (vx / len) * gap;
              const y2 = b.y - (vy / len) * gap;
              const on = hoverEdge === e;
              return (
                <g key={i}>
                  {/* Invisible fat line carrying the hit test. The drawn
                      stroke is 0.5-3.5px, and 1px of hoverable target is
                      unusable with a mouse -- worse zoomed out, where
                      the whole ring shrinks. The hit line keeps a
                      constant grab width in scene units. */}
                  <line x1={a.x} y1={a.y} x2={x2} y2={y2}
                    stroke="transparent" strokeWidth={9 / zoom}
                    style={{ pointerEvents: 'stroke', cursor: 'pointer' }}
                    onMouseEnter={() => setHoverEdge(e)}
                    onMouseLeave={() => setHoverEdge((c) => (c === e ? null : c))} />
                  <line x1={a.x} y1={a.y} x2={x2} y2={y2}
                    pointerEvents="none"
                    stroke={on ? C_NAVY : e.crossFir ? C_RED : C_GREY}
                    strokeWidth={
                      (on ? 2.2
                        : Math.min(2.4, 0.4 + Math.log10(1 + e.txns) * 0.9))
                      / zoom
                    }
                    strokeOpacity={on ? 0.95 : e.crossFir ? 0.5 : 0.28}
                    markerEnd="url(#mn-arrow)" />
                </g>
              );
            })}
            {laid.map((n) => {
              const r = nodeRadius(n.degree, maxDeg, zoom);
              return (
                <g key={n.id}
                  onMouseEnter={() => setHover(n)} onMouseLeave={() => setHover(null)}
                  onClick={() => onOpenAccount(n.id)} style={{ cursor: 'pointer' }}>
                  {/* Cross-FIR is a HALO, not the outline colour. With
                      layer on the fill and layer 1 already red, a red
                      stroke would collide with it -- two encodings
                      fighting over the same pixels. */}
                  {n.crossFir > 0 && (
                    <circle cx={n.x} cy={n.y} r={r + 2.5 / zoom}
                      fill="none" stroke={C_RED} strokeWidth={1.3 / zoom}
                      strokeDasharray={`${3 / zoom} ${2 / zoom}`}
                      strokeOpacity={0.9} />
                  )}
                  {/* Dark outline on every node: #f2c200 on a white
                      canvas is invisible without one.

                      HOLLOW = OUTSIDE THE CURRENT FILTER. An account
                      reached from one that matched, but which does not
                      match itself -- almost always a different state.
                      Drawn, because severing it is what made a state
                      filter show 30 of 389 links; distinguished,
                      because an officer must be able to tell what the
                      filter actually selected. Fill, not colour, so it
                      does not compete with the layer code. */}
                  <circle cx={n.x} cy={n.y} r={r}
                    fill={n.outside ? '#ffffff' : layerColour(n.layer)}
                    fillOpacity={n.outside ? 1 : 0.95}
                    stroke={n.outside ? C_GREY : '#20303f'}
                    strokeWidth={(n.outside ? 1.6 : 0.8) / zoom}
                    strokeDasharray={n.outside ? `${2.5 / zoom} ${1.8 / zoom}` : undefined} />
                  {/* No labels on the canvas. Account holder names run
                      20-40 characters and overlap their neighbours at
                      any zoom that still shows a ring's shape, which
                      buries the structure the diagram exists to show.
                      The name is on hover and on click instead. */}
                </g>
              );
            })}
          </g>
        </svg>

        {hover && (
          <div className="absolute pointer-events-none rounded-lg px-3 py-2 text-[11px] left-3 bottom-3"
            style={{ background: C_NAVY, color: '#fff', maxWidth: 260, zIndex: 5 }}>
            <div className="font-bold">{hover.label}</div>
            <div className="opacity-80">{hover.bank || '—'}</div>
            <div className="opacity-80">FIR {hover.fir || '—'} · {hover.ps || '—'}</div>
            <div className="mt-1">
              Layer {hover.layer ?? '—'} ({layerName(hover.layer)}) · {hover.degree} connection
              {hover.degree === 1 ? '' : 's'}
              {hover.crossFir > 0 && ` · ${hover.crossFir} cross-FIR`}
            </div>
            {/* Said on the node itself, not only in the caption. An
                officer reading a hollow circle needs to know why it is
                hollow at the moment they are looking at it. */}
            {hover.outside && (
              <div className="mt-1" style={{ color: 'var(--ksp-yellow)' }}>
                Outside the current filter — shown because it is connected
                to one that is not. Its own links are not counted here.
              </div>
            )}
            <div className="opacity-60 mt-1">click to open this account</div>
          </div>
        )}

        {/* Edge card. Nodes render above edges so both cannot be hovered
            at once, but the node wins explicitly anyway. */}
        {!hover && hoverEdge && (
          <div className="absolute pointer-events-none rounded-lg px-3 py-2 text-[11px] left-3 bottom-3"
            style={{ background: C_NAVY, color: '#fff', maxWidth: 300, zIndex: 5 }}>
            <div className="font-bold">{pos.get(hoverEdge.from)?.label || '-'}</div>
            <div className="opacity-80">transferred to</div>
            <div className="font-bold">{pos.get(hoverEdge.to)?.label || '-'}</div>
            <div className="mt-1 font-bold" style={{ fontSize: 13 }}>
              {formatINR(hoverEdge.amount)}
            </div>
            <div className="opacity-80">
              across {formatNumber(hoverEdge.txns)} transaction
              {hoverEdge.txns === 1 ? '' : 's'}
              {hoverEdge.crossFir && ' \u00b7 links two FIRs'}
            </div>
            {/* Say where the figure stops being reliable: it is what the
                parsed statements record for this pair, so a transfer
                routed through an account whose statement never parsed
                is not in it. */}
            <div className="opacity-60 mt-1">
              total from the parsed statements for this pair
            </div>
          </div>
        )}
      </div>

      <div className="px-4 py-2 text-[11px] flex items-center gap-3 flex-wrap"
        style={{ borderTop: '1px solid rgba(11,44,74,0.08)', color: C_NAVY }}>
        <span className="font-bold uppercase tracking-wide opacity-60">Layer code</span>
        {layersSeen.map((l) => (
          <span key={String(l)} className="flex items-center gap-1 font-semibold">
            <span className="inline-block w-3 h-3 rounded-full"
              style={{ background: layerColour(l), border: '1px solid #20303f' }} />
            {l === null || l === undefined
              ? 'Not recorded'
              : `L${l} — ${layerName(l)}`}
          </span>
        ))}
        <span className="flex items-center gap-1 font-semibold">
          <span className="inline-block w-3 h-3 rounded-full"
            style={{ border: `1.5px dashed ${C_RED}` }} />
          reaches another FIR
        </span>
        <span className="opacity-60 ml-2">
          layer 1 = paid directly by the victim · circle size = connections ·
          arrow = direction of transfer
        </span>
      </div>
    </div>
  );

  if (!full) return body;
  return (
    <div className="fixed inset-0 z-50 p-3 overflow-auto" style={{ background: 'rgba(11,44,74,0.6)' }}>
      <div className="max-w-[1600px] mx-auto">
        <button type="button" onClick={() => setFull(false)}
          className="mb-2 inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-bold"
          style={{ background: '#fff', color: C_NAVY }}>
          <X className="w-3.5 h-3.5" /> Close full screen
        </button>
        {body}
      </div>
    </div>
  );
}
