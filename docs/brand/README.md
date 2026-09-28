# onemore — logo

<img src="onemore-horizontal-mono-ae4278.svg" alt="onemore" width="320">

**The idea:** four tally marks and the fifth that closes the count — the rep you log after
you thought you were done. It replaced a dumbbell icon, which said "fitness app" and nothing
about this one.

## Files

| file | use |
| --- | --- |
| `onemore-symbol.svg` | master symbol, 32 px and up |
| `onemore-symbol-small.svg` | small cut for 16–24 px: three heavier bars, no gap |
| `onemore-horizontal.svg` | symbol + wordmark lockup |
| `*-black.svg` / `*-white.svg` | one-colour, for light / dark grounds |
| `*-mono-ae4278.svg`, `*-mono-cd7ba4.svg` | one-colour magenta, for light / dark grounds |
| `onemore-symbol-app-icon.svg` | master on the ink tile |
| `build_mark.py` | regenerates the three masters from their construction |

The served icons live in `src/onemore/static/`: `icon.svg` and `icon-32.png` (browser tab,
small cut on the ink tile), `apple-touch-icon.png` (180 px, full-bleed — iOS rounds the corners),
`icon-192.png`, `icon-512.png`, `maskable-512.png` (manifest), and `mark.svg` (the topbar's
`.brand-mark`, used as a CSS mask filled with `--primary`).

## Construction

On a 256 grid: four bars 30 wide at a 52 pitch, a closing stroke at exactly 30°, all one width
with round terminals, and a 10-unit gap cut into each bar where the diagonal crosses it. The
small cut is three 40-wide bars with no gap. Both are built from arcs and straight lines only
(45 and 20 anchors); `build_mark.py` is the source of truth, not the path data. The wordmark is
DM Serif Display, the app's display face, outlined to paths at −0.02 em tracking.

## Clear space and minimum size

- Keep one bar-width (30/256 of the symbol's height) clear on every side; for the lockup, the
  gap between symbol and wordmark is the minimum.
- Symbol: master down to 32 px, small cut below that, never under 16 px.
- Lockup: at least 120 px wide; below that use the symbol alone.

## Colour

All from the Pale system (`docs/design.md`); contrast is WCAG ratio, 3:1 needed for graphics.

| pair | fg | bg | contrast | use |
| --- | --- | --- | --- | --- |
| app tile | `#CD7BA4` | `#161E1A` | 5.6 | home-screen icon, favicon, dark grounds |
| light | `#AE4278` | `#F1F9F5` | 5.1 | the mark on the app's light background |
| ink | `#161E1A` | `#F1F9F5` | 15.9 | one-colour, print |
| reversed | `#F1F9F5` | `#AE4278` | 5.1 | on a magenta fill |
| green | `#F1F9F5` | `#589878` | 3.2 | large sizes only — the tightest pair |

## Don't

- Don't redraw the diagonal at another angle or let it touch the bars — the gap is the idea.
- Don't use the master below 32 px; that is what the small cut is for.
- Don't set the wordmark in live text or another face.
- Don't add a dumbbell, a plate, or any other gym object alongside it.

## Regenerating the icon set

The PNGs were exported with the `logo-design` Claude skill's `export_variants.py` (cairosvg
backend via `uv run --with cairosvg`): the master for the 180/192/512 and maskable icons with
`--icon-bg "#161E1A" --icon-fg "#CD7BA4" --icon-scale 0.7`, and the small cut on the same tile
for `icon.svg` and `icon-32.png`.
