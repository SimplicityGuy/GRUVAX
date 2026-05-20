# Conventions

> Source of truth for project-wide conventions. Synced into the root `CLAUDE.md` Conventions block by `gsd-tools generate-claude-md`. Only headings, bullet lines, and table rows survive the sync (prose paragraphs are dropped), so keep rules as bullets. Paths are written as code spans (not links) so they read correctly both here and when embedded into `CLAUDE.md` at the repo root.

## Design Language

- **Use the Nordic Grid design language for all user-facing work** — kiosk UI, admin UI, logos, favicons, generated images, slide/diagram styling, and docs. Do not invent new visual styles or one-off palettes.
- **Source of truth is `design/`** — read `design/gruvax-design-language.md` (the spec) before building any UI or visual asset. Tokens live in `design/gruvax-design-tokens.css` and `design/gruvax-design-tokens.json`; logo marks and rendered banners live in `design/` and `design/assets/`.
- **Consume tokens; never hardcode hex.** Wire `gruvax-design-tokens.css` / `.json` into the frontend as the contract between design and code. Core palette: IKEA blue `#0051A2` (`--gruvax-blue`), LED yellow `#FFDA00` (`--gruvax-yellow`), off-white `#F7F9FC` (`--gruvax-off-white`).
- **Type system is three fonts** — Barlow Condensed (display & wordmark), Space Grotesk (UI body), DM Mono (catalog numbers, bin positions, counts). Never use Barlow Condensed for body copy.
- **The Kallax cube (4×4) is the atomic UI unit.** Cell states (dim / lit / hover / selected / empty) come from the tokens; lit cells are always yellow with the LED glow — never recolor a lit cell.
- **Motion: LED physics.** Lit state springs on (overshoot), fades off (smooth); general UI feedback under ~150 ms. Use the transitions documented in the spec rather than ad-hoc easings.
- **Accessibility constraints from the spec.** Blue-on-white is AAA (body-safe). Yellow-on-blue and blue-on-yellow are ~3.1:1 — large text (18px+) or decoration only, never body copy.
- **Voice & tone.** Labels are ALL CAPS (Barlow Condensed 700, tracked wide); instructions are sentence case; error messages use plain language, no technical jargon.
- **Logo usage.** Standard (white-ground) variant on light backgrounds, Reversed (blue-ground) on dark; never recolor the border independently of the wordmark, remove the yellow rule, or add shadows/glows to the mark itself.

## Documentation

- **Diagrams use Mermaid** — every diagram in docs goes in a ` ```mermaid ` block, never ASCII art or prose arrows.
- **The main `README.md` follows the discogsography pattern** — centered header block, theme-aware banner via `<picture>` (`design/assets/banner_dark.png` / `banner_light.png`), shields.io badges, a bold tagline, and a centered nav line, then emoji-prefixed sections.
- **GitHub banners are committed as PNGs** (`design/assets/banner_{light,dark}.png`) rendered from the SVG sources, so the Barlow Condensed wordmark renders correctly instead of falling back to a system font.
