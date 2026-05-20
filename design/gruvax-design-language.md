# GRUVAX Design Language

**Version 1.0** · Vinyl Shelf Navigator · Nordic Grid identity

---

## Overview

GRUVAX is an IKEA Kallax-native vinyl record kiosk. Its design language is deliberately borrowed from IKEA's visual system — institutional blue, high-contrast yellow, condensed sans-serif typography — then extended with the vocabulary of a physical LED display and vinyl record culture.

The result is a UI that feels like it could have shipped inside a Kallax box: structured, confident, and immediately readable on a 7" touchscreen from across a room.

---

## Brand

### Name
**GRUVAX** — from Swedish *gruv* (groove, as in record groove; also mining/digging) + the IKEA product name suffix *-ax* (cf. KALLAX). Pronounced "GROO-vax."

### Tagline
*Vinyl Shelf Navigator*

### Identity concept
The A7 Shelf Tag mark: white ground, IKEA-blue border all around, 4×4 Kallax grid icon with yellow LED cells, bold condensed wordmark, yellow rule, descriptor. Looks like it came off a real IKEA price tag.

---

## Logo

### Assets

| File | Format | Dimensions | Use |
|---|---|---|---|
| `gruvax-logo-square.svg` | SVG | 500×500 | Primary mark · app icons · print |
| `gruvax-logo-banner.svg` | SVG | 800×200 | Horizontal layout · headers · splash screens (standard / light) |
| `gruvax-logo-banner-dark.svg` | SVG | 800×200 | Reversed banner for dark backgrounds (blue ground, white wordmark) |
| `gruvax-logo-icon.svg`   | SVG | 200×200 | Mark only (no wordmark) · avatar · 32px+ contexts |
| `gruvax-favicon.svg`     | SVG | 32×32   | Browser tab · small format |
| `assets/banner_light.png` | PNG | 1600×400 | Rendered light banner — README/GitHub `prefers-color-scheme: light` |
| `assets/banner_dark.png`  | PNG | 1600×400 | Rendered dark banner — README/GitHub `prefers-color-scheme: dark` |

### Logo anatomy (square)
```
┌──────────────────────────────┐  ← Blue border (#0051A2, 20px)
│                              │
│  ██ ██ 🟡 ██                 │  ← 4×4 grid, 38px cells, 7px gaps
│  ██ ○  🟡 ██                 │    ○ = vinyl cell (circle mark)
│  🟡 🟡 🟡 ██                 │    🟡 = lit LED cell (#FFDA00)
│  ██ ██ ██ ██                 │    ██ = dim cell (#D8E8F5)
│                              │
│  GRUVAX                      │  ← Barlow Condensed 900, 84px, #0051A2
│  ━━━━━━━━━━━━━━━━━━━━━━━━    │  ← Yellow rule (#FFDA00, 6px)
│  VINYL SHELF NAVIGATOR       │  ← Barlow Condensed 700, 13px, #777
│                              │
└──────────────────────────────┘
```

### Clear space
Maintain clear space equal to **12.5% of the logo's shortest dimension** on all sides. Never crop the border.

### Minimum sizes
- Square mark: 120px wide
- Banner: 240px wide
- Icon mark: 24px wide (below this, use a solid-color fallback)

### Color variants

| Variant | Background | Border | Wordmark | Use case |
|---|---|---|---|---|
| **Standard** (default) | #FFFFFF | #0051A2 | #0051A2 | All primary uses |
| **Reversed** | #0051A2 | #FFFFFF | #FFFFFF | Dark/blue backgrounds |
| **Yellow ground** | #FFDA00 | #003D7A | #003D7A | Special / promotional |
| **Monochrome** | #FFFFFF | #1A1A1A | #1A1A1A | Single-color print |

The **Standard** and **Reversed** banner variants ship as ready-to-use files: `gruvax-logo-banner.svg` and `gruvax-logo-banner-dark.svg`, rendered to `assets/banner_light.png` and `assets/banner_dark.png` for GitHub's `<picture>` element (light/dark theme switching).

### Do not
- Change the border color independently from the wordmark
- Remove the yellow rule
- Recolor the lit cells to any color other than yellow
- Add drop shadows or glows to the logo itself
- Stretch or condense the wordmark independently

---

## Color

### Brand palette

| Token | Hex | Usage |
|---|---|---|
| `--gruvax-blue` | `#0051A2` | Primary brand · borders · wordmark · interactive |
| `--gruvax-blue-dark` | `#003D7A` | Hover · pressed · dark accents |
| `--gruvax-blue-darker` | `#002855` | Active states · deepest backgrounds |
| `--gruvax-blue-light` | `#D8E8F5` | Dim cell fill · inactive backgrounds |
| `--gruvax-blue-faint` | `#EEF5FB` | Hover bg · selected row tint |
| `--gruvax-yellow` | `#FFDA00` | LED lit · CTA · accent · rule |
| `--gruvax-yellow-dark` | `#E6B800` | Yellow borders · pressed yellow |
| `--gruvax-white` | `#FFFFFF` | Primary background |
| `--gruvax-off-white` | `#F7F9FC` | Secondary surface · card backgrounds |

### Cell state colors

| State | Fill | Border | Shadow |
|---|---|---|---|
| Dim (default) | `#D8E8F5` | `#B8D0E8` | none |
| Lit (found) | `#FFDA00` | `#E6B800` | LED glow |
| Hover | `#EEF5FB` | `#0051A2` | none |
| Selected (admin) | `#003D7A` | `#002855` | none |
| Empty | `#F2F2F2` | `#DDDDDD` | none |

### LED glow
When a cell is in the **lit** state, apply the LED shadow:
```css
box-shadow: var(--gruvax-shadow-led);
/* = 0 0 12px rgba(255, 218, 0, 0.6), 0 0 24px rgba(255, 218, 0, 0.3) */
```

### Accessibility
- Blue on white: contrast ratio 7.2:1 (AAA ✓)
- Yellow on blue: contrast ratio 3.1:1 — use only for large text (18px+) or decorative elements; never for body copy
- Blue on yellow: contrast ratio 3.1:1 — same constraint

---

## Typography

### Type system

GRUVAX uses a three-font system. Load all three from Google Fonts:

```css
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700;900&family=Space+Grotesk:wght@400;500;700&family=DM+Mono:wght@400;500&display=swap');
```

### Barlow Condensed — Display & Brand

Used for all large-scale text, labels, and the wordmark. Never use for body copy.

| Role | Size | Weight | Tracking | Color |
|---|---|---|---|---|
| Wordmark | 84px | 900 | 0.04em | `--gruvax-blue` |
| Hero heading | 48px | 900 | 0.02em | `--gruvax-blue` |
| Section heading | 36px | 900 | 0.02em | `--gruvax-blue` |
| Card title | 24px | 900 | 0.02em | `--gruvax-blue` |
| Tag / badge | 13px | 700 | 0.14em | varies |
| Descriptor | 13px | 700 | 0.20em | `--gruvax-text-muted` |

### Space Grotesk — UI Body

Used for all interactive UI text: buttons, inputs, descriptions, body copy.

| Role | Size | Weight |
|---|---|---|
| Body large | 18px | 400 |
| Body | 16px | 400 |
| Body small | 14px | 400 |
| UI label | 12px | 500 |
| Caption | 11px | 400 |

### DM Mono — Data & Metadata

Used for catalog numbers, bin positions, record counts, Discogs IDs, and any data that benefits from fixed-width rendering.

| Role | Size | Weight |
|---|---|---|
| Data readout large | 16px | 500 |
| Data readout | 14px | 400 |
| Dense metadata | 11px | 400 |

---

## Grid & Cell System

The Kallax is the atomic unit of GRUVAX. Everything in the UI maps to or derives from the 4×4 grid.

### Cell sizing

| Context | Cell size | Gap | Radius |
|---|---|---|---|
| Kiosk main display | 80px | 12px | 8px |
| Standard view | 56px | 8px | 6px |
| Compact / admin | 40px | 6px | 4px |
| Thumbnail / logo | 28px | 4px | 3px |

### CSS implementation

```css
.gruvax-shelf {
  display: grid;
  grid-template-columns: repeat(4, var(--gruvax-cell-size-lg));
  grid-template-rows: repeat(4, var(--gruvax-cell-size-lg));
  gap: var(--gruvax-cell-gap-lg);
}

.gruvax-cell {
  background: var(--gruvax-cell-dim);
  border: 1.5px solid var(--gruvax-cell-dim-border);
  border-radius: var(--gruvax-cell-radius-lg);
  transition:
    background var(--gruvax-led-on-duration) var(--gruvax-led-on-ease),
    box-shadow  var(--gruvax-led-on-duration) var(--gruvax-led-on-ease);
}

.gruvax-cell[data-state="lit"] {
  background: var(--gruvax-cell-lit);
  border-color: var(--gruvax-cell-lit-border);
  box-shadow: var(--gruvax-shadow-led);
}

.gruvax-cell[data-state="empty"] {
  background: var(--gruvax-cell-empty);
  border-style: dashed;
}
```

### Multi-shelf layout

Multiple shelves are displayed as a scrollable row or paginated set. Each shelf is labeled with a Barlow Condensed 700 identifier (e.g. "SHELF A", "SHELF B") above the grid.

---

## Animation

### Principles
1. **Purposeful** — animation communicates state change, not decoration
2. **Fast feedback** — UI responses under 150ms feel instant
3. **LED physics** — lit state springs on (overshoot), fades off (smooth)
4. **Screensaver transitions** — long, cinematic (800ms–1200ms)

### LED transition

```css
/* Cell turns on: spring pop */
transition: background 300ms cubic-bezier(0.34, 1.56, 0.64, 1),
            box-shadow 300ms cubic-bezier(0.34, 1.56, 0.64, 1);

/* Cell turns off: smooth fade */
transition: background 500ms cubic-bezier(0.4, 0.0, 0.2, 1),
            box-shadow 500ms cubic-bezier(0.4, 0.0, 0.2, 1);
```

### Search result reveal

When a search completes:
1. All cells transition to dim (200ms, staggered 10ms per cell)
2. Matching shelf scrolls into view (400ms ease-decelerate)
3. Matching cells light up (300ms spring, 50ms delay after scroll)
4. LED glow pulses once (scale 1→1.04→1, 600ms)

### Screensaver

Idle timer: **3 minutes** (configurable in admin).

Transition in:
- Kiosk UI fades to black: 800ms ease-accelerate
- First image cross-fades in: 1000ms ease-decelerate

Image cycle: 8–12 seconds per image, cross-fade 1200ms.

Dismiss: any touch → immediate fade-out (300ms) → kiosk returns.

---

## Component Patterns

### Search bar
Full-width, Barlow Condensed 900, 32px, blue border 2px, yellow focus ring.

### On-screen keyboard
`simple-keyboard` JS library, themed to match: blue keys, white labels (Space Grotesk 500), yellow for Enter/Search action key.

### Admin PIN overlay
Dark blue overlay (`#002855` at 95% opacity), centered PIN pad, Barlow Condensed 900 digits.

### Bin detail panel
Slides up from bottom on cube tap. Shows: shelf name, cube position, first N records, last N records (DM Mono), Discogs artwork thumbnails.

---

## Screensaver

The screensaver displays album artwork or custom images full-bleed. Overlay elements (if any) use white type only, never blue or yellow. The GRUVAX icon mark may appear as a subtle watermark at 15% opacity, bottom-right corner.

---

## Voice & Tone (UI copy)

- Labels: **ALL CAPS**, Barlow Condensed 700, tracked wide
- Instructions: **Sentence case**, Space Grotesk 400
- Error messages: plain language, no technical jargon ("Record not found in any shelf" not "Query returned 0 results")
- Admin interface: more direct ("Delete bin" not "Remove this bin from the shelf configuration")

---

## File Reference

```
design/
├── gruvax-logo-square.svg          Primary square mark
├── gruvax-logo-banner.svg          Horizontal banner (standard / light)
├── gruvax-logo-banner-dark.svg     Horizontal banner (reversed, for dark backgrounds)
├── gruvax-logo-icon.svg            Icon mark (no wordmark)
├── gruvax-favicon.svg              Browser favicon (32×32)
├── gruvax-design-tokens.css        CSS custom properties
├── gruvax-design-tokens.json       JSON tokens (JS/TS use)
├── gruvax-design-language.md       This document
└── assets/
    ├── banner_light.png            Rendered light banner (README / GitHub light theme)
    └── banner_dark.png             Rendered dark banner (README / GitHub dark theme)
```
