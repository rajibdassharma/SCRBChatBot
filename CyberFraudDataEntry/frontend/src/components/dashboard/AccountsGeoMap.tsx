/** Account Details -> Map view (2026-07-31).
 *
 *  Renders a choropleth of account concentration over a `MapLayout`.
 *  Two rendering modes share one code path:
 *
 *    tile mode  (today)  — shapes carry row/col, drawn as <rect>
 *    path mode  (later)  — shapes carry `d`, drawn as <path>
 *
 *  Path mode is already wired so that dropping an approved boundary
 *  file into geo-tile-grid.ts turns this into a true outline map with
 *  no change here. See that file's header for why we don't ship one.
 *
 *  Deliberately built on plain SVG rather than a mapping library: the
 *  server is on an internal KSP network with no CDN reachable, and the
 *  bundle already carries recharts + xlsx + jspdf. A choropleth is a
 *  fill colour and a tooltip — it doesn't justify another dependency.
 */
import { useMemo, useRef, useState } from 'react';
import { MapPin, AlertTriangle } from 'lucide-react';
import type { MapLayout, MapShape } from '../../lib/utils/geo-tile-grid';
import type { AccountsGeoRegion } from '../../types';
import { formatNumber } from '../../lib/utils/format';

const COLOR_NAVY = '#0b2c4a';

/** Sequential red ramp, light -> dark: the darkest step is the hottest
 *  region. Single hue (4° spread), monotone in OKLCH lightness, so the
 *  eye reads "more" without consulting the legend and it survives
 *  greyscale printing for briefing packs.
 *
 *  FOUR steps, not five, and that is a measured choice rather than a
 *  stylistic one. A single-hue ramp spanning L 0.42–0.93 has only so
 *  much perceptual room: at five steps the adjacent gaps fall to
 *  ΔE ~12 (OKLab x100), under the ΔE 15 normal-vision floor — two
 *  neighbouring shades a full-colour reader cannot reliably separate.
 *  At four steps the worst adjacent pair is ΔE 16.5 normal / 14.8
 *  simulated deuteranopia, clear of both gates.
 *
 *  Verified with the dataviz validator:
 *    validate_palette.js "#fbd5d1,#f0928a,#cf4034,#8b1919"
 *        --mode light --surface "#ffffff" --ordinal   -> monotone L,
 *        adjacent dL >= 0.06, single hue all PASS
 *    ...same palette --pairs all -> CVD PASS 14.8, normal-vision PASS 16.5
 *  The one check it does not clear is the ORDINAL light-end floor
 *  (#fbd5d1 sits at 1.35:1 on white, under 2:1). That floor governs
 *  discrete ordered marks; for a sequential choropleth the lightest
 *  step means "near zero" and is expressly allowed to recede toward
 *  the surface — and every tile carries its number anyway.
 *
 *  The darkest step is the dashboard's existing Mule colour (#8b1919),
 *  so "hottest region" and "Mule" stay the same red across the app.
 */
const RAMP = ['#fbd5d1', '#f0928a', '#cf4034', '#8b1919'];

/** Index at/after which a tile's fill is dark enough to need light
 *  text. Measured, not guessed — navy ink scores 10.55 / 6.23 on steps
 *  0-1, white ink 4.73 / 9.33 on steps 2-3. Every label clears 4.5:1. */
const INK_FLIP_STEP = 2;

/** Regions with genuinely zero accounts. Neutral grey, deliberately
 *  outside the red ramp so "none" never reads as "a little" — and the
 *  region prints an em-dash instead of a number, so the distinction is
 *  never carried by colour alone.
 *
 *  Deliberately darker than the near-white it started as: on the white
 *  card a 1.13:1 fill made zero-count regions (Ladakh, the north-east)
 *  dissolve into the background and lose their borders entirely. This
 *  sits at ~1.45:1 — still clearly "empty", but a shape you can see. */
const COLOR_EMPTY = '#d4d4ce';

/** Border between regions in outline mode. White reads as a cut
 *  between neighbours rather than an ink line drawn on top, which
 *  keeps the heat ramp the only thing carrying colour meaning. */
const COLOR_BORDER = '#ffffff';

export interface AccountsGeoMapProps {
  layout: MapLayout;
  /** Raw API rows. Regions absent from this list render as zero. */
  data: AccountsGeoRegion[];
  /** Which count drives the shading. */
  metric: 'total' | 'victims' | 'mules' | 'non_mules';
  /** Called when a region tile is clicked. */
  onSelect?: (regionName: string) => void;
  selected?: string | null;
}

/** Tile edge in SVG user units. viewBox scales to the container, so
 *  this is unitless — only its ratio to the type sizes matters. */
const CELL = 100;
const GAP = 8;

/** Shrink the count to fit the tile. At weight 800 a digit advances
 *  ~0.58em, so the size falls straight out of the string length rather
 *  than from guessed tiers — en-IN grouping makes long numbers longer
 *  than you expect ("1,28,456" is 8 glyphs, not 6), and a number
 *  spilling over its tile border is the kind of thing nobody notices
 *  until it is on a briefing slide. */
function countFontSize(value: number): number {
  const len = value.toLocaleString('en-IN').length;
  const fit = Math.floor((CELL - 12) / (len * 0.58));
  return Math.max(14, Math.min(34, fit));
}

/* ── outline-mode label fitting ───────────────────────────────────────
 * Region areas span three orders of magnitude: Rajasthan has 269 units
 * of width, Delhi 15, Lakshadweep 1. So the label is the standard
 * two-letter state abbreviation (KA, TN, JK) rather than the full name
 * — it fits inside the boundary at a size that stays legible, and it
 * reads consistently across every region instead of the map switching
 * between full names and codes depending on how big a state happens to
 * be. Full names live in the tooltip and the ranked table below.
 *
 *   code + count  ->  count only  ->  count with halo  ->  nothing
 *
 * SIZING. The map renders at ~620px for a 1000-unit viewBox, so
 * 1 unit is about 0.62px. That is what the constants below are set
 * against: a 16-unit code is ~10px and a 20-unit count ~12.4px, both
 * comfortably readable, while the floors stop anything from shrinking
 * into illegibility. Change the viewBox or the height cap and these
 * want revisiting.
 *
 * Widths are estimated, not measured: measuring would need a DOM text
 * pass per region per render. 0.52em per glyph is a good average for
 * this weight, and every branch keeps an 8% margin, so an estimate a
 * little off never overflows visibly.
 */
const GLYPH_W = 0.52;
const textW = (s: string, size: number) => s.length * size * GLYPH_W;

/** Code sizes to try, largest first. ~10px down to ~7.4px on screen. */
const CODE_SIZES = [16, 15, 14, 13, 12];
/** Count caps. 20 units ~= 12.4px; below 10 units (~6.2px) a number
 *  stops being readable and we switch to the halo treatment instead of
 *  quietly rendering something nobody can make out. */
const NUM_MAX = 20;
const NUM_MIN = 10;

interface FittedLabel {
  lines: string[];
  nameSize: number;
  numSize: number;
  /** true when the label is too big for its region and is drawn with a
   *  white halo so it stays readable spilling over neighbours. */
  halo?: boolean;
}

function fitLabel(
  code: string, bw: number, bh: number,
  count: string, hasValue: boolean,
): FittedLabel | null {
  const availW = bw * 0.92;
  const availH = bh * 0.75;

  // Size the count against BOTH axes. Width alone lets a wide, flat
  // region (Meghalaya, Sikkim) award the number its full budget and
  // leave no vertical room for the code above it.
  const numSize = Math.min(
    NUM_MAX,
    Math.floor(availW / (count.length * GLYPH_W)),
    Math.floor(availH * 0.55),
  );

  if (numSize < NUM_MIN || availH < 14) {
    // Too small for anything inline. A blank region is fine when it has
    // nothing to report, but Delhi is physically tiny and among the
    // highest-count states — leaving it unlabelled would hide the very
    // thing the map exists to surface. Draw the count over the top with
    // a halo instead. This is the ONE case that knowingly breaks the
    // fits-inside-the-boundary rule, because the alternative is losing
    // the data point entirely.
    return hasValue ? { lines: [], nameSize: 0, numSize: 14, halo: true } : null;
  }

  for (const size of CODE_SIZES) {
    if (size + numSize > availH) continue;
    if (textW(code, size) <= availW) return { lines: [code], nameSize: size, numSize };
  }
  return { lines: [], nameSize: 0, numSize };   // count only
}

/** QUANTILE bucketing, not magnitude bucketing — the difference
 *  matters enough to spell out.
 *
 *  Account counts are brutally skewed: one state routinely holds more
 *  than all the others combined. Scaling colour to magnitude (linear
 *  or sqrt) spends the whole ramp on that outlier and flattens
 *  everyone else into the palest step. Measured on a realistic
 *  distribution (18 non-zero states, top = 1284) a sqrt scale put 13
 *  states in step 0, 4 in step 1, NONE in step 2 and 1 in step 3 — a
 *  four-colour ramp doing the work of two. Quantile bucketing on the
 *  same data gives 5 / 4 / 5 / 4.
 *
 *  The trade is real and worth stating: a dark tile means "top
 *  quarter", not "huge". That is acceptable only because every tile
 *  prints its actual count — colour carries the rank band, the number
 *  carries the magnitude, and the reader gets both. Do not drop the
 *  numbers from this map without switching back to a magnitude scale.
 *
 *  `sortedNonZero` must be ascending. Ties share a bucket, since the
 *  rank used is "how many values are <= mine".
 */
function bucketOf(value: number, sortedNonZero: number[]): number {
  if (value <= 0) return -1;
  const n = sortedNonZero.length;
  if (n === 0) return 0;
  let rank = 0;
  for (const v of sortedNonZero) {
    if (v <= value) rank++;
    else break;
  }
  return Math.min(RAMP.length - 1, Math.floor(((rank - 1) / n) * RAMP.length));
}

export function AccountsGeoMap({
  layout, data, metric, onSelect, selected,
}: AccountsGeoMapProps) {
  const [hover, setHover] = useState<{ shape: MapShape; row: AccountsGeoRegion } | null>(null);
  /** Pointer position in container-relative px, for the follow-cursor
   *  tooltip. Kept separate from `hover` so moving within one region
   *  still repositions the card. */
  const [ptr, setPtr] = useState<{ x: number; y: number } | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  const trackPointer = (e: { clientX: number; clientY: number }) => {
    const box = wrapRef.current?.getBoundingClientRect();
    if (!box) return;
    setPtr({ x: e.clientX - box.left, y: e.clientY - box.top });
  };

  /** Case-insensitive lookup keyed on the trimmed region name. The API
   *  already TRIMs, but branch_state is free text and casing drift
   *  ("KARNATAKA") would otherwise read as a separate, unmapped
   *  region. */
  const byRegion = useMemo(() => {
    const m = new Map<string, AccountsGeoRegion>();
    for (const r of data) {
      const key = r.region.trim().toLowerCase();
      if (!key) continue;
      const prev = m.get(key);
      // Fold any casing variants together rather than letting the last
      // one win and under-report the region.
      m.set(key, prev ? {
        region: prev.region,
        total: prev.total + r.total,
        victims: prev.victims + r.victims,
        mules: prev.mules + r.mules,
        non_mules: prev.non_mules + r.non_mules,
      } : r);
    }
    return m;
  }, [data]);

  const valueOf = (r: AccountsGeoRegion | undefined): number => (r ? r[metric] : 0);

  /** Ascending non-zero values across the plotted regions — the basis
   *  for the quantile bands. Zeroes are excluded so a mostly-empty map
   *  doesn't push every real region into the top band. */
  const sortedNonZero = useMemo(() => {
    const vals: number[] = [];
    for (const s of layout.shapes) {
      const v = valueOf(byRegion.get(s.name.trim().toLowerCase()));
      if (v > 0) vals.push(v);
    }
    return vals.sort((a, b) => a - b);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout, byRegion, metric]);

  /** Rows the layout has no tile for. Two causes, both worth showing:
   *  a blank branch_state (region === ''), and a value that isn't in
   *  the canonical picklist (legacy typo, renamed district). Silently
   *  dropping either would make the map look more complete than the
   *  data actually is. */
  const { blank, unmapped } = useMemo(() => {
    const known = new Set(layout.shapes.map((s) => s.name.trim().toLowerCase()));
    const blankRows = data.filter((r) => r.region.trim() === '');
    const strays = data.filter((r) => {
      const key = r.region.trim().toLowerCase();
      return key !== '' && !known.has(key);
    });
    // reduce without a seed: safe because the length check guarantees
    // at least one element, and it avoids inventing a zero row.
    const blankRow: AccountsGeoRegion | null = blankRows.length > 0
      ? blankRows.reduce((a, b) => ({
          region: '',
          total: a.total + b.total,
          victims: a.victims + b.victims,
          mules: a.mules + b.mules,
          non_mules: a.non_mules + b.non_mules,
        }))
      : null;
    return { blank: blankRow, unmapped: strays };
  }, [data, layout]);

  const plotted = useMemo(
    () => layout.shapes.reduce(
      (sum, s) => sum + valueOf(byRegion.get(s.name.trim().toLowerCase())), 0,
    ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [layout, byRegion, metric],
  );
  const offMap = (blank ? blank[metric] : 0)
    + unmapped.reduce((s, r) => s + r[metric], 0);

  const pathMode = layout.shapes.some((s) => s.d);

  return (
    <div>
      <div className="flex items-start justify-between flex-wrap gap-3 mb-3">
        <div>
          <h3 className="text-sm font-bold flex items-center gap-1.5" style={{ color: COLOR_NAVY }}>
            <MapPin className="w-4 h-4" /> {layout.label}
          </h3>
          <p className="text-xs mt-0.5" style={{ color: 'rgba(11,44,74,0.65)' }}>
            Shading ranks regions into four equal bands — darkest red is the
            top quarter. The number on each tile is the actual count.
            {!pathMode && ' Tiles are positioned by approximate direction, not by border or area.'}
          </p>
        </div>
        {/* Legend */}
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-semibold" style={{ color: 'rgba(11,44,74,0.7)' }}>Low</span>
          <div className="flex">
            {RAMP.map((c, i) => (
              <div key={c} title={`Step ${i + 1}`}
                style={{ background: c, width: 22, height: 12,
                  border: '1px solid rgba(11,44,74,0.15)',
                  borderLeftWidth: i === 0 ? 1 : 0 }} />
            ))}
          </div>
          <span className="text-[11px] font-semibold" style={{ color: 'rgba(11,44,74,0.7)' }}>High</span>
          <div className="flex items-center gap-1 ml-2">
            <div style={{ background: COLOR_EMPTY, width: 22, height: 12, border: '1px solid rgba(11,44,74,0.15)' }} />
            <span className="text-[11px] font-semibold" style={{ color: 'rgba(11,44,74,0.7)' }}>None</span>
          </div>
        </div>
      </div>

      <div className="relative" ref={wrapRef}>
        <svg
          viewBox={pathMode && layout.viewBox
            ? `0 0 ${layout.viewBox} ${layout.viewBox}`
            : `0 0 ${layout.cols * (CELL + GAP)} ${layout.rows * (CELL + GAP)}`}
          className="w-full"
          // The grid is taller than it is wide (9 rows), so height is
          // the binding constraint — this cap sets the tile size, and
          // the count is the primary read, so give it room.
          style={{ maxHeight: 620 }}
          role="img"
          aria-label={`${layout.label} — account concentration`}
        >
          {layout.shapes.map((s) => {
            const row = byRegion.get(s.name.trim().toLowerCase());
            const v = valueOf(row);
            const b = bucketOf(v, sortedNonZero);
            const fill = b < 0 ? COLOR_EMPTY : RAMP[b];
            // Ink flips on the two darkest steps — see INK_FLIP_STEP.
            const textFill = b >= INK_FLIP_STEP ? '#ffffff' : COLOR_NAVY;
            const isSel = selected != null
              && selected.trim().toLowerCase() === s.name.trim().toLowerCase();

            const common = {
              style: { cursor: onSelect ? 'pointer' : 'default' },
              onMouseEnter: () => setHover({ shape: s, row: row ?? { region: s.name, total: 0, victims: 0, mules: 0, non_mules: 0 } }),
              onMouseMove: trackPointer,
              onMouseLeave: () => { setHover(null); setPtr(null); },
              onClick: () => onSelect?.(s.name),
            };

            if (s.d) {
              // Public India files are published per-DISTRICT, and the
              // topological dissolve only succeeds on cleanly-derived
              // sources (1 of 36 states on the file tested). So a state
              // is usually many district subpaths, and SVG strokes every
              // one — stroking in a contrasting colour would draw ~760
              // internal hairlines. Stroking each state in ITS OWN fill
              // makes internal borders vanish while adjacent states stay
              // separated by their differing fills. Selection re-adds a
              // real outline, and the label always carries identity.
              // The dissolve gives one outline per state, so a white
              // stroke draws borders BETWEEN states without painting
              // every internal district line. It also rescues the case
              // two zero-count neighbours sit side by side — identical
              // grey fills that would otherwise merge into one blob.
              const count = v > 0 ? formatNumber(v) : '—';
              const fitted = (s.cx != null && s.cy != null)
                ? fitLabel(s.label, s.bw ?? 0, s.bh ?? 0, count, v > 0)
                : null;
              // Vertically centre the whole stack on the anchor.
              const nLines = fitted ? fitted.lines.length : 0;
              const blockH = fitted ? nLines * fitted.nameSize + fitted.numSize : 0;
              const top = (s.cy ?? 0) - blockH / 2;
              return (
                <g key={s.name} {...common}>
                  <path d={s.d} fill={fill}
                    stroke={isSel ? COLOR_NAVY : COLOR_BORDER}
                    strokeWidth={isSel ? 5 : 2}
                    strokeLinejoin="round" />
                  {fitted && (
                    <g style={{ pointerEvents: 'none' }}>
                      {fitted.lines.map((ln, i) => (
                        <text key={ln + i} x={s.cx} y={top + (i + 1) * fitted.nameSize}
                          textAnchor="middle" fontSize={fitted.nameSize}
                          fontWeight={600} fill={textFill} opacity={0.9}>
                          {ln}
                        </text>
                      ))}
                      <text x={s.cx} y={top + nLines * fitted.nameSize + fitted.numSize}
                        textAnchor="middle" fontSize={fitted.numSize}
                        fontWeight={800}
                        fill={fitted.halo ? COLOR_NAVY : textFill}
                        // paintOrder puts the stroke UNDER the glyph, so
                        // the halo reads as a cut-out rather than an
                        // outline drawn over the letterforms.
                        stroke={fitted.halo ? COLOR_BORDER : undefined}
                        strokeWidth={fitted.halo ? 3.5 : undefined}
                        paintOrder={fitted.halo ? 'stroke' : undefined}>
                        {count}
                      </text>
                    </g>
                  )}
                </g>
              );
            }

            const x = (s.col ?? 0) * (CELL + GAP);
            const y = (s.row ?? 0) * (CELL + GAP);
            return (
              <g key={s.name} {...common}>
                <rect x={x} y={y} width={CELL} height={CELL} rx={10}
                  fill={fill}
                  stroke={isSel ? COLOR_NAVY : 'rgba(11,44,74,0.25)'}
                  strokeWidth={isSel ? 4 : 1.5} />
                {/* Region code identifies the tile; the COUNT is the
                    data, so it gets the larger, heavier type. Printing
                    the number on every tile is deliberate here — on a
                    heat map it is the secondary encoding that lets a
                    reader separate two adjacent shades without
                    squinting at the legend. */}
                <text x={x + CELL / 2} y={y + 38}
                  textAnchor="middle" fontSize={22} fontWeight={700}
                  fill={textFill} opacity={0.85}>
                  {s.label}
                </text>
                <text x={x + CELL / 2} y={y + 76}
                  textAnchor="middle" fontSize={countFontSize(v)} fontWeight={800} fill={textFill}>
                  {v > 0 ? formatNumber(v) : '—'}
                </text>
              </g>
            );
          })}
        </svg>

        {hover && ptr && (() => {
          // Follow the cursor, but flip to the other side when close to
          // an edge so the card is never clipped by the container. The
          // offset keeps it clear of the pointer itself.
          const W = 200, H = 118, PAD = 14;
          const boxW = wrapRef.current?.clientWidth ?? 0;
          const boxH = wrapRef.current?.clientHeight ?? 0;
          const left = ptr.x + PAD + W > boxW ? Math.max(0, ptr.x - PAD - W) : ptr.x + PAD;
          const top = ptr.y + PAD + H > boxH ? Math.max(0, ptr.y - PAD - H) : ptr.y + PAD;
          return (
          <div className="absolute px-3 py-2 rounded-lg pointer-events-none"
            style={{ left, top, width: W,
              background: 'rgba(255,255,255,0.97)', border: `2px solid ${COLOR_NAVY}`,
              boxShadow: '0 6px 16px rgba(0,0,0,0.15)', zIndex: 5 }}>
            <div className="text-xs font-bold" style={{ color: COLOR_NAVY }}>{hover.shape.name}</div>
            {hover.shape.note && (
              <div className="text-[10px] italic" style={{ color: 'rgba(11,44,74,0.6)' }}>{hover.shape.note}</div>
            )}
            <div className="mt-1 space-y-0.5 text-[11px]" style={{ color: COLOR_NAVY }}>
              <div className="flex justify-between gap-4"><span>Total</span><b>{formatNumber(hover.row.total)}</b></div>
              <div className="flex justify-between gap-4"><span>Mule</span><b>{formatNumber(hover.row.mules)}</b></div>
              <div className="flex justify-between gap-4"><span>Victim</span><b>{formatNumber(hover.row.victims)}</b></div>
              <div className="flex justify-between gap-4"><span>Non-Mule</span><b>{formatNumber(hover.row.non_mules)}</b></div>
            </div>
          </div>
          );
        })()}
      </div>

      {/* Coverage honesty panel. branch_state / branch_district arrived
          in migrations 010/012, after data entry had already started,
          so a chunk of rows simply have no location. Reporting that
          plainly is the difference between a map that informs and one
          that quietly misleads. */}
      {offMap > 0 && (
        <div className="mt-3 px-3 py-2 rounded-lg flex items-start gap-2"
          style={{ background: 'rgba(198,124,29,0.10)', border: '1px solid rgba(198,124,29,0.35)' }}>
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" style={{ color: '#c67c1d' }} />
          <div className="text-xs" style={{ color: COLOR_NAVY }}>
            <b>{formatNumber(offMap)}</b> of{' '}
            <b>{formatNumber(plotted + offMap)}</b> accounts are not on the map
            {plotted + offMap > 0 && (
              <> ({Math.round((offMap / (plotted + offMap)) * 100)}%)</>
            )}.
            {blank && blank[metric] > 0 && (
              <> <b>{formatNumber(blank[metric])}</b> have no location recorded.</>
            )}
            {unmapped.length > 0 && (
              <> {unmapped.length} unrecognised value
                {unmapped.length === 1 ? '' : 's'}:{' '}
                <i>{unmapped.slice(0, 5).map((u) => u.region).join(', ')}
                  {unmapped.length > 5 ? ` +${unmapped.length - 5} more` : ''}</i>.
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
