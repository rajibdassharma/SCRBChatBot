/** FIR Dashboard -> Crime Type tab (2026-08-01).
 *
 *  The Overview tab answers a SUPERVISION question: who registered how
 *  many FIRs. This tab answers INVESTIGATIVE ones, and the panel order
 *  reflects that priority rather than what was easiest to plot:
 *
 *    1. Type x district    where each type is happening (local rackets)
 *    2. By volume          how many of each — read in one glance
 *    3. Arrest rate        which types we are failing to solve
 *    4. Freeze rate        golden-hour performance, per modus operandi
 *    6. Inside "Others"    MOs the 31-entry taxonomy has not caught up with
 *
 *  Everything comes from one request. Panels 3 and 4 depend on how well
 *  `arrests` and `lien_accounts` are populated, so both state their
 *  coverage on screen — a sparse table must read as "not recorded",
 *  never as "nobody solves anything".
 */
import { useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LabelList, Legend,
} from 'recharts';
import { TrendingUp, AlertTriangle, Landmark, Gavel, Grid3x3, HelpCircle } from 'lucide-react';
import type { FirCrimeTypeReport, FirCrimeTypeRow } from '../../types';

const C_NAVY = '#0b2c4a';
const C_GREEN = '#0a6b28';
const C_RED = '#8b1919';
const C_ORANGE = '#c67c1d';

const cardStyle = {
  background: '#fff',
  border: '1px solid rgba(0,0,0,0.06)',
  boxShadow: '0 6px 16px rgba(0,0,0,0.08)',
};

const fmtInt = (n: number) => n.toLocaleString('en-IN');

/** Indian-format short money. Crores and lakhs, because that is how
 *  the numbers get spoken in a review meeting. */
function fmtMoney(n: number): string {
  if (!n) return '₹0';
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)} Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(2)} L`;
  if (n >= 1e3) return `₹${(n / 1e3).toFixed(1)}k`;
  return `₹${Math.round(n)}`;
}

/** Truncate a long classification label for an axis tick. */
const shortType = (s: string, n = 26) => (s.length > n ? s.slice(0, n - 1) + '…' : s);

function PanelCard({ title, subtitle, Icon, accent, children }: {
  title: string; subtitle: string; Icon: typeof TrendingUp; accent: string; children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl p-4" style={cardStyle}>
      <h3 className="text-sm font-bold flex items-center gap-1.5" style={{ color: accent }}>
        <Icon className="w-4 h-4" /> {title}
      </h3>
      <p className="text-xs opacity-60 mt-0.5 mb-3">{subtitle}</p>
      {children}
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="py-10 text-center text-sm opacity-60">{children}</p>;
}

export function FirCrimeTypeTab({ report, from, to }: {
  report: FirCrimeTypeReport | null;
  from: string;
  to: string;
}) {
  const types = report?.types ?? [];

  /** Crime types ranked by VOLUME — the question everyone asks first,
   *  answered by bar length alone with no arithmetic required.
   *
   *  An earlier version led with change-vs-previous-window. It was
   *  better analysis and worse communication: the reader had to hold
   *  two date ranges and a derived delta before learning how many of
   *  anything there were. The trend still matters, so it survives as a
   *  small badge per bar — glanceable if you want it, ignorable if you
   *  don't, and never a precondition for reading the chart. */
  const ranked = useMemo(() => {
    return types
      .filter((t) => t.count > 0)
      .map((t) => ({
        ...t,
        delta: t.count - t.prev_count,
        isNew: t.prev_count === 0 && t.count > 0,
      }))
      .sort((a, b) => b.count - a.count || a.crime_type.localeCompare(b.crime_type))
      // EVERY crime type with at least one case. No cap: trimming this
      // to fit a layout silently dropped Digital Arrest off both panels
      // once already. If it gets tall, buy height from row pitch — never
      // from the end of the list.
      ;
  }, [types]);

  const MIN_CASES = 3;

  /** Arrest outcomes as a STACK, not a percentage.
   *
   *  A bare rate hides its denominator: 100% of 3 cases outranks 40%
   *  of 200, when the second is the one that matters. Stacking cases
   *  WITH an arrest against those without puts both on screen at once
   *  — bar length is the workload, the filled part is the outcome.
   *
   *  It also retires the arbitrary "at least 3 cases" floor the old
   *  chart needed. That threshold only existed to stop tiny denominators
   *  producing silly percentages; once the denominator is visible, the
   *  reader can see for themselves that a 3-case type is a 3-case type.
   *
   *  Ordered by UNSOLVED count, not by rate. That combines volume and
   *  failure into one ranking, so the top of the list is the largest
   *  mass of cases with nobody arrested — which is the actionable
   *  thing, rather than whichever rare type happens to score 0%. */
  const arrestRates = useMemo(
    () => types
      .filter((t) => t.count > 0)
      .map((t) => ({
        name: t.crime_type,
        arrested: t.cases_with_arrest,
        pending: Math.max(0, t.count - t.cases_with_arrest),
        cases: t.count,
        rate: Math.round((t.cases_with_arrest / t.count) * 100),
      }))
      .sort((a, b) => b.pending - a.pending || b.cases - a.cases)
      .slice(0, 12),
    [types]);
  const totalArrested = types.reduce((s, t) => s + t.cases_with_arrest, 0);

  const freezeRates = useMemo(
    () => types
      .filter((t) => t.amount_lost > 0 && t.count >= MIN_CASES)
      .map((t) => ({
        name: t.crime_type,
        // Capped at 100: freezes can exceed the recorded loss when a
        // mule account holds money from victims whose own FIRs sit
        // elsewhere. Real, but it would break the axis.
        rate: Math.min(100, Math.round((t.amount_frozen / t.amount_lost) * 100)),
        lost: t.amount_lost,
        frozen: t.amount_frozen,
      }))
      .sort((a, b) => a.rate - b.rate || b.lost - a.lost)
      .slice(0, 12),
    [types]);
  const totalFrozen = types.reduce((s, t) => s + t.amount_frozen, 0);

  /** Type x district grid — top types down the side, districts across,
   *  shaded by share of that type's statewide total so a small district
   *  with a concentration still stands out against a big one. */
  const gridView = useMemo(() => {
    const cells = report?.grid ?? [];
    if (!cells.length) return null;
    // Fewer rows and columns than the full-width version had:
    // this panel now shares a row, and a 12x12 grid in half a
    // column is a horizontal scrollbar rather than a chart.
    // Every type with a case, and below, every district with one.
    const topTypes = types.filter((t) => t.count > 0).map((t) => t.crime_type);
    // Authoritative per-type totals, straight from the same array the
    // volume chart reads. The Total column is derived from THIS, never
    // from summing the visible cells, so the two panels can never
    // disagree on screen again.
    const typeTotal = new Map(types.map((t) => [t.crime_type, t.count]));
    const districtTotals = new Map<string, number>();
    for (const c of cells) {
      if (!topTypes.includes(c.crime_type)) continue;
      districtTotals.set(c.district, (districtTotals.get(c.district) ?? 0) + c.count);
    }
    const districts = [...districtTotals.entries()]
      .filter(([, n]) => n > 0)
      .sort((a, b) => b[1] - a[1])
      .map(([d]) => d);
    const at = new Map(cells.map((c) => [`${c.crime_type}|${c.district}`, c.count]));
    const rowMax = new Map(
      topTypes.map((t) => [t, Math.max(...districts.map((d) => at.get(`${t}|${d}`) ?? 0), 1)]),
    );
    // With every district given a column this is always 0 — but the
    // check stays, so if a cap is ever reintroduced the remainder
    // reappears as a column instead of silently vanishing. That is the
    // bug that made the bar chart and this grid disagree.
    const anyOther = topTypes.some((t) => {
      const shown = districts.reduce((sum, d) => sum + (at.get(`${t}|${d}`) ?? 0), 0);
      return (typeTotal.get(t) ?? 0) - shown > 0;
    });
    return { topTypes, districts, at, rowMax, typeTotal, anyOther };
  }, [report, types]);

  if (!report) return <Empty>Loading crime-type analysis…</Empty>;
  if (!types.length) {
    return (
      <div className="rounded-2xl p-4" style={cardStyle}>
        <Empty>No FIRs registered between {from} and {to}.</Empty>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* District grid first: WHERE each crime type is happening,
           then HOW MANY of each. Both full width — the grid carries
           every crime type and every district with at least one case,
           which is wider than half a screen. */}
      <PanelCard
        title="Crime type by district"
        subtitle="Every crime type and every district with at least one case. Shaded across each ROW, so a concentration in a small district stands out instead of being drowned by a big one — a single dark cell is what a local racket looks like. Row totals match the volume chart below exactly."
        Icon={Grid3x3} accent={C_NAVY}
      >
        {!gridView ? (
          <Empty>No district breakdown available for this window.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="text-xs border-collapse">
              <thead>
                <tr>
                  <th className="px-2 py-1 text-left sticky left-0" style={{ background: '#fff' }} />
                  {gridView.districts.map((d) => (
                    <th key={d} className="px-1 py-2 font-semibold align-bottom"
                      style={{ color: C_NAVY, minWidth: 26 }}>
                      <div title={d} style={{
                        writingMode: 'vertical-rl', transform: 'rotate(180deg)',
                        whiteSpace: 'nowrap',
                        // Capped: rotated text turns name LENGTH into
                        // column HEIGHT, so one long district would set
                        // the header height for the whole grid. Full
                        // name stays in the title attribute.
                        maxHeight: 96, overflow: 'hidden', textOverflow: 'ellipsis',
                      }}>
                        {shortType(d, 18)}
                      </div>
                    </th>
                  ))}
                  {gridView.anyOther && (
                    <th className="px-1 py-2 font-semibold align-bottom"
                      title="Cases in districts outside the columns shown"
                      style={{ color: 'rgba(11,44,74,0.7)', minWidth: 26 }}>
                      <div style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)', whiteSpace: 'nowrap' }}>
                        Other
                      </div>
                    </th>
                  )}
                  <th className="px-2 py-2 font-bold align-bottom text-center"
                    style={{ color: C_NAVY }}>Total</th>
                </tr>
              </thead>
              <tbody>
                {gridView.topTypes.map((t) => {
                  const max = gridView.rowMax.get(t) ?? 1;
                  return (
                    <tr key={t}>
                      <td className="px-2 py-0.5 font-semibold whitespace-nowrap sticky left-0"
                        style={{ color: C_NAVY, background: '#fff' }} title={t}>
                        {shortType(t, 30)}
                      </td>
                      {gridView.districts.map((d) => {
                        const n = gridView.at.get(`${t}|${d}`) ?? 0;
                        const a = n === 0 ? 0 : 0.12 + 0.88 * (n / max);
                        return (
                          <td key={d} className="px-1 py-0.5 text-center font-semibold"
                            title={`${t} — ${d}: ${fmtInt(n)}`}
                            style={{
                              background: n === 0 ? '#f6f6f4' : `rgba(139,25,25,${a.toFixed(2)})`,
                              color: a > 0.55 ? '#fff' : C_NAVY,
                              border: '1px solid rgba(255,255,255,0.9)',
                            }}>
                            {n === 0 ? '' : fmtInt(n)}
                          </td>
                        );
                      })}
                      {(() => {
                        const total = gridView.typeTotal.get(t) ?? 0;
                        const shown = gridView.districts
                          .reduce((sum, d) => sum + (gridView.at.get(`${t}|${d}`) ?? 0), 0);
                        const other = Math.max(0, total - shown);
                        return (
                          <>
                            {gridView.anyOther && (
                              <td className="px-1 py-0.5 text-center font-semibold"
                                title={`${t} — districts not shown: ${fmtInt(other)}`}
                                style={{
                                  background: other === 0 ? '#f6f6f4' : 'rgba(11,44,74,0.10)',
                                  color: C_NAVY, border: '1px solid rgba(255,255,255,0.9)',
                                }}>
                                {other === 0 ? '' : fmtInt(other)}
                              </td>
                            )}
                            <td className="px-2 py-0.5 text-center font-bold"
                              style={{ color: C_NAVY, background: '#fff',
                                       borderLeft: '2px solid rgba(11,44,74,0.25)' }}>
                              {fmtInt(total)}
                            </td>
                          </>
                        );
                      })()}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </PanelCard>

      <PanelCard
        title="Crime types by volume"
        subtitle="How many FIRs of each type in the selected date range, biggest first. The small arrow beside a bar shows whether that type is up or down on the preceding period — extra context, not something you need in order to read the chart."
        Icon={AlertTriangle} accent={C_NAVY}
      >
        {ranked.length === 0 ? (
          <Empty>No FIRs registered in this window.</Empty>
        ) : (
          <ResponsiveContainer width="100%" height={Math.max(190, ranked.length * 22 + 28)}>
            <BarChart data={ranked} layout="vertical"
              margin={{ top: 4, right: 96, left: 8, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(11,44,74,0.10)" horizontal={false} />
              <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11, fill: C_NAVY }} />
              <YAxis type="category" dataKey="crime_type" width={180}
                tick={{ fontSize: 10, fill: C_NAVY }}
                tickFormatter={(v) => shortType(String(v), 30)} />
              <Tooltip
                cursor={{ fill: 'rgba(11,44,74,0.05)' }}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const p = payload[0].payload;
                  return (
                    <div className="px-3 py-2 rounded-lg text-xs"
                      style={{ background: '#fff', border: `2px solid ${C_NAVY}`,
                               boxShadow: '0 6px 16px rgba(0,0,0,0.15)', maxWidth: 260 }}>
                      <div className="font-bold" style={{ color: C_NAVY }}>{p.crime_type}</div>
                      <div className="mt-1"><b>{fmtInt(p.count)}</b> FIRs in this range</div>
                      <div className="opacity-70">
                        {p.isNew
                          ? 'None in the preceding period'
                          : `${fmtInt(p.prev_count)} in the preceding period (${p.delta > 0 ? '+' : ''}${fmtInt(p.delta)})`}
                      </div>
                    </div>
                  );
                }} />
              {/* One hue for every bar. Colouring nominal bars by their
                  own value would spend the colour channel re-encoding
                  what bar length already says. */}
              <Bar dataKey="count" fill={C_NAVY} radius={[0, 3, 3, 0]} isAnimationActive={false}>
                <LabelList dataKey="count" content={(props) => {
                  const { x, y, width, height, index } = props as unknown as
                    { x: number; y: number; width: number; height: number; index: number };
                  const row = ranked[index];
                  if (!row) return null;
                  const up = row.delta > 0;
                  const flat = row.delta === 0;
                  // Count first — that is the number being read. The
                  // trend arrow trails it, smaller and dimmer, so it
                  // never competes for attention.
                  return (
                    <g>
                      <text x={x + width + 8} y={y + height / 2} dy={4}
                        fontSize={12} fontWeight={800} fill={C_NAVY}>
                        {fmtInt(row.count)}
                      </text>
                      {!flat && (
                        <text x={x + width + 8 + String(row.count).length * 8 + 8}
                          y={y + height / 2} dy={4}
                          fontSize={10} fontWeight={700}
                          fill={up ? C_RED : 'rgba(11,44,74,0.55)'}>
                          {row.isNew ? 'new' : `${up ? '▲' : '▼'} ${Math.abs(row.delta)}`}
                        </text>
                      )}
                    </g>
                  );
                }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </PanelCard>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 3 — Arrest rate */}
        <PanelCard
          title="Arrest rate by crime type"
          subtitle="Cases with at least one arrest against those still without. Bar length is the workload, the green part is the outcome — a long bar that is nearly all grey is a big crime type nobody has been arrested for. Ordered by how many cases still have no arrest."
          Icon={Gavel} accent={C_ORANGE}
        >
          {totalArrested === 0 ? (
            <Empty>
              No arrests recorded against any FIR in this window — this reads as
              missing data rather than a clearance rate of zero.
            </Empty>
          ) : arrestRates.length === 0 ? (
            <Empty>No crime type has enough cases to compute a meaningful rate.</Empty>
          ) : (
            <ResponsiveContainer width="100%" height={Math.max(220, arrestRates.length * 26 + 44)}>
              <BarChart data={arrestRates} layout="vertical"
                margin={{ top: 4, right: 100, left: 8, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(11,44,74,0.10)" horizontal={false} />
                <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11, fill: C_NAVY }} />
                <YAxis type="category" dataKey="name" width={150}
                  tick={{ fontSize: 10, fill: C_NAVY }} tickFormatter={(v) => shortType(String(v), 24)} />
                <Tooltip
                  cursor={{ fill: 'rgba(11,44,74,0.05)' }}
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const p = payload[0].payload;
                    return (
                      <div className="px-3 py-2 rounded-lg text-xs"
                        style={{ background: '#fff', border: `2px solid ${C_NAVY}`,
                                 boxShadow: '0 6px 16px rgba(0,0,0,0.15)', maxWidth: 260 }}>
                        <div className="font-bold" style={{ color: C_NAVY }}>{p.name}</div>
                        <div className="mt-1"><b>{fmtInt(p.cases)}</b> cases</div>
                        <div style={{ color: C_GREEN }}>{fmtInt(p.arrested)} with an arrest ({p.rate}%)</div>
                        <div className="opacity-70">{fmtInt(p.pending)} with none</div>
                      </div>
                    );
                  }} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                {/* Stacked, with a 2px surface-coloured gap between the
                    fills so the boundary reads as a break rather than
                    just a change of colour. */}
                <Bar dataKey="arrested" stackId="a" name="With an arrest"
                  fill={C_GREEN} stroke="#fff" strokeWidth={2} isAnimationActive={false} />
                <Bar dataKey="pending" stackId="a" name="No arrest yet"
                  fill="#d4d4ce" stroke="#fff" strokeWidth={2} isAnimationActive={false}>
                  <LabelList dataKey="cases" content={(props) => {
                    const { x, y, width, height, index } = props as unknown as
                      { x: number; y: number; width: number; height: number; index: number };
                    const row = arrestRates[index];
                    if (!row) return null;
                    return (
                      <text x={x + width + 8} y={y + height / 2} dy={4}
                        fontSize={11} fontWeight={700}
                        fill={row.rate === 0 ? C_RED : C_NAVY}>
                        {fmtInt(row.arrested)}/{fmtInt(row.cases)} · {row.rate}%
                      </text>
                    );
                  }} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </PanelCard>

        {/* 4 — Freeze rate */}
        <PanelCard
          title="Freeze rate by crime type"
          subtitle="Amount lien-marked as a share of amount lost — golden-hour performance per modus operandi. Lowest first."
          Icon={Landmark} accent={C_GREEN}
        >
          {totalFrozen === 0 ? (
            <Empty>
              No lien-marked amounts recorded in this window — missing data rather
              than a freeze rate of zero.
            </Empty>
          ) : freezeRates.length === 0 ? (
            <Empty>Not enough cases with a recorded loss to compute a rate.</Empty>
          ) : (
            <ResponsiveContainer width="100%" height={340}>
              <BarChart data={freezeRates} layout="vertical" margin={{ top: 4, right: 28, left: 8, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(11,44,74,0.10)" horizontal={false} />
                <XAxis type="number" domain={[0, 100]} unit="%" tick={{ fontSize: 11, fill: C_NAVY }} />
                <YAxis type="category" dataKey="name" width={150}
                  tick={{ fontSize: 10, fill: C_NAVY }} tickFormatter={(v) => shortType(String(v), 24)} />
                <Tooltip
                  formatter={(v, _k, item) => [
                    `${v}%  (${fmtMoney(item?.payload?.frozen ?? 0)} of ${fmtMoney(item?.payload?.lost ?? 0)})`,
                    'Frozen',
                  ]}
                  labelFormatter={(l) => String(l)} />
                <Bar dataKey="rate" fill={C_GREEN} radius={[0, 4, 4, 0]} name="Freeze rate" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </PanelCard>
      </div>

      {/* 5 — Crime type x district */}
      {/* 6 — Inside "Others" */}
      <PanelCard
        title={`Inside "Others" — ${fmtInt(report.others.length)} distinct ${report.others.length === 1 ? 'description' : 'descriptions'}`}
        subtitle="What operators typed when none of the 31 classifications fitted. A phrase recurring here is an emerging modus operandi the taxonomy has not caught up with — and a candidate for the next revision of the list."
        Icon={HelpCircle} accent={C_ORANGE}
      >
        {report.others.length === 0 ? (
          <Empty>No "Others" free text recorded in this window.</Empty>
        ) : (
          <div className="flex flex-wrap gap-2">
            {report.others.map((o) => (
              <span key={o.text}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold"
                style={{
                  background: o.count > 1 ? 'rgba(198,124,29,0.16)' : 'rgba(11,44,74,0.06)',
                  border: o.count > 1 ? '1px solid rgba(198,124,29,0.45)' : '1px solid rgba(11,44,74,0.12)',
                  color: C_NAVY,
                }}
                title={o.count > 1 ? 'Recurring — worth a look' : 'Seen once'}>
                {o.text}
                <b className="ml-1.5">{fmtInt(o.count)}</b>
              </span>
            ))}
          </div>
        )}
      </PanelCard>
    </div>
  );
}

/** Re-exported for the parent page's KPI strip. */
export function crimeTypeHeadlines(types: FirCrimeTypeRow[]) {
  const total = types.reduce((s, t) => s + t.count, 0);
  const others = types.find((t) => t.crime_type === 'Others')?.count ?? 0;
  const top = types[0];
  const biggestRise = [...types]
    .map((t) => ({ t, d: t.count - t.prev_count }))
    .sort((a, b) => b.d - a.d)[0];
  return {
    distinct: types.filter((t) => t.count > 0).length,
    top: top?.crime_type ?? '—',
    topCount: top?.count ?? 0,
    othersPct: total > 0 ? Math.round((others / total) * 100) : 0,
    rising: biggestRise && biggestRise.d > 0 ? biggestRise.t.crime_type : '—',
    risingDelta: biggestRise && biggestRise.d > 0 ? biggestRise.d : 0,
  };
}
