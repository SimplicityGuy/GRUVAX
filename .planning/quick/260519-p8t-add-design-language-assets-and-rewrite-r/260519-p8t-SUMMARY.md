---
quick_id: 260519-p8t
slug: add-design-language-assets-and-rewrite-r
description: Add design-language assets and rewrite README in discogsography pattern
date: 2026-05-20
status: complete
---

# Quick Task 260519-p8t — Summary

## What was delivered

Committed the GRUVAX **Nordic Grid** design-language package and rewrote the
top-level `README.md` to the discogsography header pattern, then wired the
design language into project conventions so future phases use it.

### Design assets (`design/`)
- Tracked the design package: `gruvax-design-language.md` (spec),
  `gruvax-design-tokens.css` / `.json` (tokens), `gruvax-logo-{square,banner,icon}.svg`,
  `gruvax-favicon.svg`.
- Authored `gruvax-logo-banner-dark.svg` — the **Reversed** variant (blue ground,
  white wordmark) for dark backgrounds.
- Rendered both banners to `design/assets/banner_light.png` and
  `design/assets/banner_dark.png` (1600×400) via headless Chromium, so the
  Barlow Condensed wordmark renders correctly instead of falling back to a
  system font (GitHub strips the SVG's Google-Fonts `@import`).

### README
- Centered header using a `<picture>` element with `prefers-color-scheme`
  light/dark `srcset`, `width="600"`.
- Static tooling badges (trimmed by user to License + Python), on one line.
- Bold tagline + centered emoji nav line (anchors verified).
- All prior substantive content preserved; new **Design** section documents the
  palette, type system, and the `design/` package.

### Conventions (GSD-compatible)
- Created `.planning/codebase/CONVENTIONS.md` — the durable source GSD's
  `generate-claude-md` reads for the Conventions block.
- Synced it into `CLAUDE.md`'s `GSD:conventions` block by generating to a temp
  file and copying the byte-identical block, leaving Stack/Project/Architecture
  blocks untouched (idempotent under future `generate-claude-md --auto`).

## Decisions (from user)
1. Badges: static tooling only (then trimmed to License + Python); single line.
2. Logo: pixel-perfect PNGs, light + dark variants via `<picture>`.
3. Content: preserve existing README; restyle header only.
4. Enforce the design language durably via `CONVENTIONS.md` source.

## Verification
- Both banner PNGs verified visually (Barlow Condensed, correct colors).
- README rendered via GitHub's markdown API in light + dark themes; banners,
  one-line badges, nav anchors, and tables confirmed.
- `CLAUDE.md` diff confirmed scoped to the conventions block only.

## Out of scope (future phases)
- Applying design tokens to actual frontend code (UI/frontend phase).
- GitHub Actions workflows for CI-status badges.
