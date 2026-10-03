# Bundled design fonts

The LAN kiosk serves these unmodified WOFF2 files locally. `fonts.css` preserves
all 19 face/subset declarations from the previous Google Fonts request, including
the same Unicode ranges and `font-display: swap`:

| Family | Requested weights | Subsets |
| --- | --- | --- |
| Barlow Condensed | 700, 900 | Latin, Latin Extended, Vietnamese |
| Space Grotesk | 400, 500, 700 | Latin, Latin Extended, Vietnamese |
| DM Mono | 400, 500 | Latin, Latin Extended |

Space Grotesk's three weight declarations share the upstream variable-font files.
The 19 declarations therefore use 13 distinct files (170,796 bytes total).
Vite resolves the local URLs into its hashed production assets. Docker already
copies the design directory into the frontend build context; no runtime network
or additional package dependency is needed.

## Source and attribution

Retrieved from the official Google Fonts CSS API and `fonts.gstatic.com` on
2026-10-03. `sources.json` records the exact stylesheet request/user agent, its
hash, every face's Unicode range, and the original URL/SHA-256 of each unmodified
font file. Preserve those ranges and requested weights when updating assets.

These fonts are distributed under SIL Open Font License 1.1. Their copyright
notices and full licenses accompany the binaries:

- Barlow Condensed: The Barlow Project Authors; [official license](https://github.com/google/fonts/blob/main/ofl/barlowcondensed/OFL.txt), copied in `OFL-barlow-condensed.txt`.
- Space Grotesk: The Space Grotesk Project Authors; [official license](https://github.com/google/fonts/blob/main/ofl/spacegrotesk/OFL.txt), copied in `OFL-space-grotesk.txt`.
- DM Mono: The DM Mono Project Authors; [official license](https://github.com/google/fonts/blob/main/ofl/dmmono/OFL.txt), copied in `OFL-dm-mono.txt`.

Copyright and license notices must remain with redistributed font copies. Matching
notices in `frontend/public/font-licenses/` are copied by Vite into production
`static/font-licenses/`, so the runtime Docker image includes them too. Keep those
copies identical when updating the originals.
