# Vendored faces

The three families `docs/design.md` names, latin subset only, pulled from Google
Fonts' `css2` endpoint and served from here because `web.py`/`static/` must stay
CDN-free — the NAS is tailnet-only, so the export's `@import` lines could never
have resolved. `pale.css` declares them with `@font-face`.

| file | family | upstream | notes |
| --- | --- | --- | --- |
| `plex.woff2` | IBM Plex Sans | https://fonts.google.com/specimen/IBM+Plex+Sans | variable, 100–700 |
| `dmserif.woff2` | DM Serif Display | https://fonts.google.com/specimen/DM+Serif+Display | 400 only; the `label` (600) and `overline` (700) rows synthesise their weight |
| `jbmono.woff2` | JetBrains Mono | https://fonts.google.com/specimen/JetBrains+Mono | variable, 100–800 |

All three are licensed under the SIL Open Font License 1.1
(https://openfontlicense.org). Plex and JetBrains Mono ship as variable faces, so
one file covers every weight the type scale asks for.
