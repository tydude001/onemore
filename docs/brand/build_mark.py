"""Regenerate the onemore mark from its construction.

    uv run --no-project --with fonttools,brotli python3 docs/brand/build_mark.py

Writes onemore-symbol.svg, onemore-symbol-small.svg and onemore-horizontal.svg next to this
file. The symbols need nothing beyond the standard library; the lockup outlines the wordmark
from the vendored DM Serif Display, which needs fonttools + brotli.

Construction, on a 256 grid: four vertical strokes and a closing stroke at exactly 30°, one
width, round terminals. Where the diagonal crosses a bar the bar is cut back by a clear gap so
the fifth mark reads as laid on top. The small cut (16–24 px) has three heavier bars and no
gap, because a gap closes up at favicon size.
"""
import math
from pathlib import Path

HERE = Path(__file__).parent
FONT = HERE.parents[1] / "src/onemore/static/fonts/dmserif.woff2"
T = math.tan(math.radians(30))
SIN, COS = math.sin(math.radians(30)), math.cos(math.radians(30))


def f(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def y_diag(x):
    return 128 - (x - 128) * T


def pill_v(x, top, bottom, h):
    return (f"M{f(x - h)} {f(top)}A{f(h)} {f(h)} 0 0 1 {f(x + h)} {f(top)}"
            f"V{f(bottom)}A{f(h)} {f(h)} 0 0 1 {f(x - h)} {f(bottom)}Z")


def pill_diag(dx, h):
    p1, p2 = (128 - dx, 128 + dx * T), (128 + dx, 128 - dx * T)
    n = (SIN * h, COS * h)
    a1, a2 = (p1[0] - n[0], p1[1] - n[1]), (p2[0] - n[0], p2[1] - n[1])
    b2, b1 = (p2[0] + n[0], p2[1] + n[1]), (p1[0] + n[0], p1[1] + n[1])
    return (f"M{f(a1[0])} {f(a1[1])}L{f(a2[0])} {f(a2[1])}A{f(h)} {f(h)} 0 0 1 {f(b2[0])} {f(b2[1])}"
            f"L{f(b1[0])} {f(b1[1])}A{f(h)} {f(h)} 0 0 1 {f(a1[0])} {f(a1[1])}Z")


def tally(bars_x, top, bottom, w, gap, dx):
    h = w / 2
    d = []
    if gap:
        v = (h + gap) / COS  # vertical half-height of the knockout band
        for x in bars_x:
            xl, xr = x - h, x + h
            up_l, up_r = y_diag(xl) - v, y_diag(xr) - v
            lo_l, lo_r = y_diag(xl) + v, y_diag(xr) + v
            assert up_r > top and lo_l < bottom, "cut reaches into a cap: lengthen the bars"
            d.append(f"M{f(xl)} {f(up_l)}V{f(top)}A{f(h)} {f(h)} 0 0 1 {f(xr)} {f(top)}V{f(up_r)}Z")
            d.append(f"M{f(xl)} {f(lo_l)}V{f(bottom)}A{f(h)} {f(h)} 0 0 0 {f(xr)} {f(bottom)}V{f(lo_r)}Z")
    else:
        d += [pill_v(x, top, bottom, h) for x in bars_x]
    d.append(pill_diag(dx, h))
    return "".join(d)


MASTER = tally([50, 102, 154, 206], 44, 212, w=30, gap=10, dx=100)
SMALL = tally([62, 128, 194], 52, 204, w=40, gap=0, dx=106)


def svg(body, w=256):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} 256" width="{w}" height="256">'
            f'<title>onemore logo</title>{body}</svg>\n')


def wordmark(x, baseline=182, size=176, tracking=-0.02):
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.ttLib import TTFont

    font = TTFont(FONT)
    gs, cmap = font.getGlyphSet(), font.getBestCmap()
    s = size / font["head"].unitsPerEm
    pen = SVGPathPen(gs, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip("."))
    for ch in "onemore":
        g = cmap[ord(ch)]
        gs[g].draw(TransformPen(pen, (s, 0, 0, -s, x, baseline)))
        x += gs[g].width * s + tracking * size
    return pen.getCommands(), x - tracking * size


if __name__ == "__main__":
    (HERE / "onemore-symbol.svg").write_text(svg(f'<path fill="#111" d="{MASTER}"/>'))
    (HERE / "onemore-symbol-small.svg").write_text(svg(f'<path fill="#111" d="{SMALL}"/>'))
    d, end = wordmark(236)
    sym = f'<path fill="#111" transform="translate(0 32) scale(0.75)" d="{MASTER}"/>'
    (HERE / "onemore-horizontal.svg").write_text(svg(f'{sym}<path fill="#111" d="{d}"/>', w=math.ceil(end + 4)))
    print("wrote onemore-symbol.svg, onemore-symbol-small.svg, onemore-horizontal.svg")
