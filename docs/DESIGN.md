# Design system and screens

How Pravah looks, moves and behaves. It applies to every screen and is part of the product specification (`SPEC.md` §14).

---

## 0. Using this document

Build in this order:

1. Tokens (§3)
2. Components (§4)
3. App shell (§6)
4. Screens (§7)
5. Motion (§5) and access flows (§8, §9)

The `/styleguide` route renders every token and every component state in light and dark. Review it before building screens.

Rules:

- No component file contains a raw color, font size, spacing value or shadow. Everything comes from tokens, and lint enforces this.
- Primitives are built on Radix UI. If a component library such as shadcn/ui is used, its primitives can stay, but its default theme is replaced entirely by these tokens.
- Every screen ships with screenshots at 1440 and 390 px, in light and dark, taken on seeded demo data.

---

## 1. Design direction

**Concept: the control-room instrument panel.** Data moves through pipes; the console is the gauge wall. It should feel precise, quiet and dense but legible. Color is for state, not decoration.

Principles:

1. **Color means status.** Green, amber, red and blue appear only for health and run state. Everything else is ink on paper, plus one accent (Pravah teal) for actions, links and focus.
2. **One memorable element: the tenant health board** on Overview. It gets the boldness: the live flow animation, the status glyphs, and the strongest type. Everything around it stays quiet.
3. **Hierarchy comes from type and space, not boxes.** Not every block is a card. Use panels only where content is a real group, and separate sections with whitespace and hairlines.
4. **Numbers are first-class.** Tabular figures everywhere, units always shown, no fake precision.
5. **Motion only shows change.** Something moves only because it changed or because you touched it.

---

## 2. Patterns we avoid

These make an interface feel generic and harder to read. Design review checks every screen against this list:

- [ ] Identical rounded cards with the same soft shadow on everything. Panels get borders, not shadows; only overlays get shadows.
- [ ] One border radius used for everything. Use the radius scale in §3.
- [ ] Gradient backgrounds, gradient text, glows, glassmorphism, blurred blobs.
- [ ] Emoji anywhere in the UI or copy.
- [ ] An icon in front of every heading or label. Use icons only where they carry meaning: status, actions, navigation.
- [ ] Badges or pills on things that aren't a status or a count.
- [ ] ALL-CAPS tracked labels and eyebrows above headings.
- [ ] Meta strings joined with middle dots ("Acme · L · 2h SLA"). Use a definition list or labeled fields.
- [ ] "→" or "»" appended to links and buttons.
- [ ] Centered empty states with a giant icon and "Oops!" or "Nothing here yet!".
- [ ] Generic copy: "Welcome back!", "Seamless", "Powerful insights", "Get started", "Unlock". Use the copy rules in §10.
- [ ] Hover lifts or scale on cards; fade-and-slide-up on every section at page load.
- [ ] Rainbow chart palettes, or red and green used for things that aren't status.
- [ ] Mixed spacing (p-4 next to p-5 next to p-6), misaligned panel edges, headers that don't line up.
- [ ] Placeholder text used instead of labels.
- [ ] Fake precision (98.9472%) and mixed units (min, m, mins and minutes on the same screen).
- [ ] Full-page centered spinners. Use skeletons in place.
- [ ] Tooltips that repeat the visible label.
- [ ] Inter, Geist or the system default as the brand font.

---

## 3. Design tokens

All tokens live in `frontend/src/styles/tokens.css` as CSS variables and are mapped into Tailwind (`theme.extend`). Components use only token-backed classes.

### 3.1 Color: light (default)

| Token | Hex | Use |
|---|---|---|
| `--paper` | `#F3F5F4` | App background |
| `--surface` | `#FFFFFF` | Panels, tables, inputs |
| `--sunken` | `#EEF2F0` | Row hover, code blocks, tracks |
| `--line` | `#DDE3E0` | Hairlines, panel borders |
| `--line-strong` | `#C6CFCB` | Input borders, dividers that need contrast |
| `--ink-900` | `#13201D` | Primary text (16.8:1 on surface) |
| `--ink-600` | `#465450` | Secondary text (7.9:1) |
| `--ink-500` | `#5C6A66` | Meta text, axis labels (5.7:1) |
| `--ink-400` | `#7D8B86` | Disabled and decorative only (3.6:1; never for body text) |
| `--accent` | `#0B6B75` | Pravah teal: primary buttons, links, focus, selection (6.2:1) |
| `--accent-soft` | `#DFF0F1` | Selected rows, active nav, info callouts |
| `--ok` / `--ok-soft` | `#1D7A49` / `#E2F1E8` | Success, healthy |
| `--warn` / `--warn-fill` / `--warn-soft` | `#8F5B00` text / `#D99A1E` fills / `#FBEFD5` | Degraded, stuck, acknowledged |
| `--bad` / `--bad-soft` | `#B3302A` / `#FAE3E0` | Failed, down, critical |
| `--run` / `--run-soft` | `#2B58C2` / `#E4EBFB` | Running, syncing, onboarding |
| `--idle` / `--idle-soft` | `#8C9894` / `#EDF0EF` | Queued, paused, not used |

### 3.2 Color: dark (and the TV default)

| Token | Hex |
|---|---|
| `--paper` | `#0B1311` |
| `--surface` | `#111B18` |
| `--sunken` | `#16221E` |
| `--line` / `--line-strong` | `#213029` / `#2E3F38` |
| `--ink-900` / `--ink-600` / `--ink-500` / `--ink-400` | `#E2EAE7` / `#A3B1AC` / `#8A9893` / `#62716C` |
| `--accent` / `--accent-soft` | `#3FAEB8` / `#12302F` (button text on accent: `#062023`) |
| `--ok` / `--ok-soft` | `#4CC283` / `#16301F` |
| `--warn` / `--warn-soft` | `#E6A740` / `#33270F` |
| `--bad` / `--bad-soft` | `#F06C62` / `#3A1A18` |
| `--run` / `--run-soft` | `#7FA2FF` / `#1A2645` |
| `--idle` / `--idle-soft` | `#62716C` / `#1C2723` |

Every text and status pair above meets WCAG AA (4.5:1 or better). Keep it that way if you tweak a value.

### 3.3 Chart palette (not status)

Use this for series that aren't status, such as sources, pipelines and tenants: `#0B6B75` teal, `#4D5BB5` indigo, `#9A7B2F` ochre, `#8A4F7D` plum, `#5D6B78` slate. Dark variants: lighten each by about 25%.

- Never use status colors for non-status series.
- Don't use more than 5 series on one chart; group the rest as "Other".

### 3.4 Typography

- **UI font:** IBM Plex Sans, weights 400, 500 and 600. Self-host it with `@fontsource/ibm-plex-sans` so the offline demo still works.
- **Code font:** IBM Plex Mono, weights 400 and 500 (`@fontsource/ibm-plex-mono`). Use it only for logs, run ids, connection ids, SQL and the error message block. Never use it for labels or numbers in the UI.
- Fallback stack: `"IBM Plex Sans", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`.
- Turn on `font-variant-numeric: tabular-nums` globally.

| Token | Size / line height | Weight | Use |
|---|---|---|---|
| `text-display` | 32 / 40 | 600 | TV KPI values only |
| `text-title` | 24 / 32 | 600, -0.01em | Page titles |
| `text-heading` | 16 / 24 | 600 | Panel titles |
| `text-body` | 14 / 20 | 400 | Default |
| `text-label` | 13 / 18 | 500 | Buttons, form labels, table headers |
| `text-meta` | 12 / 16 | 400 | Timestamps, helper text, axis labels |
| `text-kpi` | 24 / 32 | 600 | KPI values |

Sentence case everywhere. Never use all caps.

### 3.5 Spacing and layout

- **Spacing scale:** a 4 px base, using 4, 8, 12, 16, 20, 24, 32, 40, 48 and 64. Nothing else.
- **Page padding:** 24 px on desktop, 16 px at 390 px. Content max width is 1440 px; TV mode has none.
- **Grid:** 12 columns with 16 px gutters. Every panel spans a whole number of columns (12, 8+4, 6+6, 4+4+4). **Panel edges must line up vertically across rows.**
- **Vertical rhythm:**
  - 24 px from page title to the first section.
  - 16 px between sections and between panels.
  - 12 px from a panel header to its content.
- **Panel padding:** 16 px; 20 px for panels wider than 6 columns.
- **Control heights:** 32 px default, 28 px small (tables and toolbars), 40 px large (sign-in, wizard footer). Inputs, selects and buttons in the same row are always the same height.
- **Icons:** 16 px, 1.75 px stroke, from one set (lucide). 8 px gap to their label.
- **Tables:**
  - Row height 40 px (32 px in compact density), cell padding 12 px horizontal.
  - Numbers align right, text aligns left, and headers align with their column's content.

### 3.6 Radius, elevation and layers

- **Radius:**
  - 4 px for checkboxes and tags.
  - 6 px for buttons, inputs and menus.
  - 10 px for panels.
  - 12 px for dialogs and drawers.
  - Fully round only for status dots and avatars.
- **Elevation:** panels have none, just a 1 px `--line` border. Only overlays (menus, popovers, dialogs, toasts) get the one shadow token: `0 8px 24px rgb(0 0 0 / 0.12), 0 1px 2px rgb(0 0 0 / 0.08)`. In dark mode, use a border plus a 30%-black shadow.
- **z-index tokens:** header 20, drawer 40, dialog 50, popover 60, toast 70, tooltip 80.

### 3.7 Motion tokens

| Token | Value | Use |
|---|---|---|
| `--dur-micro` | 80 ms | Hover, press |
| `--dur-fast` | 140 ms | Menus, popovers, tooltips |
| `--dur-base` | 200 ms | Drawers, dialogs, toasts |
| `--dur-slow` | 320 ms | Number tweens, chart transitions |
| `--ease-standard` | `cubic-bezier(0.2, 0, 0, 1)` | Entering and moving |
| `--ease-exit` | `cubic-bezier(0.4, 0, 1, 1)` | Leaving |

---

## 4. Components

Built on Radix UI primitives (`@radix-ui/react-*`) and styled only with tokens. Show every component on `/styleguide` in every state: default, hover, focus-visible, active, disabled, loading, error. Show each in light and dark.

### 4.1 Buttons

| Variant | Look | Use |
|---|---|---|
| Primary | Accent fill, white text | At most one per view: the main action ("Start resync", "Continue") |
| Secondary | Surface fill, `--line-strong` border, ink-900 text | Most actions |
| Ghost | No border, ink-600 text, sunken on hover | Toolbars, table rows |
| Danger | Surface fill, `--bad` text and border | Pause tenant, disable user. Always confirmed |
| Icon | 32×32 ghost, tooltip required | Copy, more (⋯), close |

States:

- **Hover:** darken the fill by 6%, over `--dur-micro`.
- **Active:** darken by 10%. No scale or transform.
- **Focus-visible:** a 2 px accent ring with a 2 px offset.
- **Disabled:** 45% opacity and `cursor: not-allowed`. Always show a tooltip with the reason, e.g. "Requires the operator role" or "A resync is already running".
- **Loading:** a spinner replaces the leading icon; the label and width stay the same.

Rules:

- Labels start with a verb and use sentence case ("Retry run", not "Retry"). The same word carries through the whole flow: the button "Start resync" leads to the toast "Resync started".

### 4.2 Inputs and forms

- Labels go above the field (13/500), with helper text below (12, ink-500). Error text replaces the helper and has an icon. The field gets a `--bad` border and `aria-invalid`.
- Never use a placeholder as the label. Placeholders show example values only.
- **Password fields:** a show/hide toggle, and a caps-lock warning.
- **Secret reference field:** a prefix select (`vault:`, `aws-sm:`) next to the path input, with inline validation.
- **Number fields:** show the unit inside the field on the right ("min").
- Validate when the user leaves a field and on submit, not on every keystroke.

### 4.3 Select, combobox, multi-select (dropdowns)

Replace every native `<select>`:

- **Select:** for up to 8 options. A 32 px trigger with a chevron. The menu matches the trigger width (min 180 px), with a check mark on the selected option.
- **Combobox:** for tenants, error classes, and any list over 8 items. Type to filter, highlight the match, and use the arrow keys.
- **Multi-select:** for the status and pipeline filters. Selected values show as removable chips in the trigger; past 2 chips, show "+3". It has a "Clear" option.
- **Menus:**
  - Max height 320 px with internal scroll.
  - 8 px padding, 32 px items, 6 px radius.
  - Open with a fade plus scale from 0.98 to 1, growing from the trigger, over `--dur-fast`; close faster.
- **Row action menu (⋯):** Radix DropdownMenu. Destructive items sit last, in `--bad`, after a separator.

### 4.4 Tooltips and popovers

- Tooltips open after 300 ms, use 12 px text, max 280 px wide, and never repeat the visible label.
- Popovers are for interactive content, like the active-syncs list and filter builders. They close on Escape and on outside click, and focus returns to the trigger.

### 4.5 Dialogs and drawers

- **Dialogs:** only for confirmations and short forms.
  - Confirmation copy: the title says what happens ("Pause Acme Retail?"), the body says the consequence, and the buttons are "Pause tenant" and "Cancel".
  - For resync and pause, the user types the tenant id to confirm.
- **Drawer:** 480 px from the right, 100% wide on mobile. Use it for quick looks (a run, an incident, an error group, a check editor) so the user keeps their place in the list. It always has "Open full page".

### 4.6 Toasts

- Bottom-right on desktop, bottom-center on mobile; at most 3 stacked.
- Auto-dismiss after 5 s, except errors, which stay until dismissed.
- Optional action, e.g. "View run" or "Undo" where undo is safe.
- Variants: success, info and error, each with an icon. No emoji.

### 4.7 Tables

- Sticky header. The first column is sticky when the table scrolls sideways.
- Sortable headers show a sort arrow, plus `aria-sort`.
- Hover row: `--sunken`. Selected row: `--accent-soft`.
- Truncated text gets a full-text tooltip.
- **Pagination:** bottom-right, showing "1–25 of 312" with previous/next. Use a virtualized list instead of pages when the user is filtering more than 500 rows.
- **Density toggle** (comfortable or compact), remembered per user.
- **Column picker** on Runs.
- **Selection:** a checkbox column. Selecting rows shows a selection bar with the bulk actions ("Compare", "Acknowledge").

### 4.8 Status

- **StatusGlyph:** a 16 px shape plus color, so state is never conveyed by color alone.

  | State | Glyph |
  |---|---|
  | Success / healthy | Filled check |
  | Failed / down | Cross in a square |
  | Running | Ring with an animated arc (§5) |
  | Queued | Clock outline |
  | Degraded / stuck | Triangle |
  | Paused | Pause bars |
  | Not used | Dash |

- **StatusLabel:** the glyph plus a text label. Use it in tables and headers.
- **Pill:** only for statuses, severities and counts. Height 20 px, 12 px text, 4 px radius. A dot is optional, because the glyph already carries the state.

### 4.9 Data display

- **KPI:** a label (13, ink-600), a value (`text-kpi`), and a delta line (12): "up 0.6 pts from previous 24h". Color the delta by good or bad, not by direction. KPIs sit in one bordered strip with hairline dividers, not separate cards.
- **Definition list:** for metadata like owner, schema, SLA and connection ids. Labels are ink-500; values are ink-900. Values in mono only when they're ids.
- **Empty state:** left-aligned inside the panel. One 20 px line icon, one sentence saying what's missing, and one action. No illustrations.
- **Loading:** skeleton blocks with the content's exact dimensions, so nothing shifts when data arrives. Show a static `--sunken` block, plus a 1.2 s opacity pulse only when motion is allowed.
- **Error state:** what failed, what to do, and a "Try again" button. Name the service, e.g. "The API isn't responding."

### 4.10 Charts

Use one library for every chart, with one shared theme module.

- **Gridlines:** horizontal only, `--line` at 60%. No chart borders and no background fills.
- **Axes:** axis labels are 12 px ink-500. Units go in the axis label or in the tooltip header.
- **Tooltips:** styled like popovers, with tabular numbers, a crosshair on time series, and status glyphs where relevant.
- **Heights:** 160 px for small charts, 220 px for standard, 280 px for the tenant timeline area.
- **Empty and loading** states render inside the chart area at the same height.
- **Heatmaps:** a single-hue sequential scale (the bad hue from 15% to 100%) with a visible legend.
- **Duration charts:** show a p25–p75 baseline band (accent at 12%) instead of a dashed median line, plus the run points.

---

## 5. Motion and live updates

Motion exists to show change. All of it switches off under `prefers-reduced-motion`; state changes still happen, instantly.

**Interactions**

- **Hover and press:** a color change only, over `--dur-micro`.
- **Menus, popovers and tooltips:** fade plus 0.98-to-1 scale from the trigger, over `--dur-fast`.
- **Drawers:** slide 24 px and fade over `--dur-base`. **Dialogs:** fade and scale.
- **Route changes:** no animated page transitions. The content swaps instantly, and skeletons cover loading.

**Live data**

- **Status change** on a board cell, table row or pill: a one-time 600 ms background settle from the new status's soft color to normal. That's how people notice that something changed.
- **KPI values:** count to the new value over `--dur-slow`. Tabular figures stop the digits jittering.
- **New activity feed items:** slide in 8 px and fade over `--dur-base`. The list must not jump: reserve the height or keep the scroll anchored.
- **No layout shift on live updates.** Measure it in e2e: CLS stays under 0.01 on Overview during a 60-second live session.

**Active syncs** (the signature motion)

- **FlowBar:** a 2 px bar along the bottom edge of every running pipeline cell, run row and sync indicator. A short accent dash travels left to right, looping every 1.6 s.
  - **Stuck runs:** the dash turns amber and slows to 4 s, and the cell shows "Stuck".
  - **Retrying:** the dash is dashed and broken.
- **Running glyph:** a ring with a rotating 90° arc, 1.2 s per turn.
- **Header "Active syncs" chip:** "4 syncing", with a mini FlowBar.
  - Clicking it opens a popover listing each running sync: tenant, pipeline, elapsed time against the usual time, and an estimated progress bar (elapsed ÷ median, capped at 95%, labelled "estimated").
  - Stuck syncs come first, marked amber.
  - Each row links to its run.
- **Live indicator in the header:**
  - Connected: "Live" with a slow 2 s pulse.
  - SSE dropped: switches to amber "Reconnecting…" and shows "Data as of 14:02", until it reconnects.
  - Never show "Live" while the connection is down.
- **Browser tab:**
  - The favicon gets a red dot while there's an open critical incident, and an amber dot for high.
  - The title is prefixed with the count, e.g. "(2) Overview".

---

## 6. App shell and layout

- **Sidebar:** 232 px wide, collapsible to a 64 px icon rail (remembered per user).
  - Groups, with sentence-case group labels (12 px, ink-500):
    - **Monitor:** Overview, Tenants, Runs, Errors, Freshness, Alerts
    - **Investigate:** Dependencies, Data quality, Activity
    - **Operate:** Onboard tenant
    - **Settings:** Platform, Administration
  - Active item: an `--accent-soft` background and ink-900 text at weight 500.
  - The Alerts count badge appears only for firing critical or high incidents.
- **Header:** 56 px, sticky. It holds the command/search trigger (with a "⌘K" hint), the global time range (segmented: 6h, 24h, 7d, custom), the Active syncs chip, the Live indicator, the environment badge, and the user menu.
  - **Page titles live in the page, not in the header.**
- **Environment badge:** from `ENVIRONMENT_NAME`.
  - Demo: teal outline, plus the demo banner (SPEC §13).
  - Staging: an amber badge and a 3 px amber stripe across the top of the app.
  - Production: no stripe; "Production" shows in the user menu only.
- **User menu:** name and email, role (read-only), theme (System, Light, Dark), time zone (Local or UTC), density, "Change password" (local auth only), and "Sign out".
- **Page header pattern** (the same on every page):
  - Breadcrumb (12 px) when the page is nested.
  - Title (`text-title`), with the status label inline where relevant.
  - A one-line description or status sentence.
  - Actions right-aligned and bottom-aligned with the title block.
- **Mobile, at 900 px and below:** the sidebar becomes a drawer behind a menu button, and the header keeps search, the active syncs chip and the user menu. Touch targets are at least 44 px. Tables become stacked rows (§7).

---

## 7. Screens

The layout and behavior of every screen. Screenshots use seeded demo data.

### 7.1 Sign-in
**Spec:**
- Left-aligned 400 px form column on `--paper`. Pravah product mark and name at the top, then the environment badge. No illustration and no marketing copy.
- **OIDC mode:** one primary button, "Sign in with {provider}", and no password fields.
- **Local mode:** email, password (show/hide, caps-lock warning), a "Forgot password?" link, and a 40 px primary "Sign in" button.
- **Demo mode:** a secondary "Explore the demo" button (read-only viewer).
- Errors appear inline above the button, for example "Email or password is incorrect.", and the same message is used for unknown emails.
- Footer: version and environment, 12 px, ink-500.

### 7.2 Overview
**Spec** (12-column layout):
- **Row 1:** page header with the one-sentence status (SPEC §2.1). Actions: "TV mode" (secondary) and "Onboard tenant" (primary).
- **Row 2:** a 6-KPI strip: Tenants (healthy, degraded and down in one value), Success rate, Failed runs, Data within SLA, Active syncs, Open incidents. Each has a delta.
- **Row 3:** Health board (8 columns) next to Incidents (4 columns: open incidents first, then live activity under a divider).
- **Row 4:** Runs over time (6 columns) next to Duration by pipeline (6 columns, with a p95 tick).
- **Row 5:** Recent failures table (12 columns).
- **Health board spec** (the signature element):
  - Rows 52 px. The tenant column is 200 px (name in 14/600 plus a health StatusLabel).
  - Four equal pipeline cells, at least 112 px wide. Each shows the StatusGlyph, a status word, and one secondary line ("12m ago", "for 31m", "Binlog purged").
  - Running cells carry the FlowBar.
  - The freshness column is a mini gauge with ticks at 75% and 100% of the SLA.
  - Problems sort to the top. Hovering highlights the row; clicking the row opens the tenant and clicking a cell opens that run.
  - Sticky header and tenant column.
  - Cells play the status-change settle animation from §5.

### 7.3 Tenants list
**Spec:**
- Search plus health filter chips (All, Down, Degraded, Healthy, Paused) with counts.
- Sortable table: Tenant, Health, Success 7d (with a sparkline), Within SLA, Failures, CDC avg, Last success per source, Owner, and a ⋯ menu (Open, Add maintenance window, Pause).
- Rows 48 px.

### 7.4 Tenant detail
**Spec:**
- **Header:** breadcrumb "Tenants / Acme Retail", the name plus a health StatusLabel, a definition list (Owner, Schema, SLA, Onboarded), and actions. Primary appears only when needed (e.g. "Start resync"); otherwise the actions are secondary ("Pause tenant", in a danger style with a confirm).
- **Incident banner** when an incident is open: the cause, how long it's been open, the "What to do" line, and the action. One banner per incident, not per alert.
- **Tabs, synced to the URL** (`?tab=`): Overview, Runs, Alerts, Quality, Config.
  - **Overview tab:** KPI strip, timeline, duration chart with the baseline band, and freshness by table.
  - **Timeline:** 28 px lanes and a "now" line. Maintenance windows shade the background and change markers appear as ticks on top. A hover tooltip card shows the run. Dragging across the timeline zooms the time range.

### 7.5 Runs explorer
**Spec:**
- **Filter bar:** tenant combobox, status multi-select, pipeline select, error class combobox, date range, and text search. Saved views go on the right.
- An active-filter chip row with "Clear all". Filters are kept in the URL.
- Virtualized table with a column picker and density toggle.
- Clicking a row opens the **run drawer** (status, timing against usual, error with hint, the last 30 log lines, actions, and "Open full run").
- Checkbox selection shows a selection bar with "Compare" (exactly 2 selected) and "Export".

### 7.6 Run detail
**Spec:**
- **Header:** breadcrumb "Acme Retail / Runs / MySQL CDC, 07:00", the title plus status, and actions (Retry run; "Start resync" when the position is lost). Both are role-gated and confirmed.
- A meta definition list.
- **Attempts strip:** a mini Gantt of the Airflow try and the Airbyte attempts, with failure points marked.
- **Error panel:** the message in a mono block with a copy button, then the "What to do" callout with a runbook link, then the failure origin and type.
- **Log viewer:**
  - Virtualized, with line numbers and level filter chips (All, Warn, Error).
  - Search with previous/next and a match count.
  - A wrap toggle and "Jump to first error".
  - Copy a link to a line, and download the redacted log.
- **Previous runs:** a duration bar chart colored by status, with the current run highlighted.
- **Mobile:** a sticky bottom action bar.

### 7.7 Run compare
**Spec:**
- Two aligned columns, with differing values highlighted in `--accent-soft`.
- A stream table showing record counts for both runs and the difference (signed, right-aligned).
- A log diff toggle (only lines in A, only lines in B).

### 7.8 Errors
**Spec:**
- **Group table:** severity StatusGlyph, class, normalized message (mono, one line, tooltip), runs, tenants (up to 3 chips plus "+N"), first and last seen, and a 7-day sparkline. A row opens the group drawer.
- **Charts:** failures by stage (horizontal bars in ink, with the highest in `--bad`), time to recover by tenant, and a heatmap with a legend and maintenance-window hatching.

### 7.9 Freshness
**Spec:**
- **Table** sorted by the share of SLA used. Columns: tenant, source, last CDC success, an SLA gauge with ticks at 75% and 100%, and compliance for 24h and 7d.
- **Volume anomalies:** a before-and-after mini bar with the percentage.
- **Schema changes:** neutral "+ column" / "− column" chips. These aren't status, so they're not colored.

### 7.10 Alerts and incidents
**Spec:**
- **Tabs:** Open, Acknowledged, Resolved, with counts.
- **Incident rows:** a severity StatusGlyph and label, title, cause, time open, assignee, and actions (Acknowledge, Resolve, ⋯).
- **Incident drawer:** a vertical timeline (fired, notified, acknowledged, resolved, and notes), with the assignee picker and notes box.
- **Rules:** table with on/off switches. Admins edit thresholds inline, with validation.
- **Channels:** table with a "Send test" button that shows the delivery result.
- **Silences and maintenance windows:** their own tab.

### 7.11 Onboarding wizard and progress
**Spec:**
- A numbered stepper (the steps really are a sequence).
- Form max width 720 px, two columns at 900 px and wider. Labels above, with helper text.
- **Pre-flight:** a live checklist of glyphs, with a "How to fix" expander on each failed check.
- **Review:** grouped summaries, each with an "Edit" link back to its step.
- **Progress:** a vertical step timeline with each step's duration. It survives leaving and returning to the page.
- Enter submits the current step.

### 7.12 Data quality
**Spec:**
- **Checks table:** name, table, type, schedule, last result glyph, a pass/fail strip for the last 20 results, next run, and "Run now" (role-gated).
- The check editor opens in a drawer.

### 7.13 Dependencies
**Spec:**
- **Layout:** left to right (source, Airbyte connection, DAG/task, warehouse table), matching how people think about the pipeline.
- **Nodes:** each asset type gets its own shape and icon.
- **Edges:** solid for configured links, dashed for observed ones, with a visible legend.
- Selecting a node highlights its impacted path and opens a side panel.
- Zoom and fit controls, plus a **List view** alternative for accessibility.

### 7.14 Activity
**Spec:**
- Grouped by day, with sticky date headers.
- Each row has a 64 px tabular time gutter, a type glyph, a plain sentence ("You acknowledged 'Acme Retail: MySQL CDC position lost'"), and a link to the item.
- Filters for type, tenant and actor.

### 7.15 Platform
**Spec:**
- **Components table:** status, detail, and a 24-hour uptime strip (96 segments).
- Pool usage bars, the import error history, and collector poll stats.
- Console version, build and environment.

### 7.16 Administration
**Spec:** tabs for Users, Roles, Alert rules, Channels, Runbooks, Maintenance, Settings and Audit log. Users and Roles follow §8. Audit log: filterable, exportable, read-only styling.

### 7.17 Profile and account
**Spec:**
- Name, email and role (read-only).
- Preferences: theme, time zone, density.
- "Change password" (local auth).
- **Active sessions:** device, location (if known), last seen, and "Sign out of this session" / "Sign out everywhere else".

### 7.18 System pages (403, 404, 500, API down)
**Spec:** a left-aligned panel saying what happened and what to do next. For example, 403: "You don't have access to Administration. Ask an admin to change your role." followed by the list of admins.

### 7.19 TV mode
**Spec:**
- Dark theme by default. Hide the sidebar and header controls.
- Larger type: 40 px KPI values, 64 px board rows, a 16 px base.
- Show a clock and "Updated 12s ago". The Overview and Incidents screens can auto-rotate (off by default).
- Design layouts for 1920×1080 and 1280×720.

### 7.20 Mobile (390 px)
**Spec:**
- The Overview health board becomes **tenant cards**: name and health on top, four compact pipeline chips, and the freshness gauge.
- Other tables become stacked rows (primary value on top, two secondary values below).
- Sticky action bars on Run and Tenant pages.
- No horizontal scrolling at page level on any page.

---

## 8. RBAC

### 8.1 Permission matrix

The server enforces this on every endpoint. The UI only reflects it.

| Capability | Viewer | Operator | Admin |
|---|:-:|:-:|:-:|
| See monitoring and investigation pages | ✓ | ✓ | ✓ |
| Export CSV, save private views | ✓ | ✓ | ✓ |
| Acknowledge, resolve, assign incidents and add notes | | ✓ | ✓ |
| Retry run | | ✓ | ✓ |
| Start resync, pause or resume tenant (typed confirm) | | ✓ | ✓ |
| Maintenance windows and silences | | ✓ | ✓ |
| Run a quality check now | | ✓ | ✓ |
| Onboard tenant | | ✓ | ✓ |
| Edit alert rules, channels, runbooks, quality checks | | | ✓ |
| Manage users and roles; send password reset links | | | ✓ |
| View the audit log | | | ✓ |
| Reset the demo | | | ✓ |

Phase 2, not now: scoping operators to particular tenants (e.g. an account team).

### 8.2 How the UI behaves

- **Pages** a role can't use are hidden from navigation and the command palette. Opening the URL directly shows the 403 page.
- **In-context actions** a role can't use stay visible but disabled, with the tooltip "Requires the operator role". People learn the system that way.
- **Administration → Roles** shows the matrix read-only for the built-in roles.
- The role shows in the user menu.
- **"View as role":** admins can preview the UI as a viewer or operator. It's read-only, shows a persistent banner ("Viewing as viewer. Exit"), and is audited.
- **OIDC mode:** a user's role comes from their group mapping. The Users page shows the mapped group and marks the role "Managed by your identity provider", and roles can't be edited in the console.

### 8.3 Users page (local auth mode)

- **Table:** name, email, role, status (Active, Invited, Disabled), last sign-in, active sessions, and a ⋯ menu.
- **Invite user:** email and role. Sends a one-time link that expires after 72 hours. The invitee sets their password on the same screen as password reset (§9).
- **Change role:** a confirm dialog, then an audit entry.
  - Nobody can change their own role.
  - The last remaining admin can't be demoted or disabled.
- **Disable user:** revokes all their sessions immediately. **Re-enable** works, and so does **Revoke sessions**.
- **Send password reset link:** admins never see or set passwords.

### 8.4 Tests

- An API test for every row of the matrix, run for every role (allowed returns 2xx; denied returns 403 and writes an audit entry).
- e2e: a viewer sees disabled actions with reasons and can't reach Administration; an operator can retry but can't edit rules; the last admin can't demote themselves.

---

## 9. Authentication flows (local auth mode)

In OIDC mode, password login is off. The sign-in page shows only the provider button, and "Forgot password?" becomes "Sign-in is managed by {provider}. Reset your password there." The flows below apply to local and demo modes.

### 9.1 Forgot password

1. "Forgot password?" on the sign-in page leads to a form with one email field.
2. On submit, always show the same message, so attackers can't tell which emails have accounts: "If an account exists for that email, we've sent a reset link. It expires in 30 minutes."
3. Rate-limit requests: 5 per hour per email and 20 per hour per IP.
4. The email goes out through the configured mailer (SMTP or SES).
   - In offline demo mode, emails go to a dev mailbox page instead (`/dev/mailbox`, admin only), so the flow can be shown without a mail server.
   - On the public hosted demo, reset is disabled for the shared demo accounts, with a message saying so.
5. **The token:**
   - 32 random bytes, stored only as a SHA-256 hash.
   - Single use, and expires after 30 minutes.
   - Issuing a new token, or changing the password, invalidates older tokens.

### 9.2 Set a new password

This screen is shared with invite acceptance.

- New password and confirm fields, with show/hide toggles.
- Requirements show live: at least 12 characters, not one of the most common or breached passwords (use a bundled list so it works offline), and not the user's email.
- A strength meter that suggests improvements but doesn't block.
- **On success:**
  - Hash with argon2id.
  - Revoke **all** of the user's sessions.
  - Send a "Your password was changed" notice.
  - Write an audit entry.
  - Redirect to sign-in with the toast "Password updated. Sign in with your new password."
- An expired or used link shows: "This link has expired or was already used." and a "Send a new link" button.

### 9.3 Change password (signed in)

- Requires the current password, with the same rules as above.
- On success, signs out every other session; the current one stays signed in.

### 9.4 Lockout and sign-in safety

- After 10 failed attempts in 15 minutes, apply a 15-minute cool-down per account and per IP. The message stays generic.
- Show the last sign-in time and device in the user menu.
- Session cookies stay HttpOnly, Secure and SameSite as today. Keep the existing CSRF protection on all of these forms.

### 9.5 Tests

- Unit tests:
  - Tokens are stored hashed.
  - Expired, used and superseded tokens are rejected.
  - Rate limits apply.
  - The response is identical for known and unknown emails.
- Integration: a reset revokes the user's sessions; a password change keeps the current session and revokes the others.
- e2e: the full forgot-password flow through the dev mailbox; invite acceptance; the lockout message.

---

## 10. Copy and formatting rules

- **Voice:** plain verbs, sentence case, no filler, no exclamation marks.
- **Errors:** say what happened, then what to do. "The API isn't responding. Check the backend service, then try again."
- **Durations:** `45s`, `4m 12s`, `2h 05m`, `3d 4h`. Never use "mins" or decimal minutes in the UI. (Charts may use decimal minutes, with "min" on the axis.)
- **Times:** relative under 24 hours ("12m ago"), with the absolute local time in a tooltip and UTC also in the tooltip. Absolute beyond that ("Nov 9, 07:00").
- **Numbers:** thousands separators. Percentages get one decimal place ("98.9%"), except exactly "100%". No trailing ".0".
- **Names:** "Tenant", "Run", "Incident", "Sync", used the same way everywhere. A page title matches its nav label.
- **Empty states:** "No failures in the last 24 hours." or "No tenants yet. Onboard your first tenant."

---

## 11. Design review rubric and quality gates

### 11.1 Rubric

Every new or changed screen is scored from 0 (poor) to 2 (good) on each of the following, in its pull request:

1. Hierarchy: the most important thing is obvious within 3 seconds.
2. Alignment and spacing: on the 12-column grid, rhythm tokens only, edges aligned.
3. Typography: the type scale is used and numbers are tabular.
4. Color: status-only semantics, contrast meets AA.
5. Component consistency: the same control looks and behaves the same everywhere.
6. States: loading, empty, error and partial-data states are all designed.
7. Motion: purposeful, and respects reduced motion.
8. Responsiveness: correct at 1440, 1024 and 390 px; no page-level horizontal scroll.
9. Accessibility: keyboard only, focus visible, axe clean.
10. Copy: the §10 rules are followed, and nothing from §2 appears.

A page passes at 17/20 or higher, with no zeros.

### 11.2 Gates (CI)

- **Lint:** no raw hex values, no arbitrary Tailwind values, no inline styles in components except computed geometry (chart and timeline positions).
- **Accessibility:** axe finds zero serious or critical issues on every page, in light and dark.
- **Visual regression:** Playwright screenshots for every page in §7, at 1440 and 390 px, light and dark, on seeded demo data with a frozen clock. Diffs are reviewed in the PR.
- **Layout stability:** CLS under 0.01 on Overview during a 60-second live session.
- **Performance:** Overview interactive in under 2 s on the demo dataset (local production build).

---

## 12. Definition of done (per screen)

- It scores 17/20 or more on the rubric, with no zeros.
- It uses only tokens and the §4 components, and `/styleguide` covers any new component state.
- It passes the §11.2 gates in light and dark, at 1440 and 390 px.
- `make reset && make demo` shows every SPEC §13 scenario on the screens where it applies.
