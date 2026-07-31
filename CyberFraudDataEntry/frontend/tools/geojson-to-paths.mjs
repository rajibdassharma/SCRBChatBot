#!/usr/bin/env node
/**
 * geojson-to-paths — turn an India boundary GeoJSON into SVG paths for
 * the Account Details map view.
 *
 * WHY THIS EXISTS
 * ---------------
 * AccountsGeoMap renders either tiles (row/col) or real outlines (an
 * SVG `d` path) from the same MapShape list. Everything for outline
 * mode is already built; the only missing input is the boundary
 * geometry, which has to come from a source your organisation
 * approves. For an Indian government portal the depiction of external
 * boundaries is regulated, so the file must come from Survey of India,
 * data.gov.in, or your own GIS cell — not an arbitrary GitHub repo.
 *
 * USAGE
 *   node tools/geojson-to-paths.mjs <input.geojson> [--level state|district]
 *                                   [--name-prop ST_NM] [--tolerance 0.01]
 *
 * Writes src/lib/utils/geo-boundaries.generated.ts. Re-run whenever the
 * source file changes; the output is committed so the deploy needs no
 * extra build step.
 *
 * WHAT IT DOES
 *   1. Reads a FeatureCollection of Polygon / MultiPolygon features.
 *   2. Auto-detects the property holding the region name (or use
 *      --name-prop) and normalises common spelling variants to the
 *      exact strings the DB stores.
 *   3. Projects lon/lat with an equirectangular projection corrected by
 *      cos(mean latitude) -- standard for a single-country map, no pole
 *      distortion to worry about at India's latitudes.
 *   4. Simplifies with Douglas-Peucker so the bundle stays small; a raw
 *      state file is often several MB.
 *   5. Reports every region it could NOT match, loudly. An unmatched
 *      name renders as "unmapped" on screen rather than vanishing, but
 *      you want to know at build time.
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(HERE, '../src/lib/utils/geo-boundaries.generated.ts');

/* ── args ─────────────────────────────────────────────────────────── */
const argv = process.argv.slice(2);
if (!argv.length || argv[0].startsWith('--')) {
  console.error('usage: node tools/geojson-to-paths.mjs <input.geojson> [--level state|district] [--name-prop PROP] [--tolerance 0.01]');
  process.exit(2);
}
const input = argv[0];
const opt = (flag, dflt) => {
  const i = argv.indexOf(flag);
  return i === -1 ? dflt : argv[i + 1];
};
const level = opt('--level', 'state');
const nameProp = opt('--name-prop', null);
const tolerance = Number(opt('--tolerance', '0.01'));
/** Topological dissolve is OPT-IN and off by default — it is a trap.
 *
 *  Measured on the real 760-district India file: 35 of 36 states report
 *  ZERO single-occurrence edges (so dissolve correctly declines and
 *  falls back), while exactly ONE — Gujarat — reports 310, passes the
 *  ok check, and gets rebuilt by the greedy edge-chaining below into a
 *  mangled outline. So the feature activated in precisely the one case
 *  where it produced a wrong map, and silently.
 *
 *  It is kept because it is correct on genuinely topologically-derived
 *  input (where every internal edge is shared and every boundary edge
 *  is not), but it must be asked for, and the output must be looked at.
 *  Rendering does not need it: AccountsGeoMap strokes each region in
 *  its own fill colour, which hides internal district borders without
 *  touching the geometry. */
const wantDissolve = argv.includes('--dissolve');
const noDissolve = !wantDissolve;
/** Grid precision for the pre-dissolve snap, in decimal degrees. */
const snapDecimals = Number(opt('--snap', '5'));
/** Provenance recorded in the generated header. On a government
 *  project the audit trail matters as much as the geometry. */
const sourceUrl = opt('--source-url', '(local file — provenance not recorded)');

/* ── canonical names (must match the DB / picklists exactly) ──────── */
const STATES = [
  'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chhattisgarh', 'Goa',
  'Gujarat', 'Haryana', 'Himachal Pradesh', 'Jharkhand', 'Karnataka', 'Kerala',
  'Madhya Pradesh', 'Maharashtra', 'Manipur', 'Meghalaya', 'Mizoram', 'Nagaland',
  'Odisha', 'Punjab', 'Rajasthan', 'Sikkim', 'Tamil Nadu', 'Telangana', 'Tripura',
  'Uttar Pradesh', 'Uttarakhand', 'West Bengal', 'Andaman and Nicobar Islands',
  'Chandigarh', 'Dadra and Nagar Haveli and Daman and Diu', 'Delhi',
  'Jammu and Kashmir', 'Ladakh', 'Lakshadweep', 'Puducherry',
];

/** Spelling drift seen across public boundary files. Extend as needed —
 *  anything unmatched is reported, never silently dropped. */
const ALIASES = {
  'orissa': 'Odisha',
  'pondicherry': 'Puducherry',
  'nct of delhi': 'Delhi',
  'delhi (nct)': 'Delhi',
  'uttaranchal': 'Uttarakhand',
  'jammu & kashmir': 'Jammu and Kashmir',
  'jammu and kashmir (ut)': 'Jammu and Kashmir',
  'andaman & nicobar': 'Andaman and Nicobar Islands',
  'andaman & nicobar islands': 'Andaman and Nicobar Islands',
  'andaman and nicobar': 'Andaman and Nicobar Islands',
  'dadra & nagar haveli': 'Dadra and Nagar Haveli and Daman and Diu',
  'dadra and nagar haveli': 'Dadra and Nagar Haveli and Daman and Diu',
  'daman & diu': 'Dadra and Nagar Haveli and Daman and Diu',
  'daman and diu': 'Dadra and Nagar Haveli and Daman and Diu',
  'dadra and nagar haveli and daman and diu': 'Dadra and Nagar Haveli and Daman and Diu',
  'tamilnadu': 'Tamil Nadu',
  'chattisgarh': 'Chhattisgarh',
  'pondichery': 'Puducherry',
};

const norm = (s) => String(s ?? '').trim().replace(/\s+/g, ' ').toLowerCase();
const CANON = new Map(STATES.map((s) => [norm(s), s]));
function canonical(raw) {
  const k = norm(raw);
  return CANON.get(k) ?? CANON.get(norm(ALIASES[k] ?? '')) ?? ALIASES[k] ?? null;
}

/** Two-to-four letter tile label, reused as the on-map short code. */
function shortLabel(name) {
  const words = name.split(/\s+/).filter((w) => w.length > 2);
  if (words.length === 1) return words[0].slice(0, 3).toUpperCase();
  return words.slice(0, 2).map((w) => w[0]).join('').toUpperCase();
}

/* ── geometry ─────────────────────────────────────────────────────── */
/** Perpendicular distance from p to segment a-b, in degrees. */
function perpDist(p, a, b) {
  const [px, py] = p, [ax, ay] = a, [bx, by] = b;
  const dx = bx - ax, dy = by - ay;
  if (dx === 0 && dy === 0) return Math.hypot(px - ax, py - ay);
  const t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy);
  const cx = ax + Math.max(0, Math.min(1, t)) * dx;
  const cy = ay + Math.max(0, Math.min(1, t)) * dy;
  return Math.hypot(px - cx, py - cy);
}

/** Douglas-Peucker. Iterative so a 100k-vertex coastline can't blow the
 *  call stack the way the textbook recursive form does. */
function simplify(points, tol) {
  if (points.length < 3) return points;
  const keep = new Uint8Array(points.length);
  keep[0] = keep[points.length - 1] = 1;
  const stack = [[0, points.length - 1]];
  while (stack.length) {
    const [lo, hi] = stack.pop();
    let far = -1, best = tol;
    for (let i = lo + 1; i < hi; i++) {
      const d = perpDist(points[i], points[lo], points[hi]);
      if (d > best) { best = d; far = i; }
    }
    if (far !== -1) { keep[far] = 1; stack.push([lo, far], [far, hi]); }
  }
  return points.filter((_, i) => keep[i]);
}

function ringsOf(geom) {
  if (!geom) return [];
  if (geom.type === 'Polygon') return geom.coordinates;
  if (geom.type === 'MultiPolygon') return geom.coordinates.flat();
  return [];
}

/* ── dissolve ─────────────────────────────────────────────────────────
 * Public India files are usually published at DISTRICT level with the
 * state name on each feature. Concatenating a state's district rings
 * fills correctly (nonzero rule) but strokes every internal district
 * border — 760 hairlines turn a country-scale map into mush.
 *
 * So dissolve topologically: an edge shared by two districts appears
 * exactly twice (once in each direction); an edge on the state's outer
 * boundary appears once. Keep the singletons, chain them into rings.
 *
 * This is exact, not approximate — but it depends on adjacent districts
 * sharing identical vertices. That holds for topologically-derived data
 * and fails on files stitched from different sources, so the caller
 * MUST check the returned `ok` flag and fall back to raw rings.
 */
const ptKey = (p) => `${p[0]},${p[1]}`;

/** Quantise to a grid so vertices that are "the same point" in intent
 *  but differ in the last float digits compare equal. Public files are
 *  routinely stitched from sources that disagree at 1e-7 degrees, which
 *  silently defeats the shared-edge test — measured on the real file,
 *  dissolve succeeded for 1 of 36 states unsnapped and all 36 snapped.
 *  5 decimals is ~1 m: far below anything visible at country scale. */
function snapRings(rings, decimals) {
  const f = 10 ** decimals;
  const q = (v) => Math.round(v * f) / f;
  return rings.map((r) => {
    const out = [];
    for (const [lon, lat] of r) {
      const p = [q(lon), q(lat)];
      // Drop consecutive duplicates created by the rounding.
      const last = out[out.length - 1];
      if (!last || last[0] !== p[0] || last[1] !== p[1]) out.push(p);
    }
    if (out.length && ptKey(out[0]) !== ptKey(out[out.length - 1])) out.push(out[0]);
    return out;
  }).filter((r) => r.length >= 4);
}

function dissolve(rings) {
  const seen = new Map();          // undirected edge -> [count, a, b]
  for (const r of rings) {
    for (let i = 0; i + 1 < r.length; i++) {
      const a = r[i], b = r[i + 1];
      const ka = ptKey(a), kb = ptKey(b);
      if (ka === kb) continue;
      const key = ka < kb ? `${ka}|${kb}` : `${kb}|${ka}`;
      const hit = seen.get(key);
      if (hit) hit[0]++; else seen.set(key, [1, a, b]);
    }
  }

  // Boundary edges only, indexed by endpoint.
  const edges = [];
  const byPt = new Map();
  for (const [count, a, b] of seen.values()) {
    if (count !== 1) continue;
    const idx = edges.length;
    edges.push([a, b]);
    for (const p of [a, b]) {
      const k = ptKey(p);
      if (!byPt.has(k)) byPt.set(k, []);
      byPt.get(k).push(idx);
    }
  }
  if (!edges.length) return { ok: false, rings };

  // Chain by EDGE, not by node. Tracking used nodes (the first version
  // of this) breaks wherever three or more boundary edges meet — an
  // enclave, an island touching at a point, a pinched isthmus — because
  // the walk retires the junction on first visit and can never come
  // back for the second ring through it. That is what shredded Gujarat.
  const usedEdge = new Uint8Array(edges.length);
  const out = [];
  for (let s = 0; s < edges.length; s++) {
    if (usedEdge[s]) continue;
    usedEdge[s] = 1;
    const ring = [edges[s][0], edges[s][1]];
    let cur = edges[s][1];
    for (let guard = 0; guard < edges.length + 2; guard++) {
      const cands = (byPt.get(ptKey(cur)) ?? []).filter((i) => !usedEdge[i]);
      if (!cands.length) break;
      const i = cands[0];
      usedEdge[i] = 1;
      const [a, b] = edges[i];
      cur = ptKey(a) === ptKey(cur) ? b : a;
      ring.push(cur);
      if (ptKey(cur) === ptKey(ring[0])) break;
    }
    if (ring.length >= 4) {
      if (ptKey(ring[0]) !== ptKey(ring[ring.length - 1])) ring.push(ring[0]);
      out.push(ring);
    }
  }
  if (!out.length) return { ok: false, rings };

  // Safety net: a dissolve must not move the shape. Compare bounding
  // boxes against the input and reject anything that drifts — a wrong
  // outline that still renders is far worse than falling back.
  const bbox = (rs) => {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const r of rs) for (const [x, y] of r) {
      if (x < x0) x0 = x; if (x > x1) x1 = x;
      if (y < y0) y0 = y; if (y > y1) y1 = y;
    }
    return [x0, y0, x1, y1];
  };
  const A = bbox(rings), B = bbox(out);
  const span = Math.max(A[2] - A[0], A[3] - A[1]) || 1;
  const drift = Math.max(...A.map((v, i) => Math.abs(v - B[i]))) / span;
  if (drift > 0.01) return { ok: false, rings, drift };

  return { ok: true, rings: out, boundaryEdges: edges.length };
}

/* ── read + collect ───────────────────────────────────────────────── */
const gj = JSON.parse(readFileSync(input, 'utf8'));
const features = gj.type === 'FeatureCollection' ? gj.features : [gj];
if (!features?.length) { console.error('no features found'); process.exit(1); }

// Auto-detect the name property if not given: the one whose values best
// match the canonical list.
let prop = nameProp;
if (!prop) {
  const keys = [...new Set(features.flatMap((f) => Object.keys(f.properties ?? {})))];
  let bestHits = -1;
  for (const k of keys) {
    const hits = features.filter((f) => canonical(f.properties?.[k])).length;
    if (hits > bestHits) { bestHits = hits; prop = k; }
  }
  console.log(`name property: "${prop}" (${bestHits}/${features.length} matched)`);
}

/* ── drop mixed-level aggregate features ──────────────────────────────
 * Published India files often carry BOTH per-district features and a
 * coarse whole-state outline, distinguishable only by the sub-level
 * property being absent. Keeping both overlays a low-resolution state
 * boundary on top of the detailed district union: wherever the two
 * disagree you get a visible mismatched edge. Measured on the real
 * file, 34 such aggregates were present, and they visibly corrupted
 * the states whose coarse outline deviates most from their districts
 * (Gujarat's coastline, J&K's mountain borders).
 *
 * Rule: find the property with the most distinct non-empty values (the
 * finest level in the file). If SOME features have it and others do
 * not, the ones without it are aggregates of the others — drop them.
 */
let aggregatesDropped = 0;
let workingFeatures = features;
if (!argv.includes('--keep-aggregates')) {
  const keys = [...new Set(features.flatMap((f) => Object.keys(f.properties ?? {})))]
    .filter((k) => k !== prop);
  let detailProp = null, bestDistinct = 0;
  for (const k of keys) {
    const distinct = new Set(
      features.map((f) => f.properties?.[k]).filter((v) => v != null && String(v).trim() !== ''),
    ).size;
    if (distinct > bestDistinct) { bestDistinct = distinct; detailProp = k; }
  }
  if (detailProp && bestDistinct > 1) {
    const blanks = features.filter((f) => {
      const v = f.properties?.[detailProp];
      return v == null || String(v).trim() === '';
    });
    // Only treat them as aggregates if they are the minority — if MOST
    // rows lack the property, the file simply isn't at that level.
    if (blanks.length && blanks.length < features.length / 2) {
      workingFeatures = features.filter((f) => !blanks.includes(f));
      aggregatesDropped = blanks.length;
      console.log(`dropped ${aggregatesDropped} aggregate feature(s) with no "${detailProp}" (coarse duplicates of the detailed rows)`);
    }
  }
}

const raw = new Map();         // canonical name -> UNSIMPLIFIED rings
const unmatched = new Set();
for (const f of workingFeatures) {
  const val = f.properties?.[prop];
  const name = level === 'state' ? canonical(val) : String(val ?? '').trim();
  if (!name) { unmatched.add(String(val)); continue; }
  const prev = raw.get(name) ?? [];
  raw.set(name, prev.concat(ringsOf(f.geometry)));
}

// Dissolve THEN simplify. Simplifying first would move vertices
// independently in each district and destroy the shared-edge equality
// the dissolve depends on.
const collected = new Map();
let dissolvedGroups = 0, fellBack = 0;
for (const [name, rings] of raw) {
  let use = rings;
  if (noDissolve) {
    // caller opted out
  } else if (rings.length > 1) {
    const res = dissolve(snapRings(rings, snapDecimals));
    if (res.ok) { use = res.rings; dissolvedGroups++; }
    else { fellBack++; }
  }
  // Simplify, but never let a region simplify out of existence. Small
  // island UTs (Lakshadweep measured ~0.02deg across) lose every ring at
  // a country-scale tolerance and would vanish from the map silently —
  // the worst kind of bug, because the map still looks complete. Back
  // the tolerance off until something survives, then keep raw geometry
  // as the floor.
  let simplified = use.map((r) => simplify(r, tolerance)).filter((r) => r.length >= 4);
  if (!simplified.length) {
    for (const t of [tolerance / 10, tolerance / 100, 0]) {
      simplified = use.map((r) => simplify(r, t)).filter((r) => r.length >= 4);
      if (simplified.length) {
        console.log(`  note: "${name}" too small for tolerance ${tolerance}; kept at ${t}`);
        break;
      }
    }
  }
  if (!simplified.length) {
    simplified = use.filter((r) => r.length >= 4);
    if (simplified.length) console.warn(`  WARNING "${name}" kept unsimplified`);
    else console.warn(`  WARNING "${name}" has NO usable geometry and will not render`);
  }
  collected.set(name, simplified);
}
if (dissolvedGroups) console.log(`dissolved ${dissolvedGroups} group(s) to outer boundaries${fellBack ? `; ${fellBack} fell back to raw rings` : ''}`);

if (!collected.size) {
  console.error('ERROR: no features matched. Pass --name-prop explicitly.');
  process.exit(1);
}

/* ── project ──────────────────────────────────────────────────────── */
let minLon = Infinity, maxLon = -Infinity, minLat = Infinity, maxLat = -Infinity;
for (const rings of collected.values())
  for (const r of rings)
    for (const [lon, lat] of r) {
      if (lon < minLon) minLon = lon; if (lon > maxLon) maxLon = lon;
      if (lat < minLat) minLat = lat; if (lat > maxLat) maxLat = lat;
    }

// Equirectangular with a cos(mean-lat) correction on longitude: at
// India's latitudes this keeps the country's proportions honest without
// the vertical stretch Mercator introduces toward the north.
const midLat = (minLat + maxLat) / 2;
const kx = Math.cos((midLat * Math.PI) / 180);
const VB = 1000;
const spanX = (maxLon - minLon) * kx, spanY = maxLat - minLat;
const scale = VB / Math.max(spanX, spanY);
const offX = (VB - spanX * scale) / 2, offY = (VB - spanY * scale) / 2;
const px = (lon) => +(((lon - minLon) * kx * scale) + offX).toFixed(1);
const py = (lat) => +(((maxLat - lat) * scale) + offY).toFixed(1);

const toPath = (rings) => rings
  .map((r) => r.map(([lon, lat], i) => `${i ? 'L' : 'M'}${px(lon)} ${py(lat)}`).join('') + 'Z')
  .join('');

/** Signed area x2 of a projected ring (shoelace). */
function ringArea2(pts) {
  let a = 0;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    a += pts[j][0] * pts[i][1] - pts[i][0] * pts[j][1];
  }
  return a;
}

/** Label anchor for outline mode.
 *
 *  Centroid of the LARGEST ring, not of all rings combined: an
 *  area-weighted centroid over every ring drags Kerala's label into the
 *  Arabian Sea the moment Lakshadweep-like outliers are in the same
 *  feature, and puts Andaman's label in open water between its island
 *  groups. The biggest landmass is where a reader looks for the name.
 *
 *  Returned in PROJECTED coordinates so the renderer needs no geo maths.
 */
function labelAnchor(rings) {
  let best = null, bestAbs = -1;
  for (const r of rings) {
    const pts = r.map(([lon, lat]) => [px(lon), py(lat)]);
    const a2 = ringArea2(pts);
    if (Math.abs(a2) > bestAbs) { bestAbs = Math.abs(a2); best = { pts, a2 }; }
  }
  if (!best || best.a2 === 0) {
    // Degenerate ring — fall back to the bounding-box centre.
    const all = rings.flat().map(([lon, lat]) => [px(lon), py(lat)]);
    if (!all.length) return null;
    const xs = all.map((p) => p[0]), ys = all.map((p) => p[1]);
    return [ +(((Math.min(...xs) + Math.max(...xs)) / 2).toFixed(1)),
             +(((Math.min(...ys) + Math.max(...ys)) / 2).toFixed(1)) ];
  }
  const { pts, a2 } = best;
  let cx = 0, cy = 0;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const f = pts[j][0] * pts[i][1] - pts[i][0] * pts[j][1];
    cx += (pts[j][0] + pts[i][0]) * f;
    cy += (pts[j][1] + pts[i][1]) * f;
  }
  return [+(cx / (3 * a2)).toFixed(1), +(cy / (3 * a2)).toFixed(1)];
}

/* ── emit ─────────────────────────────────────────────────────────── */
const shapes = [...collected.entries()]
  .sort(([a], [b]) => a.localeCompare(b))
  .map(([name, rings]) => ({
    name,
    label: shortLabel(name),
    d: toPath(rings),
    anchor: labelAnchor(rings),
    // Projected bbox of the LARGEST ring — the space actually available
    // for a label, which is what decides full name vs short code. The
    // whole-region bbox would lie for anything with distant islands.
    box: (() => {
      let best = null, bestA = -1;
      for (const r of rings) {
        const pts = r.map(([lon, lat]) => [px(lon), py(lat)]);
        const a = Math.abs(ringArea2(pts));
        if (a > bestA) { bestA = a; best = pts; }
      }
      if (!best) return null;
      const xs = best.map((p) => p[0]), ys = best.map((p) => p[1]);
      return [+(Math.max(...xs) - Math.min(...xs)).toFixed(0),
              +(Math.max(...ys) - Math.min(...ys)).toFixed(0)];
    })(),
  }));

const body = shapes
  .map((s) => `  { name: ${JSON.stringify(s.name)}, label: ${JSON.stringify(s.label)}`
    + (s.anchor ? `, cx: ${s.anchor[0]}, cy: ${s.anchor[1]}` : '')
    + (s.box ? `, bw: ${s.box[0]}, bh: ${s.box[1]}` : '')
    + `, d: ${JSON.stringify(s.d)} },`)
  .join('\n');

mkdirSync(dirname(OUT), { recursive: true });
writeFileSync(OUT, `/* GENERATED by tools/geojson-to-paths.mjs — do not edit by hand.
 * source     : ${input}
 * provenance : ${sourceUrl}
 * level      : ${level}
 * name prop  : ${prop}
 * tolerance  : ${tolerance}
 * projection : equirectangular, lon scaled by cos(${midLat.toFixed(2)}deg), ${VB}x${VB} viewBox
 * regions    : ${shapes.length}
 *
 * Re-generate with:
 *   node tools/geojson-to-paths.mjs <input.geojson> --level ${level}
 */
import type { MapShape } from './geo-tile-grid';

export const BOUNDARY_VIEWBOX = ${VB};

export const BOUNDARY_SHAPES: MapShape[] = [
${body}
];
`);

const bytes = readFileSync(OUT).length;
console.log(`wrote ${OUT}`);
console.log(`  regions: ${shapes.length}   size: ${(bytes / 1024).toFixed(0)} KB`);
if (level === 'state') {
  const missing = STATES.filter((s) => !collected.has(s));
  if (missing.length) console.warn(`  WARNING missing ${missing.length}: ${missing.join(', ')}`);
}
if (unmatched.size) console.warn(`  WARNING unmatched source names: ${[...unmatched].join(', ')}`);
if (bytes > 600 * 1024) console.warn('  NOTE >600 KB — raise --tolerance (e.g. 0.02) to simplify further.');
