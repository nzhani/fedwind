# FedWind app pages: Sites, Admin, Login/Register (design spec)

Companion to `DESIGN_SPEC.md` (marketing pages, tokens, type scale). This file designs the signed-in
pages: minimal, professional, calm. No code here. Endpoints and the demo simulation behind these pages
are in `../DEMO_SIMULATION_PLAN.md`.

Design stance: **quiet surfaces, one accent, data first.** The marketing pages are loud (orange
bands, 120 px serif); the app pages are the opposite: white, hairline structure, tabular numbers, the
accent only for the one action that matters on each screen.

---

## 1. App shell (all signed-in pages)

### 1.1 Frame
- Same floating white **nav pill** as the marketing pages (`DESIGN_SPEC.md` §4.1). Right end: account
  menu (name · role) and, for admins, "Admin".
- Page background `#FFFFFF`; content max-width **1200 px**, side padding **40 px** (phone 20 px).
- 104 px from the top of the page to the page header (clears the fixed nav).

### 1.2 Page header (every page)
```
SITES                                              (10 px uppercase label, #737373, +0.1 em)
Your plants                                        (44 / 48, Medium, −0.02 em; phone 32 / 36)
Plants of Zhanatas Energy LLP in the federation.   (16 / 24, #737373, max 640 px)
                                      [ Register plant → ]   (primary pill M, right-aligned, baseline of the title)
```
48 px between the header and the first content block.

### 1.3 Surfaces
| Element | Spec |
|---|---|
| Card | white, radius 16 px, border `1px solid rgba(34,34,34,0.08)`, no shadow, padding 24 px |
| Card title | 16 / 24 Medium ink; optional right-aligned text action |
| Divider | 1 px `rgba(34,34,34,0.08)` |
| Hover surface (rows, list items) | `#F7F4F1` (warm white from the reference) |
| Muted text | `#737373` |
| Danger text | accent-dark (see §1.9) |

### 1.4 Type in the app
| Style | Spec |
|---|---|
| Page title | 44 / 48, 500, −0.02 em |
| Section title | 20 / 28, 500 |
| Body | 16 / 24, 400 |
| Small | 14 / 20, 400 |
| Label | 11 / 16, 500, uppercase, +0.08 em, `#737373` |
| Data | Fragment Mono 14 / 20: ids, coordinates, capacities, timestamps, IPs, numbers in tables |

No serif in the app, except the auth panel line (§5).

### 1.5 Tables
- Header row: label style, no background, 1 px divider below.
- Rows: **56 px** tall, 1 px divider between, hover `#F7F4F1`, whole row clickable when it opens a detail.
- Numbers right-aligned in mono; text left-aligned; no zebra stripes; no vertical lines.
- Row actions: right-most column, quiet text buttons (ink, text-roll on hover); destructive actions
  inside a "⋯" menu, never as bare red buttons in a row.
- Phone (< 810 px): rows become stacked list items (title line, meta line, status at the right).

### 1.6 Status pill (one component everywhere)
22 px tall, radius 999, padding 0 10 px, 12 / 16 Medium **ink text**, background `#F4F4F2`, with a
6 px coloured dot before the text. Colour lives only in the dot:

| Status | Dot | Text |
|---|---|---|
| registered | amber `#E8A400` | Waiting for approval |
| approved | blue `#2F6FEB` | Approved |
| kit issued | blue `#2F6FEB` | Kit issued |
| active + online | green `#1F9D55` | Online |
| active + offline | grey `#A3A3A3` | Offline |
| suspended | grey `#A3A3A3` | Suspended |
| rejected / revoked | accent-dark | Rejected / Revoked |
| simulated (extra pill) | none, dashed 1 px border | Simulated |

### 1.7 Forms
- Two-column sections on desktop: left 1/3 = section title (20 px) + one-line help (14 px muted);
  right 2/3 = fields. Sections separated by a divider and 32 px.
- Input: 44 px, radius 12 px, border `1px solid rgba(34,34,34,0.14)`, 16 px text; focus: border ink
  plus a 3 px ring of the accent at 20 % opacity; disabled: background `#F7F4F1`.
- Label above (14 / 20 Medium), help below (13 / 18 muted), error below in accent-dark, replacing the help.
- Segmented control for 2–3 options (Wind / Solar): pill track `#F4F4F2`, selected segment white
  with the hairline border.
- Toggle cards for consents: full-width card, title + one-sentence explanation + switch at the right.
- **Sticky action bar** at the bottom of long forms: white, top hairline, Cancel (text) + primary pill.

### 1.8 Feedback
| Pattern | Spec |
|---|---|
| Toast | bottom-right, white card radius 12, hairline border, 14 px text, 4 s, one optional action |
| Inline notice | soft fill `#F7F4F1`, 14 px ink, 16 px icon; errors use accent at 8 % fill |
| Empty state | centred in the card: 24 px line icon (muted), 20 px title, 16 px body, one action |
| Loading | skeleton bars `#F2F2F0`, same height as the content; no spinners except inside buttons |
| Confirm with reason | the clicked action turns into an inline row: reason input (required, "The operator sees this") + destructive pill + Cancel |

### 1.9 Colour accessibility
White text on the reference orange `#FF3F10` is ≈ 3.5 : 1, enough only for large text. In the app:
primary pill labels are 16 px Medium, so use an **accent-dark** shade for text-bearing small elements
(links, danger text, small pill fills) chosen to reach ≥ 4.5 : 1 on white; keep the bright accent for
large fills. Never use colour alone for status (dot + word).

### 1.10 Motion in the app
Only: text roll on pill buttons and nav links, 150 ms fade for toasts and menus, row hover. No smooth
scroll (Lenis) on app pages. Everything off under `prefers-reduced-motion`.

---

## 2. Sites (operator)

### 2.1 `/sites`: Your plants
```
SITES
Your plants                                                     [ Register plant → ]
Plants of Zhanatas Energy LLP in the federation.

┌ 4 stat tiles (label + 32 px number) ───────────────────────────────────────────────┐
│ PLANTS 3        ACTIVE 1        WAITING FOR APPROVAL 1        ONLINE NOW 1          │
└──────────────────────────────────────────────────────────────────────────────────────┘
┌ Card ────────────────────────────────────────────────────────────────────────────────┐
│ PLANT                     TYPE    CAPACITY   STATUS                 CONNECTION   UPDATED │
│ ◌ Zhanatas Wind Farm      Wind    100 MW     ● Online  [Simulated]  2 min ago    19 Nov  │
│   zhanatas-wind-farm-1ded                                                              │
│ ◌ Saran Solar             Solar    50 MW     ● Waiting for approval  —           19 Nov  │
└──────────────────────────────────────────────────────────────────────────────────────┘
```
- Stat tiles: borderless, label style over a 32 px Medium number (mono digits), 4 across, 24 px gap.
- Plant cell: 20 px wind/solar line icon, name 16 Medium, id below in mono 12 muted.
- Empty: icon, "No plants yet", "Register your first plant; an admin approves it, then you install the
  site kit.", [Register plant].

### 2.2 `/sites/new`: Register a plant
Two-column form (§1.7), sections:
1. **Plant**: name; type (segmented Wind | Solar); installed capacity (MW).
2. **Location**: latitude, longitude (mono inputs) with a live check "Inside Kazakhstan ✓" or the
   error; region and time zone shown read-only beside it (time zone selectable); "Open in map ↗".
3. **Equipment**: wind (turbine model, number, hub height, rated power) or solar (module type,
   mounting, tilt, azimuth); fields swap with the type, values kept per type.
4. **Data and contact**: data source (CSV export / OPC UA / PI / other), technical contact.
5. **Consents**: three toggle cards: Federated training (required, locked on with a lock icon and
   "Required to join"), Central forecasting, Public forecasts.

Sticky bar: "Cancel" · [Register plant]. On success: go to the plant page with the toast "Plant
registered. An admin will review it."

### 2.3 `/sites/[id]`: Plant page
```
← Your plants
Zhanatas Wind Farm                                   ● Online  [Simulated]      [ ⋯ ]
zhanatas-wind-farm-1ded · Wind · 100 MW · Zhambyl region · Asia/Almaty

┌ Progress ──────────────────────────────────────────────────────────────────────────┐
│  ● Registered ───── ● Approved ───── ● Kit installed ───── ● Online                │
│  19 Nov 21:56        19 Nov 21:57      19 Nov 22:10           since 22:10           │
└─────────────────────────────────────────────────────────────────────────────────────┘
┌ Left 2/3 ───────────────────────────────────────┐ ┌ Right 1/3 ─────────────────────┐
│ Connection                                       │ │ Activity                       │
│  Last heartbeat 40 s ago · agent 0.1.0 (sim)     │ │ ● Online        22:10          │
│  Data until 19 Nov 22:00 UTC · 0 gaps today      │ │ ● Kit installed 22:10          │
│  Data quality, last 7 days  ▁▂▇▇▇▇▇ (bars)       │ │ ● Approved      21:57 · Admin  │
│ Site kit (only while approved, not installed)    │ │ ● Registered    21:56 · Aigerim│
│ Forecast (Tier 2) sparkline + "Open forecast →"  │ │                                │
│ Details (definition list)                        │ │ Consents (3 lines with ✓ / –)  │
└──────────────────────────────────────────────────┘ └────────────────────────────────┘
```
- **Progress stepper**: 4 steps, 8 px dots on a 1 px line; done = ink dot, current = accent dot with a
  soft accent halo, future = hollow grey; date under each. Rejected/revoked replace the line with a
  single row: dot + "Rejected 19 Nov · reason".
- **Site kit card** (status approved, not yet enrolled):
  - Title "Install the site kit" + valid-until in mono ("valid 71 h").
  - [Download kit (.zip)] primary pill.
  - Three numbered steps, each with a copyable command in a mono block:
    `unzip …` · `docker compose up -d` · "This page turns Online within a minute."
  - For the demo also: `deploy/sim/run_site.sh <kit.zip>` labelled "Simulate the plant on this computer".
  - Text action "Lost the kit? Ask an admin to re-issue it."
- **Connection card** (after enrollment): state line, heartbeat age, agent version and kind,
  data-until, quality bars (7 small bars, height = share of clean hours, muted; today in ink).
- **Details**: definition list, labels 14 muted at the left (1/3), values 14 ink; numbers in mono.
- **⋯ menu** (operator): Edit (only while waiting), Pause participation (later), Leave federation (later).

---

## 3. Admin

### 3.1 Navigation
Admin pages share a second row under the page header: text tabs
**Overview · Approvals (n) · Sites · Users · Audit log**. Active tab: ink text with a 2 px ink
underline; others muted; the count is a small grey pill.

### 3.2 `/admin`: Overview
- 5 stat tiles: Waiting for approval · Active sites · Online now · Users · Run (Idle / "Round 3 of 20").
- **Needs attention** card: one line per item, newest first, each with one action:
  - "Saran Solar waiting since 2 h · Review →"
  - "Aktau offline for 3 h · Open →"
  - "Run solar-fedavg-h72 failed · Open →"
  - Empty: "Nothing needs attention."
- **Recent activity** card: last 8 audit entries in the compact activity style (§3.6), "View all →".

### 3.3 `/admin/approvals`: Approvals queue (master–detail)
- Left (5/12): list of waiting plants, newest first: name, org, type icon, capacity, "2 h ago".
  The selected item has the warm hover fill and a 2 px ink bar at the left.
- Right (7/12): the selected registration as a read-only review sheet: map coordinates (mono),
  equipment, data source, contact, consents, submitted by/at. Bottom bar: [Approve] (primary)
  · Reject (text, opens the confirm-with-reason row).
- After a decision: toast "Approved Zhanatas Wind Farm. The operator can download the kit."
  and the next item is selected.
- Empty: "No plants waiting. New registrations appear here."

### 3.4 `/admin/sites`: All sites
- Filter bar: search (name, id, org) · Type (All / Wind / Solar) · Status (multi) · Source
  (Lab / Plants) · Connection (Online / Offline).
- Table: Plant · Organization (Lab sites show "Lab · simulated") · Type · Capacity · Status ·
  Connection · Last heartbeat · ⋯
- ⋯ menu: Open · Suspend · Resume · Re-issue kit · Revoke (danger, last, needs reason).

### 3.5 `/admin/users`: Users
- Table: User (name + email) · Organization · Role (inline select, quiet) · Status · Last login (mono) · ⋯
- [Add user] opens a **side sheet** from the right (480 px): name, email, role, organization (only
  for operators), initial password, [Create user]. A one-time password is shown once, with a copy button.
- ⋯ menu: Disable / Enable, Reset password (later: email link).
- Your own row: role and status locked, with a tooltip "You can't change your own access".

### 3.6 `/admin/audit`: Audit log
- Filter bar: action group (Accounts / Sites / Runs / Models / Security), actor, target, date range.
- Table: Time (mono, local + UTC on hover) · Actor (name or "system"/"anonymous") · Action (mono
  code, e.g. `site.approve`) · Target (mono, linked to site/run/user) · Details (`key: value` pairs,
  muted, truncated with hover) · IP (mono).
- Security events (`login.failed`, `login.throttled`, `site.revoke`) get an accent-dark action code.
- "Load older" at the bottom (cursor pagination); "Export CSV" text action at the top right.

---

## 4. Shared states and edge cases
| Situation | Behaviour |
|---|---|
| Not logged in on a protected page | page header + card "Log in to see your plants" + [Log in] (returns to the page) |
| Wrong role | same card: "This page is for admins." No data requested. |
| Database or API down | inline notice in the card: "Can't reach FedWind right now. Retrying…" plus Retry |
| Lost connection while editing | keep the form, show the error under the sticky bar |
| Long names | truncate in tables with full text on hover; never wrap a status pill |
| Many sites (100+) | tables paginate at 50; filters keep state in the URL |

---

## 5. Login and Register
Split layout on desktop:
- **Left 5/12**: full-height accent panel with the hero glow (`DESIGN_SPEC.md` §2.2), FedWind mark at the
  top, one serif line in 48 px white ("Forecasts, without sharing data."), three short white
  lines at the bottom (Train at the plant · Only model updates travel · One shared forecast).
- **Right 7/12**: centred form, 400 px wide, page-header style title ("Log in" / "Register your
  organization"), fields per §1.7, full-width primary pill, small switch link below.
- Register shows a 3-step "What happens next" list under the button: Register plant → Admin
  approves → Install the site kit.
- Phone: the panel collapses to a 160 px band above the form.

---

## 6. Copy rules
- Sentence case everywhere; buttons are verbs ("Register plant", "Download kit", "Approve").
- Plain words for states: "Waiting for approval", not "PENDING".
- Times: relative in lists ("2 min ago"), exact in detail views (mono, with UTC).
- Simulated things always say so ("Simulated" pill; agent "0.1.0 (sim)").
