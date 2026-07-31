/** Tile-grid ("cartogram") layouts for the Account Details map view.
 *
 *  WHY A TILE GRID AND NOT AN OUTLINE MAP
 *  --------------------------------------
 *  Rendering a true outline of India requires a boundary dataset, and
 *  for a police portal that dataset is not a neutral technical choice:
 *  the depiction of Jammu & Kashmir, Ladakh and Arunachal Pradesh is
 *  regulated, and third-party GeoJSON files routinely get it wrong.
 *  Rather than ship a non-compliant map, this layout places each region
 *  as a labelled square in roughly its geographic position. It is
 *  explicitly schematic — nobody can mistake it for a survey map — and
 *  it answers the actual question ("where are mule accounts
 *  concentrated?") just as well, because the eye is comparing shading
 *  across regions, not measuring borders.
 *
 *  UPGRADING TO A REAL MAP LATER
 *  -----------------------------
 *  `MapShape` carries an optional `d` (SVG path). When an approved
 *  Survey of India / KSP GIS boundary file is available, project it to
 *  path strings and populate `d` — `AccountsGeoMap` already renders
 *  path-mode shapes and needs no change. Positions (`row`/`col`) are
 *  simply ignored once `d` is present.
 *
 *  ACCURACY NOTE: grid positions are approximate by design. They encode
 *  adjacency and rough compass direction, nothing more. They are NOT a
 *  statement about borders, territory, or area.
 */

import { BOUNDARY_SHAPES, BOUNDARY_VIEWBOX } from './geo-boundaries.generated';

export interface MapShape {
  /** MUST match the value stored in the DB exactly — this is the join
   *  key against the API's `region` field. Mismatches surface in the
   *  "unmapped" bucket rather than silently disappearing. */
  name: string;
  /** Short label drawn inside the tile. */
  label: string;
  /** Tile-mode position. Ignored when `d` is set. */
  row?: number;
  col?: number;
  /** Path-mode geometry (SVG path data). Empty today — see the header. */
  d?: string;
  /** Label anchor in projected path-mode coordinates. Centroid of the
   *  region's largest ring, so the text lands on the main landmass
   *  rather than in the sea between island groups. */
  cx?: number;
  cy?: number;
  /** Bounding box of the region's largest ring, in the same projected
   *  units — the space actually available for a label. Drives the
   *  full-name / short-code / number-only fallback. */
  bw?: number;
  bh?: number;
  /** Shown in the tooltip. Used to mark police commissionerates, which
   *  are not revenue districts but do appear in the district picklist. */
  note?: string;
}

export interface MapLayout {
  id: string;
  /** Human label for the layout, shown above the map. */
  label: string;
  rows: number;
  cols: number;
  shapes: MapShape[];
  /** Square viewBox edge for outline mode. Set only when `shapes`
   *  carry `d` paths; tile mode derives its viewBox from rows/cols. */
  viewBox?: number;
}

/* ── India: 28 states + 8 union territories ───────────────────────────
 * Names match INDIAN_STATES in ./indian-states.ts character-for-
 * character; that list is what the Branch State dropdown writes to the
 * DB, so any drift here shows up as an unmapped region on screen.
 */
const INDIA_TILES: MapShape[] = [
  // Northern tier
  { name: 'Jammu and Kashmir', label: 'JK', row: 0, col: 3 },
  { name: 'Ladakh',            label: 'LA', row: 0, col: 4 },
  { name: 'Punjab',            label: 'PB', row: 1, col: 2 },
  { name: 'Chandigarh',        label: 'CH', row: 1, col: 3 },
  { name: 'Himachal Pradesh',  label: 'HP', row: 1, col: 4 },
  { name: 'Uttarakhand',       label: 'UK', row: 1, col: 5 },
  // Indo-Gangetic plain
  { name: 'Rajasthan',         label: 'RJ', row: 2, col: 1 },
  { name: 'Haryana',           label: 'HR', row: 2, col: 2 },
  { name: 'Delhi',             label: 'DL', row: 2, col: 3 },
  { name: 'Uttar Pradesh',     label: 'UP', row: 2, col: 4 },
  { name: 'Arunachal Pradesh', label: 'AR', row: 2, col: 8 },
  { name: 'Gujarat',           label: 'GJ', row: 3, col: 1 },
  { name: 'Madhya Pradesh',    label: 'MP', row: 3, col: 2 },
  { name: 'Bihar',             label: 'BR', row: 3, col: 4 },
  { name: 'Sikkim',            label: 'SK', row: 3, col: 5 },
  { name: 'Assam',             label: 'AS', row: 3, col: 6 },
  { name: 'Nagaland',          label: 'NL', row: 3, col: 7 },
  // Central + east + north-east cluster
  { name: 'Dadra and Nagar Haveli and Daman and Diu', label: 'DD', row: 4, col: 0 },
  { name: 'Maharashtra',       label: 'MH', row: 4, col: 1 },
  { name: 'Chhattisgarh',      label: 'CG', row: 4, col: 2 },
  { name: 'Jharkhand',         label: 'JH', row: 4, col: 3 },
  { name: 'West Bengal',       label: 'WB', row: 4, col: 4 },
  { name: 'Meghalaya',         label: 'ML', row: 4, col: 5 },
  { name: 'Manipur',           label: 'MN', row: 4, col: 6 },
  { name: 'Goa',               label: 'GA', row: 5, col: 1 },
  { name: 'Telangana',         label: 'TG', row: 5, col: 2 },
  { name: 'Odisha',            label: 'OD', row: 5, col: 3 },
  { name: 'Tripura',           label: 'TR', row: 5, col: 5 },
  { name: 'Mizoram',           label: 'MZ', row: 5, col: 6 },
  // Peninsular south
  { name: 'Karnataka',         label: 'KA', row: 6, col: 1 },
  { name: 'Andhra Pradesh',    label: 'AP', row: 6, col: 2 },
  { name: 'Lakshadweep',       label: 'LD', row: 7, col: 0 },
  { name: 'Kerala',            label: 'KL', row: 7, col: 1 },
  { name: 'Tamil Nadu',        label: 'TN', row: 7, col: 2 },
  { name: 'Puducherry',        label: 'PY', row: 7, col: 3 },
  { name: 'Andaman and Nicobar Islands', label: 'AN', row: 8, col: 4 },
];

/** Outline mode the moment a boundary file has been generated, tiles
 *  until then. The switch is data-driven rather than a flag, so nothing
 *  needs editing here when the GeoJSON lands — run the converter and
 *  rebuild.
 *
 *  Tile labels are preserved across the switch: the converter derives
 *  its own short codes, but the hand-tuned ones here read better
 *  ("BNU" over "BU"), so they win where the names match. */
const TILE_LABELS = new Map(INDIA_TILES.map((t) => [t.name, t.label]));

export const INDIA_LAYOUT: MapLayout = BOUNDARY_SHAPES.length > 0
  ? {
      id: 'india-states',
      label: 'India — States & Union Territories',
      rows: 1,
      cols: 1,
      viewBox: BOUNDARY_VIEWBOX,
      shapes: BOUNDARY_SHAPES.map((s) => ({
        ...s,
        label: TILE_LABELS.get(s.name) ?? s.label,
      })),
    }
  : {
      id: 'india-states',
      label: 'India — States & Union Territories',
      rows: 9,
      cols: 10,
      shapes: INDIA_TILES,
    };

/* ── Karnataka: police geography, not revenue geography ───────────────
 * KARNATAKA_DISTRICTS mixes 31 revenue districts with 5 city police
 * commissionerates (Bengaluru City, Mysuru City, Hubli-Dharwad,
 * Mangaluru City, Belagavi City). That is deliberate — it mirrors what
 * `police_stations` uses and what the Branch District dropdown writes.
 * Each commissionerate gets its own tile beside its parent district,
 * because "Bengaluru City" and "Bengaluru Urban" are genuinely
 * different buckets in this data and merging them would hide a real
 * distinction.
 */
const KARNATAKA_TILES: MapShape[] = [
  // North — Kalyana Karnataka + northern Bombay Karnataka
  { name: 'Belagavi',      label: 'BGM', row: 0, col: 2 },
  { name: 'Vijayapura',    label: 'BJP', row: 0, col: 3 },
  { name: 'Bidar',         label: 'BDR', row: 0, col: 5 },
  { name: 'Belagavi City', label: 'BGC', row: 1, col: 2, note: 'City commissionerate' },
  { name: 'Bagalkot',      label: 'BGK', row: 1, col: 3 },
  { name: 'Kalaburagi',    label: 'KLB', row: 1, col: 4 },
  { name: 'Yadgir',        label: 'YDG', row: 1, col: 5 },
  // Northern midlands + coast
  { name: 'Uttara Kannada', label: 'UK', row: 2, col: 1 },
  { name: 'Dharwad',        label: 'DWD', row: 2, col: 2 },
  { name: 'Gadag',          label: 'GDG', row: 2, col: 3 },
  { name: 'Koppal',         label: 'KPL', row: 2, col: 4 },
  { name: 'Raichur',        label: 'RCR', row: 2, col: 5 },
  { name: 'Hubli-Dharwad',  label: 'HBL', row: 3, col: 2, note: 'City commissionerate' },
  { name: 'Haveri',         label: 'HVR', row: 3, col: 3 },
  { name: 'Vijayanagara',   label: 'VJN', row: 3, col: 4 },
  { name: 'Ballari',        label: 'BLR', row: 3, col: 5 },
  // Central
  { name: 'Udupi',          label: 'UDP', row: 4, col: 1 },
  { name: 'Shivamogga',     label: 'SMG', row: 4, col: 2 },
  { name: 'Davanagere',     label: 'DVG', row: 4, col: 3 },
  { name: 'Chitradurga',    label: 'CTD', row: 4, col: 4 },
  { name: 'Dakshina Kannada', label: 'DK',  row: 5, col: 1 },
  { name: 'Chikkamagaluru',   label: 'CKM', row: 5, col: 2 },
  { name: 'Tumakuru',         label: 'TMK', row: 5, col: 3 },
  { name: 'Chikkaballapur',   label: 'CKB', row: 5, col: 5 },
  // South
  { name: 'Mangaluru City',   label: 'MNC', row: 6, col: 1, note: 'City commissionerate' },
  { name: 'Hassan',           label: 'HSN', row: 6, col: 2 },
  { name: 'Bengaluru Rural',  label: 'BNR', row: 6, col: 3 },
  { name: 'Bengaluru Urban',  label: 'BNU', row: 6, col: 4 },
  { name: 'Kolar',            label: 'KLR', row: 6, col: 5 },
  { name: 'Kodagu',           label: 'KDG', row: 7, col: 1 },
  { name: 'Mandya',           label: 'MDY', row: 7, col: 2 },
  { name: 'Ramanagara',       label: 'RMN', row: 7, col: 3 },
  { name: 'Bengaluru City',   label: 'BNC', row: 7, col: 4, note: 'City commissionerate' },
  { name: 'Mysuru',           label: 'MYS', row: 8, col: 2 },
  { name: 'Mysuru City',      label: 'MYC', row: 8, col: 3, note: 'City commissionerate' },
  { name: 'Chamarajanagar',   label: 'CMR', row: 8, col: 4 },
];

export const KARNATAKA_LAYOUT: MapLayout = {
  id: 'karnataka-districts',
  label: 'Karnataka — Districts & City Commissionerates',
  rows: 9,
  cols: 7,
  shapes: KARNATAKA_TILES,
};
