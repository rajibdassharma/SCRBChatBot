# UI / UX Standards — CyberFraud Portal

The conventions this app already follows. Written down so new screens
match the existing ones by default, and so the reasoning behind the
non-obvious choices survives.

**Where a rule was derived by measurement rather than taste, the
measurement is quoted.** Colour in particular is computable — several
choices here reversed an initial instinct once validated, and the
numbers are recorded so nobody re-litigates them from memory.

---

## 1. Colour

### 1.1 Brand

| Token | Value | Used for |
|---|---|---|
| `--ksp-navy` | `#0b2c4a` | Primary ink, table headers, active tab, primary buttons |
| `--ksp-yellow` | `#ffd400` | Text on navy, active-tab underline, section rules |
| `--ksp-red` | — | Page subtitles, warnings |
| Sign Out red | `#c62828` | Sign Out button, sidebar section headings |

Sign Out red lives in one constant (`SIGNOUT_RED` in `Sidebar.tsx`) and
is shared by the button and the section headings, so "same colour as
Sign Out" stays true if either is restyled.

### 1.2 Account types

| Type | Colour | |
|---|---|---|
| Victim | `#EF4444` | bright red |
| Mule | `#8b1919` | dark red — offender |
| Non-Mule | `#0b2c4a` | navy — neutral / unknown |

Validated all-pairs on white: worst CVD ΔE 11.1 (protan), worst
normal-vision ΔE 23.0. **PASS.**

Non-Mule was blue-700 (`#1d4ed8`) until 2026-08-02 — a third hue that
appeared nowhere else. Navy matches the FIR dashboard's navy/red pair
and the pill already used in the drill-down panel.

> **Known inconsistency.** The account-type *pill* in
> `AccountsPsDetailPanel` renders Victim in green (`#0a6b28`) while
> charts use red. Aligning charts to green is **not** an option:
> green against Mule red measures ΔE 3.9 under deuteranopia — one
> colour to roughly 1 in 12 men. If the two are ever unified, move the
> pill to red, not the chart to green.

### 1.3 Sequential (heat maps, choropleths)

```
RAMP = ['#fbd5d1', '#f0928a', '#cf4034', '#8b1919']   // light -> dark
COLOR_EMPTY = '#d4d4ce'                               // no data
```

**Four steps, not five** — a measured limit, not a style choice. A
single-hue ramp spanning L 0.42–0.93 has finite perceptual room: at
five steps adjacent gaps fall to ΔE ~12, under the ΔE 15
normal-vision floor. At four, the worst adjacent pair is ΔE 16.5
normal / 14.8 simulated deuteranopia.

The darkest step is the Mule colour, so "hottest region" and "Mule"
are the same red app-wide.

`COLOR_EMPTY` is a neutral grey deliberately **outside** the ramp, so
"none" never reads as "a little". It sits at ~1.45:1 on white; it was
`#f1f1ef` (1.13:1) until zero-count regions started dissolving into
the background and losing their borders.

**Ink flips at step 3.** Navy scores 10.55 / 6.23 on steps 0–1, white
4.73 / 9.33 on steps 2–3. Every label clears 4.5:1.

### 1.4 Categorical (pie / multi-series)

```
['#2a78d6','#eb6834','#1baf7a','#eda100','#e87ba4','#008300','#4a3aa7']
```

Fixed order, assigned in sequence, never cycled.

**Do not substitute the app's accent colours here.** Validated, they
FAIL: navy, purple and dark red fall outside the lightness band, and
navy and teal drop under the chroma floor — they render as grey.

Three slots sit under 3:1 contrast, which obliges **visible labels or
a table view** as relief. The pie legend list (name, %, count) is that
relief; don't remove it.

### 1.5 Diverging (signed change)

Red `#8b1919` for a rise, navy `#0b2c4a` for a fall. Deuteranopia
ΔE 11.1.

**Not red/green** — that pair measures ΔE 3.9 and is the single most
common accessibility failure in dashboards. Direction and the signed
label carry the meaning anyway; colour is the third encoding.

### 1.6 Rule

> **Never colour nominal bars by their own value.** Bar length already
> encodes magnitude; colouring by it spends the identity channel
> re-encoding what the reader can already see. One hue for the series.

---

## 2. Layout

### 2.1 Cards

```js
{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)',
  boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }   // + rounded-2xl, p-4
```

KPI tiles add `borderTop: 4px solid <accent>`.

### 2.2 Dashboard page skeleton

```
Title + subtitle
Filter bar (date window, scope, type)   <- applies to ALL tabs
Tab bar                                  <- navy fill, yellow text, yellow underline
Tab content
```

Filters sit **above** the tab bar. They scope every tab, and moving
them per-tab makes controls jump as you switch.

### 2.3 Tab naming

`Overview` · `PS Ranking View` · `Map View` · `Crime-Type View`

Overview first, then the detailed table it summarises, then analytical
views.

### 2.4 Side by side

Two panels per row only when both are readable at half width. A time
series takes 2/3 and a pie 1/3 (`lg:grid-cols-3` + `col-span-2`) — a
line chart needs horizontal room, a pie does not.

A wide table (crime type × district) is **full width**. Pairing it
forced horizontal scrolling and, worse, tempted truncation.

Cards in a grid row stretch to the tallest. Give a shorter card
`flex flex-col` with a `flex-1 flex items-center` body so its content
centres rather than pinning to the top over a pool of whitespace.

### 2.5 Actions

Export buttons sit **inside** the card, directly above the column
headers of the table they export, right-aligned — the action next to
its object. Gate them to the tab that shows that table.

---

## 3. Tables

- Header: navy background, yellow text, `text-xs uppercase font-bold`
- Sortable headers: click to sort, click again to reverse; stable
  tiebreak so equal values don't reshuffle between renders
- **Zero rows stay visible.** A silent police station is the finding;
  omitting it hides the row worth asking about. Show `0` in red
- Right-align numbers, `toLocaleString('en-IN')` throughout
- Money short-forms as Cr / L / k — how the numbers are spoken in a
  review meeting

### 3.1 Pagination

**25 rows per page.** Above the table: `showing 1–25 of 312 accounts`.
Pager below with First / Prev / 5 numbered pages / Next / Last.

- Hide the pager entirely on a single page
- Clamp the page index — changing a filter can shrink the result set
  while the index still points past the end
- **Exports are never paginated.** The download is the whole dataset,
  not the page being viewed
- Reset to page 1 when the underlying query changes

---

## 4. Charts

Recharts for standard charts; hand-written SVG for maps (no mapping
library — the server has no CDN reachable, and a choropleth is a fill
and a tooltip).

### 4.1 Choosing the form

| The question | The form |
|---|---|
| How many of each? | Ranked horizontal bars, biggest first |
| How does it split? | Stacked bar — **never** a bare percentage |
| Over time? | Line, zero-filled so gaps read as inactivity |
| Share of a whole? | Donut, top 7 + aggregated "Other" |
| Where? | Choropleth |
| Two measures per category? | Grouped bars, **not** a scatter |

**Scatter plots are avoided.** Two continuous axes plus bubble size is
three encodings to decode before learning anything; twice replaced
with paired or stacked bars that said the same thing at a glance.

### 4.2 Percentages hide their denominator

100% of 3 cases outranks 40% of 200. Stack the parts instead — bar
length is the workload, the fill is the outcome. This also removes the
need for arbitrary "minimum N" floors, which only ever existed to
suppress silly percentages.

Where a ranking is meant to surface failure, order by **absolute
unresolved count**, not by rate — that combines volume and failure
into one ordering.

### 4.3 Labels

Full names in tooltips and tables; short codes on the chart. Estimate
text width (≈0.52em per glyph) against the space available and degrade:
full name → two lines → short code → number only → nothing.

For map labels the space is the polygon **at the label row**, measured
by ray-casting — not the bounding box, which overstates by up to 76%
on a diagonal region and pushes text over the border.

### 4.4 Every chart states its own blind spot

- Rows with no location → amber banner: *"N of M not on the map"*,
  naming unrecognised values
- No arrests recorded → *"reads as missing data, not a clearance rate
  of zero"*
- A truncated axis → an explicit `Other` column, and a `Total` read
  from the **same array** the companion chart uses

> A top-N cut once made two panels on the same screen disagree
> (7 in the bar chart, 5 across the grid). Totals must derive from the
> authoritative array, never from summing what happens to be visible.

---

## 5. Maps

- Outline mode when a boundary file exists, tile grid otherwise — a
  data-driven switch, no flag
- White borders between regions; regions stroked in their own fill
  where internal sub-borders would otherwise show
- Label anchor is the **pole of inaccessibility**, not the centroid —
  a centroid falls outside a concave region (Arunachal) or into water
  between islands (Andaman)
- Legend is a vertical scale left of the map, darkest at top: on a
  vertical axis "more" reads upward
- Region name folding is **display-time only**. Aliases map stored
  values onto merged shapes; nothing is rewritten and the picklist is
  untouched

> Boundary data for an Indian government portal is not a neutral
> technical choice. J&K, Ladakh and Arunachal depiction is regulated.
> The current file is a community source pending KSRSAC / Survey of
> India sign-off, recorded in the generated file headers.

---

## 6. Interaction

- Tooltips follow the cursor and flip near edges so they never clip
- Hover shows the full breakdown; the chart shows the headline
- Toasts (`sonner`) for outcomes; never for routine loads
- Destructive or slow actions disable while in flight and say so
  (`Generating…`)

---

## 7. Empty, loading, error

| State | Treatment |
|---|---|
| Loading | Centred italic text, never a spinner over stale data |
| Empty | Say *why* it's empty and what would change it |
| Partial | Amber banner quantifying what's missing |
| Failed | Toast with the message; keep whatever already loaded |

`Promise.allSettled`, not `Promise.all` — one failing panel must not
blank a page that already has data.

---

## 8. Access

- `admin` sees its own PS; `super_admin` sees cross-PS
- Filter by role **before** grouping, or a non-admin gets a section
  heading with nothing under it
- Hide a tab that would hold one row for the viewer rather than
  showing a comparison of one

> `/daily-work/dashboard` shipped with no `super_admin` branch at all
> — the only module without one — so HQ saw zeros while every station
> had data. When adding a dashboard, check the cross-PS path exists.

---

## 9. Test fixtures never appear in a dashboard

`TestDistrict` / `Test PS` exist so an administrator can verify the app
end to end without touching a real station's data. They are real rows
— login, data entry and their own reports keep working — but they are
excluded from **every** dashboard figure: KPI cards, tables, charts,
maps, rankings and the Excel/PDF exports alike.

Applied in the backend (`api/test_scope.py`), never in the frontend.
Filtering on the client would leave a KPI card counting rows the table
beneath it had dropped — see §10.

Configurable per environment via `CFDSR_TEST_UNITS` /
`CFDSR_TEST_STATIONS`. Set either to empty to disable the exclusion,
which is what a dev box wants when the fixture is the only data there.

> **Known consequence.** Signed in AS Test PS, dashboards will be
> empty — the fixture is filtered even from its own view. Data entry
> still works. If verifying dashboards as Test PS matters, the
> exclusion needs to skip when the viewer IS the test station.

## 10. Numbers must reconcile

The rule behind several of the above:

> **Two numbers describing the same thing, on the same screen, must
> come from the same array.**

Derive a total from the authoritative source, not by summing visible
cells. Apply a filter to every derived figure, including secondary
columns like *Yesterday* — filtering one and not the other silently
compares two populations side by side.

Exports must honour the on-screen filter. A filtered table with an
unfiltered download is the kind of mismatch that gets noticed in a
briefing.
