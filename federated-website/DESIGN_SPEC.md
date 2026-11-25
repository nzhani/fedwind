# FedWind design specification (reference: tem.energy)

Reverse-engineered on 2026-11-19 from https://www.tem.energy/ (a Framer site) by reading the live page's
computed styles, layer names and animations at 1440 px and at the phone breakpoint. Values marked
**measured** come straight from the page; **inferred** ones come from layer names, transforms or
screenshots and should be checked visually once.

We take the reference's **design system** (layout rhythm, type scale, components, motion), not its
brand: no tem logo, star mark, copy, photos or illustrations. FedWind keeps its own name, mark and
content (§8).

---

## 1. Layout

### 1.1 Page structure (home page, top to bottom; 1440 px viewport, page ≈ 10 400 px tall)

| # | Section | Background | Height | Content |
|---|---|---|---|---|
| 1 | Hero | solid orange + blurred radial glow | 100vh (900), pinned during the first scroll | animated mark, 120 px serif headline, small down-chevron |
| 2 | Statement | white | ≈ 560 | one 52 px paragraph-headline, two-tone (accent words + ink words), 1080 wide |
| 3 | Product band ("Introducing …") | solid orange `#FF3F10` | ≈ 1180 | small 80 %-white label, 110 px wordmark, 20 px body, white pill button, device mock-up rising from the bottom |
| 4 | Feature stack | ink `#222222` | ≈ 1000 | three 1200 × 400 cards that stack while scrolling ("Accordion Stack"); 60 px headlines in white or orange, 32 px feature titles, 20 px body |
| 5 | Logo wall | white | ≈ 1080 | infinite horizontal marquee of partner logos |
| 6 | Press | white | ≈ 390 | "Take a deeper look" + article cards |
| 7 | Testimonials | full-bleed photo + `rgba(34,34,34,.3)` overlay | ≈ 930 | 52 px white title; slider of white 16 px-radius cards, 1225 wide |
| 8 | FAQ | white | ≈ 790 | 44 px headings, questions as an accordion, 1200 container |
| 9 | Call to action | white page, **inset orange panel** 40 px from both edges | ≈ 805 | centered 24 px text + pill button; 186 px vertical padding inside |
| 10 | Join | white | ≈ 925 | ring of 220 × 270 rounded images rotating around the text; white fade at the bottom |
| 11 | Footer | white | ≈ 590 | 3 link columns with tiny grey labels, very large (32 px) link text |

**Measured:** order, colors, heights, widths. **Inferred:** the pinning and stacking behavior (§5).

### 1.2 Content widths (measured)

| Use | Width |
|---|---|
| Navbar pill | 1100 px, centered, fixed |
| Main container (feature cards, FAQ, press) | 1200 px |
| Statement text block | 1080 px |
| Testimonial card | 1225 px |
| Inset orange CTA panel | viewport − 2 × 40 px |
| Footer content | viewport − 2 × 48 px |
| Side padding (all breakpoints) | 40 px |

There is no visible column grid: sections are centered flex stacks with fixed max-widths. Inside
components, spacing comes from flex `gap`: nav 40 px, footer 64 px, testimonial card 48 px,
small groups 10 px.

### 1.3 Vertical rhythm (measured)

| Where | Padding |
|---|---|
| Standard content section (FAQ) | 120 px top and bottom, 40 px sides |
| Product band | 80 px top, content runs into the bottom edge |
| Inset CTA panel | 186 px top and bottom inside the panel |
| Footer | 48 px top, 50 px bottom |
| Card interior (testimonial) | 24 px |

Spacing values cluster on **10 / 24 / 40 / 48 / 64 / 80 / 120** (plus 186 for the hero-like CTA).

### 1.4 Alignment and whitespace
- Hero, product band and CTA: everything **centered**. Content sections: **left-aligned** text in a
  centered container.
- Whitespace is generous and comes from section padding, not from borders or dividers.
- Full-bleed colour bands alternate with white: orange → white → orange → ink → white → photo →
  white → (inset orange) → white. The alternation does the work that cards and borders do elsewhere.

---

## 2. Visual design

### 2.1 Colour palette (measured)

| Token | Value | Use |
|---|---|---|
| `accent` | `#FF3F10` (rgb 255 63 16) | brand fill: hero, product band, CTA panel, primary buttons, highlighted words, "Log in" link |
| `ink` | `#222222` | all body and heading text on white; dark section background |
| `white` | `#FFFFFF` | page background, text on orange/ink, button fill on orange |
| `muted` | `#737373` | 10 px uppercase labels ("EXPLORE") |
| `on-accent-soft` | `rgba(255,255,255,0.8)` | secondary text on orange |
| `overlay` | `rgba(34,34,34,0.3)` | darkening over photos |
| `glow-1 / glow-2` | `#FCC492` → `#FF7700` → `#FF3F10` | hero radial glow (§2.2) |
| `warm-white` | `#F7F4F1` | start of the fade into white near the bottom |

Effectively a **two-colour system** (orange + charcoal) on white. No greys for surfaces; no second accent.

### 2.2 Backgrounds (measured)
- **Hero glow:** a 1425 px circle with `radial-gradient(50% 50% at 50% 68.9%, #FCC492 0.3%, #FF7700 45.5%, #FF3F10 100%)`,
  `filter: blur(75px)`, `mix-blend-mode: color-dodge`, over solid `#FF3F10`, centre slightly low.
  Result: a warm, glowing, almost light-emitting orange.
- **Band joins:** a 135 px `linear-gradient(0deg, transparent → #FF3F10)` softens where the product band
  starts; a 181 px `linear-gradient(transparent #F7F4F1 → #FFFFFF)` fades images into the footer.
- **Photo sections:** full-bleed photo + 30 % ink overlay.

### 2.3 Borders, shadows, radii (measured)

| | Value |
|---|---|
| Borders | **none** anywhere sampled (0 px) |
| Shadows | only the navbar: `0 3px 6px rgba(0,0,0,0.05)` |
| Radius: buttons | 32 px (full pill) |
| Radius: navbar | 38 px (full pill) |
| Radius: cards | 16 px |
| Radius: images | 12 px |
| Radius: sections and bands | 0 |

### 2.4 Hierarchy
1. Giant display type (110–120 px) owns each band.
2. 52–60 px section statements.
3. 32 px feature titles and stats.
4. 20 px body, 16 px UI, 10 px labels.
Colour does the rest: one accent word group per headline, everything else ink or white.

---

## 3. Typography

### 3.1 Families (measured)

| Role | Reference typeface | Licence | FedWind substitute (free) |
|---|---|---|---|
| Display serif | Victor Serif Smooth Regular | commercial | **Instrument Serif** (Google Fonts, OFL): narrow, high-contrast display serif, one weight |
| UI / body / headings | PP Neue Montreal Regular 400, Medium 500 | commercial (Pangram Pangram) | **Geist Sans** (OFL, `geist` package) or **Inter Tight**; Geist is closer in its neutral grotesk feel |
| Mono (data, codes) | Fragment Mono | OFL | **Fragment Mono** (Google Fonts), the same font |
| Handwriting accent | Reenie Beanie | OFL | don't use: it doesn't fit a research product |

We can't ship the two commercial fonts without licences; the substitutes keep the contrast
between an editorial serif for big moments and a quiet grotesk for everything else.

### 3.2 Type scale (measured; desktop → phone)

| Style | Family | Size / line-height | Tracking | Weight | Used for |
|---|---|---|---|---|---|
| `display-xl` | serif | 120 / 120 → 72 / 72 | −0.04 em (−4.8 px → −2.88 px) | 400 | hero headline |
| `display-l` | sans | 110 / 110 | −0.03 em (−3.3 px) | 400 | product wordmark |
| `heading-xl` | sans | 60 / 72 | −0.03 em (−1.8 px) | 400 | feature-stack headlines |
| `heading-l` | sans | 52 / 52 → 36 / 36 | −0.02 em | 500 | statements, section titles |
| `heading-m` | sans | 44 / 48.4 → 32 / 35.2 | 0 | 500 | FAQ / section headings |
| `heading-s` | sans | 32 / 35.2 | 0 | 500 | feature titles, footer links (23 px on phone) |
| `stat` | sans | 32 / 38.4 | −0.01 em | 500 | numbers with labels ("25 % lower …") |
| `lead` | sans | 24 / 33.6 | 0 | 500 | CTA paragraphs |
| `body-l` | sans | 20 / 28 → 18 / 25.2 | 0 | 400 | paragraphs |
| `button-l` | sans | 18 / 24 | 0 | 500 | large buttons |
| `body` / `ui` | sans | 16 / 22.4 | 0 (nav −0.01 em) | 400 / 500 | text, nav links, small buttons |
| `label` | sans | 10 / 10–12 | +0.1–0.2 em (1–2 px) | 500, uppercase | eyebrows, footer column labels |

Rules visible in the reference:
- **The bigger the type, the tighter the tracking** (−4 % at 120 px, −3 % at 60–110 px, −2 % at 52 px, 0 at body).
- Large headings use **line-height 1.0–1.2**; body uses **1.4**.
- Only two weights in practice: **400 and 500**. No bold.
- Button labels are capitalised words ("Get Started"), never all caps; only the 10 px labels are uppercase.

---

## 4. Components

### 4.1 Navbar (measured)
- Fixed at the top, transparent full-width wrapper 72 px tall; inside it a **white pill** 1100 × 56 px,
  radius 38 px, padding 8 px 10 px 8 px 28 px, gap 40 px, shadow `0 3px 6px rgba(0,0,0,.05)`.
- Left: wordmark with a small mark (accent colour). Centre: 4–5 text links, 16 px Medium ink,
  −0.16 px tracking. Right: "Log in" text link in accent, then a **small primary pill button** with an arrow.
- Floats over the orange hero and over white sections alike (no colour change on scroll observed).
- Phone: same pill height (56 px), links collapse into a menu (**inferred**: no burger layer name found).

### 4.2 Buttons (measured)

| Size | Height | Padding | Text | Radius |
|---|---|---|---|---|
| S | 36 px | 8 × 14 px | 16 / 20, 500 | 32 px |
| M | 44 px | 10 × 16 px | 16 / 24, 500 | 32 px |
| L | 52 px | 14 × 20 px | 18 / 24, 500, gap 2 px | 32 px |

Variants:
- **Primary:** `#FF3F10` fill, white label.
- **On-fill:** white fill, `#FF3F10` label, used on orange bands.
- **Text link:** accent label, no fill.

No borders, no shadows. A right arrow (→) follows the label. Hover is the text roll (§5.2).

### 4.3 Cards
- **Testimonial card** (measured): white, radius 16 px, padding 24 px, gap 48 px, no shadow or border;
  sits on a dark photo, so contrast comes from the background.
- **Feature-stack card** (measured size, inferred look): 1200 × 400, ink background, radius 0, large
  60 px headline (white or accent) with 32 px feature titles and 20 px white body.
- **Image tiles** (measured): 220 × 270, radius 12 px.
- **Stat** (measured): 32 px Medium number+label in ink.

### 4.4 Forms (inferred, from the product mock-up)
- White card, centered title in the display serif ("Tell us about you"), step dots, thin full-width
  input lines with small grey labels, one orange pill button at the bottom.
- The marketing site itself has no form except the cookie banner.

### 4.5 FAQ / accordion (measured section, inferred interaction)
- White section, 120 px padding, 1200 container; 44 px Medium headings; question rows open to 20 px body.
- No borders sampled on rows; separation by spacing.

### 4.6 Marquee (measured)
- Logo list (`UL`) translating linearly, **118.4 s per loop**, infinite.

### 4.7 Footer (measured)
- White; 48 px top, 50 px bottom; 48 px side margins; columns 64 px apart.
- Columns: `EXPLORE` / `FIND US` / `ADDRESS`. Each label is 10 px uppercase Medium `#737373` with 1 px tracking.
- **Links are huge:** 32 px Medium ink, line-height 1.1, each with the text-roll hover. Phone: 23 px.
- Address in 16 px Medium.

### 4.8 Cookie banner (measured)
- Floating light card near the bottom centre, 14 px Inter, grey text, a small "Okay" pill.
  (FedWind doesn't need one unless analytics are added.)

---

## 5. Behaviour

### 5.1 Scrolling
- **Smooth scrolling with Lenis** (`html.lenis`): wheel input is eased, giving the "heavy", calm feel.
- **Pinned hero** (inferred): the hero stays while the statement section scrolls in.
- **Scroll-revealed statement** (inferred): the two-tone 52 px paragraph appears as you scroll, likely
  word by word.
- **Sticky stacking cards** (inferred from "Accordion Stack" and the 3 × 400 px cards): each card
  sticks and the next slides over it.
- **Rotating image ring** (inferred from a 2950 px "Image Rotate Wrapper"): tiles orbit the join text,
  tied to scroll.
- **Device mock-up** rising into the product band.

### 5.2 Hover: the text roll (measured)
Buttons and footer links contain the label twice. At rest the second copy sits about 40 px below,
**skewed ~22°** (`matrix(1, 0.404, 0, 1, …)`) and transparent. On hover the visible copy slides
down/out (~45 px) and the second copy slides up into place while un-skewing and fading in.
Background colour does **not** change. It's driven by Framer Motion springs, not CSS transitions;
duration ≈ 0.4–0.6 s (inferred).

### 5.3 Intro animation (observed)
- The hero first shows only the mark, centred; it rotates and settles above the headline; the headline fades/rises in.

### 5.4 Other
- No CSS keyframes or transitions in the page's own CSS: all motion is JavaScript-driven (Framer Motion).
- One continuous WAAPI animation: the marquee.

### 5.5 Responsive (measured at the phone breakpoint, < 810 px)
| Item | Desktop | Phone |
|---|---|---|
| Hero h1 | 120 / 120 | 72 / 72 (−0.04 em kept) |
| Statement | 52 / 52 | 36 / 36 |
| Section heading | 44 / 48.4 | 32 / 35.2 |
| Body | 20 / 28 | 18 / 25.2 |
| Footer links | 32 | 23 |
| Product wordmark | 110 | 110 (wraps less; still fits) |
| Section padding | 120 / 40 | 120 / 40 (unchanged) |
| Navbar pill | 56 px tall | 56 px tall |

Framer's standard breakpoints apply: desktop ≥ 1200, tablet 810–1199, phone < 810.

---

## 6. Design identity: why it looks professionally designed

1. **One loud colour, used in whole surfaces.** Instead of small orange accents, entire bands are
   orange. That builds a recognisable brand with almost no decoration.
2. **Editorial serif against a neutral grotesk.** The serif appears only at the very top (the
   promise); everything functional is a quiet sans. The contrast reads as "premium", not "app".
3. **Very large type, tight tracking, only two weights.** Hierarchy comes from size and colour, not from bold.
4. **No borders, almost no shadows.** Structure comes from colour blocks, pills and whitespace,
   which keeps the page calm even with big type.
5. **Consistent geometry.** Pills for everything you click (32–38 px), 16 px cards, 12 px images, square bands.
6. **Crafted motion with restraint.** Smooth scroll, a text roll instead of colour flashes, pinned and
   stacking sections. Motion carries the story; nothing blinks.
7. **Strict rhythm.** The same 40 px side padding and 120 px section padding everywhere, and
   1200 / 1080 px containers.

---

## 7. How this maps onto FedWind

### 7.1 Tokens to implement (values for Tailwind theme / CSS variables)

| Token | Value |
|---|---|
| `--color-accent` | decision D1 (§9); default `#FF3F10`-family signal orange |
| `--color-ink` | `#222222` |
| `--color-paper` | `#FFFFFF` |
| `--color-muted` | `#737373` |
| `--color-paper-warm` | `#F7F4F1` |
| `--radius-pill` | 32 px |
| `--radius-card` | 16 px |
| `--radius-image` | 12 px |
| `--shadow-nav` | `0 3px 6px rgba(0,0,0,.05)` |
| `--space-section-y` | 120 px |
| `--space-page-x` | 40 px |
| `--container` | 1200 px (text 1080 px) |
| fonts | Instrument Serif (display), Geist Sans (UI), Fragment Mono (data) |

### 7.2 Marketing pages (Home, About, Architecture, Data Source, Solar overview)
| Reference section | FedWind version |
|---|---|
| Orange hero with glow, serif promise | "Forecasting the wind and sun, without sharing the data." Mark: FedWind's own (§8) |
| Two-tone statement | One sentence on federated learning; accent on "data never leaves the plant" |
| Orange product band + device mock-up | Forecast page screenshot in a laptop frame; on-fill button "See forecasts" |
| Ink feature stack (3 cards) | 1 Train at the plant · 2 Only model updates travel · 3 One shared model forecasts every site |
| Logo marquee | Marquee of the federation's sites (Almaty, Zhezkazgan, … Konaev, Saran) with energy icons |
| Testimonials on photo | Optional: a wind-farm / solar-field photo with result stat cards (skill vs persistence) |
| FAQ | "What is federated learning?", "Does my data leave the plant?", "How accurate is it?" |
| Inset orange CTA | "Register your plant" → `/register` |
| Footer with big links | Forecast · Training · Experiments · Sites · About; GitHub / team; NU address |

### 7.3 App pages (Forecast, Training, Run detail, Experiments, Sites, Admin, Login/Register)
Detailed page designs for Sites, Admin and Login/Register: `APP_PAGES_SPEC.md`.
The reference has no dashboard, so app pages use a **calm variant** of the same system:
- White pages, 1200 container, 40 px side padding; page title in `heading-l` (52 px, sans, not serif).
- Cards: white, 16 px radius, **1 px `rgba(34,34,34,0.08)` border** (dashboards need some edges;
  the reference's no-border rule is for marketing bands), no shadow.
- Primary actions as accent pills (M size); secondary as ink-outline pills; destructive in red-orange
  only for revoke/stop.
- Numbers (errors, sizes, timestamps, IDs) in Fragment Mono; small uppercase `label` style for card eyebrows.
- Charts: accent for the forecast, ink for actual, muted dashed for clear sky; no gridline clutter.
- Status badges as small pills (same colours as today, softer fills).
- Navbar: the same floating white pill on every page; account area at its right end.

### 7.4 Motion for FedWind
- Lenis smooth scroll on marketing pages only (not on dashboards with tables and charts).
- Text roll on buttons and footer links; fade-and-rise on section entry; sticky feature stack on the home page.
- All motion off under `prefers-reduced-motion`.
- Library: `motion` (Framer Motion) for React; `lenis` for scrolling.

---

## 8. What we don't copy
- tem's name, logo, star mark, product names ("RED™"), copy, photos, mock-ups, partner logos, addresses.
- The two commercial typefaces (substitutes in §3.1).
- The handwriting font and the cookie banner (not needed).
FedWind gets its own mark (e.g. a simple turbine/sun glyph) and its own words.

## 9. Decisions before implementation
| # | Question | Options |
|---|---|---|
| D1 | Accent colour | (a) signal orange close to the reference, (b) FedWind's own accent in the same role, e.g. a deep teal for wind with orange kept for solar |
| D2 | Display serif | Instrument Serif (default) · Fraunces · none (sans only) |
| D3 | Scope for tomorrow | Home + navbar + footer + design tokens first; app pages restyled to §7.3 next |
| D4 | Hero mark | new FedWind glyph (needed in any case) |
