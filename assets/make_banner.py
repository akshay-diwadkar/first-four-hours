"""Regenerate the README banner: assets/banner.svg.

The banner is a dusk forest scene. The sun's path across the sky is a six-hour clock: hours 1-4 are
gold and sit over a grindstone with the axe on the wheel (sharpen), hours 5-6 are plain and sit over
a stump with the axe in it and the felled log (chop).

The scene is lit from the sun at hour 5: a warm glow and faint stars in the sky, four rows of pines
that grow hazier with distance and fade into ground mist, a thin rim of sunlight on the sun-facing
edges, sparks where the bevel meets the wheel, and grass and ferns in the foreground. It uses
gradients only, no SVG filters, so it paints cheaply.

GitHub shows README images through <img>, which cannot load web fonts, so all text is converted to
outline paths and the SVG depends on no fonts.

    pip install fonttools uharfbuzz
    python assets/make_banner.py

The script downloads the two OFL fonts (DM Serif Display, Nunito Sans) from the google/fonts
repository into a temporary directory. Nothing else is fetched or kept.
"""

import itertools
import math
import random
import tempfile
import urllib.request
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

OUT = Path(__file__).resolve().parent / "banner.svg"
FONT_URLS = {
    "serif": "https://raw.githubusercontent.com/google/fonts/main/ofl/dmserifdisplay/DMSerifDisplay-Regular.ttf",
    "sans": "https://raw.githubusercontent.com/google/fonts/main/ofl/nunitosans/NunitoSans%5BYTLC%2Copsz%2Cwdth%2Cwght%5D.ttf",
}

W, H = 1600, 480
X = 112  # left edge of the title block
GROUND = 458

T = dict(
    sky0="#080c0b", sky1="#1d2a23", fg="#f5efe6", muted="#d9d1c5", accent="#c9a227", sun="#e2b13c",
    g1="#2c4337", g2="#21352b", g3="#172820", ground="#0b130f",
    wood="#9a6d42", wood_dark="#5e432a", wood_hi="#c99359", cut="#d4ae74",
    stone="#918c83", stone_hi="#cbc5b8", stone_lo="#4f4b45",
    steel="#908e8a", steel_hi="#e4e0d8", steel_lo="#4a4845", water="#4a6c71",
    outline="#f3e7cf", outline_op="0.3", shadow_op="0.55",
    haze="#3a4a40", glint="#fff3d6", grass="#1a2a21", grass_lit="#3c4a2f", fern="#0c1611",
)

# The sun's path: an elliptical arc split into six hours.
ARC_CX, ARC_CY, ARC_RX, ARC_RY = 1190, 470, 340, 380
ARC_A0, ARC_A1 = 164.0, 34.0

STUMP_W, STUMP_H = 76, 44


def fmt(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def poly(*pts) -> str:
    return "M " + " L ".join(f"{fmt(x)} {fmt(y)}" for x, y in pts) + " Z"


def mix(a: str, b: str, t: float) -> str:
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


# ---------- text ----------

class Face:
    """A font, instanced at one weight if variable, shaped with HarfBuzz for kerning."""

    def __init__(self, path: Path, wght: float | None = None) -> None:
        tt = TTFont(path)
        if "fvar" in tt:
            axes = {a.axisTag: a.defaultValue for a in tt["fvar"].axes}
            if wght is not None:
                axes["wght"] = wght
            path = path.with_name(f"{path.stem}-{wght}.ttf")
            instantiateVariableFont(tt, axes).save(path)
            tt = TTFont(path)
        self.glyphs = tt.getGlyphSet()
        self.order = tt.getGlyphOrder()
        self.upem = tt["head"].unitsPerEm
        self.hbfont = hb.Font(hb.Face(hb.Blob.from_file_path(str(path))))

    def _shape(self, text):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.hbfont, buf, {"kern": True, "liga": True})
        return buf.glyph_infos, buf.glyph_positions

    def width(self, text: str, size: float, tracking: float = 0.0) -> float:
        infos, pos = self._shape(text)
        return sum(p.x_advance for p in pos) * size / self.upem + tracking * size * (len(infos) - 1)

    def path(self, text: str, x: float, y: float, size: float, tracking: float = 0.0) -> str:
        infos, pos = self._shape(text)
        s = size / self.upem
        commands = []
        for info, p in zip(infos, pos):
            pen = SVGPathPen(self.glyphs, ntos=fmt)
            offset = (s, 0, 0, -s, x + p.x_offset * s, y - p.y_offset * s)
            self.glyphs[self.order[info.codepoint]].draw(TransformPen(pen, offset))
            commands.append(pen.getCommands())
            x += p.x_advance * s + tracking * size
        return " ".join(c for c in commands if c)


FACES: dict[str, Face] = {}


def label(text, x, y, size, fill, anchor="middle", tracking=0.12) -> str:
    f = FACES["bold"]
    w = f.width(text, size, tracking)
    x0 = x - w / 2 if anchor == "middle" else (x - w if anchor == "end" else x)
    return f'<path fill="{fill}" d="{f.path(text, x0, y, size, tracking)}"/>'


def title() -> str:
    f = FACES
    return "\n".join([
        f'<path fill="{T["fg"]}" d="{f["bold"].path("SKILLS FOR AI AGENTS", X, 104, 22, 0.28)}"/>',
        f'<rect x="{X}" y="126" width="72" height="4" fill="{T["accent"]}"/>',
        f'<path fill="{T["fg"]}" d="{f["serif"].path("First Four", X, 262, 150)}"/>',
        f'<path fill="{T["fg"]}" d="{f["serif"].path("Hours", X, 382, 150)}"/>',
        f'<path fill="{T["muted"]}" d="{f["sans"].path("Sharpen the axe first.", X + 4, 444, 40)}"/>',
    ])


# ---------- gradients ----------

_ids = itertools.count(1)


def gid(prefix: str) -> str:
    return f"{prefix}{next(_ids)}"


def lin(id_, stops, x1=0, y1=0, x2=0, y2=1) -> str:
    st = "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in stops)
    return f'<linearGradient id="{id_}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">{st}</linearGradient>'


def stops(st) -> str:
    """Gradient stops from (offset, color) or (offset, color, opacity) tuples."""
    out = []
    for s in st:
        op = f' stop-opacity="{s[2]}"' if len(s) > 2 else ""
        out.append(f'<stop offset="{s[0]}" stop-color="{s[1]}"{op}/>')
    return "".join(out)


def ulin(id_, x1, y1, x2, y2, st) -> str:
    """Linear gradient in user space, so it spans a whole row of shapes."""
    return (f'<linearGradient id="{id_}" gradientUnits="userSpaceOnUse" x1="{fmt(x1)}" y1="{fmt(y1)}" '
            f'x2="{fmt(x2)}" y2="{fmt(y2)}">{stops(st)}</linearGradient>')


def urad(id_, cx, cy, r, st) -> str:
    return (f'<radialGradient id="{id_}" gradientUnits="userSpaceOnUse" cx="{fmt(cx)}" cy="{fmt(cy)}" '
            f'r="{fmt(r)}">{stops(st)}</radialGradient>')


def brad(id_, st) -> str:
    """Radial gradient fitted to the shape's own box."""
    return f'<radialGradient id="{id_}">{stops(st)}</radialGradient>'


# ---------- sky ----------

def arc_pt(hour: float, grow: float = 0.0):
    a = math.radians(ARC_A0 - (ARC_A0 - ARC_A1) * hour / 6)
    return ARC_CX + (ARC_RX + grow) * math.cos(a), ARC_CY - (ARC_RY + grow) * math.sin(a)


def arc_path(h0: float, h1: float) -> str:
    pts = [arc_pt(h0 + (h1 - h0) * i / 40) for i in range(41)]
    return "M " + " L ".join(f"{fmt(x)} {fmt(y)}" for x, y in pts)


SUN = arc_pt(5)


def sky() -> str:
    """Dusk gradient, a warm glow around the sun and along the horizon, and faint stars away from it."""
    sx, sy = SUN
    g0, g1, g2 = gid("sky"), gid("sunglow"), gid("horizon")
    defs = (ulin(g0, 0, 0, 0, H, [(0, "#050908"), (0.5, "#0f1915"), (0.8, "#1b2822"), (1, "#26332a")])
            + urad(g1, sx, sy, 560, [(0, T["sun"], 0.3), (0.18, T["sun"], 0.13), (0.5, T["sun"], 0.04), (1, T["sun"], 0)])
            + urad(g2, 1300, 470, 620, [(0, "#d08a3a", 0.22), (0.45, "#b0743a", 0.08), (1, "#b0743a", 0)]))
    out = [f"<defs>{defs}</defs>", f'<rect width="{W}" height="{H}" fill="url(#{g0})"/>',
           f'<rect width="{W}" height="{H}" fill="url(#{g1})"/>',
           f'<rect width="{W}" height="{H}" fill="url(#{g2})"/>']
    rng = random.Random(5)
    stars = []
    while len(stars) < 70:
        x, y = rng.uniform(10, W - 10), rng.uniform(8, 300)
        if math.hypot(x - sx, y - sy) < 330 or y > 330 - x * 0.05:
            continue
        r = rng.choice((0.6, 0.7, 0.8, 0.9, 1.1, 1.4))
        stars.append(f'<circle cx="{fmt(x)}" cy="{fmt(y)}" r="{r}" opacity="{fmt(rng.uniform(0.18, 0.6))}"/>')
    out.append(f'<g fill="{T["fg"]}">{"".join(stars)}</g>')
    return "".join(out)


def hours() -> str:
    """The six hours: gold for sharpening, dotted for chopping."""
    out = [f'<path fill="none" stroke="{T["accent"]}" stroke-width="4" stroke-linecap="round" d="{arc_path(0, 4)}"/>',
           f'<path fill="none" stroke="{T["muted"]}" stroke-width="3" stroke-linecap="round" stroke-dasharray="1 11" '
           f'opacity="0.7" d="{arc_path(4, 6)}"/>']
    for h in range(7):
        x, y = arc_pt(h)
        if h <= 4:
            out.append(f'<circle cx="{fmt(x)}" cy="{fmt(y)}" r="7" fill="{T["accent"]}"/>')
        else:
            out.append(f'<circle cx="{fmt(x)}" cy="{fmt(y)}" r="6" fill="{T["sky0"]}" stroke="{T["muted"]}" stroke-width="2.5"/>')
    for h in range(1, 7):
        x, y = arc_pt(h - 0.5, 24)
        out.append(label(str(h), x, y + 6, 15, T["accent"] if h <= 4 else T["muted"], tracking=0))
    lx, ly = arc_pt(2.2, -50)
    out.append(label("SHARPEN · 4 HOURS", lx + 20, ly + 24, 15, T["accent"], tracking=0.22))
    lx, ly = arc_pt(5.5, -44)
    out.append(label("CHOP · 2", lx - 6, ly + 18, 15, T["muted"], anchor="end", tracking=0.22))
    return "\n".join(out)


def sun() -> str:
    sx, sy = SUN
    b, c = gid("bloom"), gid("core")
    defs = (brad(b, [(0, T["sun"], 0.55), (0.25, T["sun"], 0.22), (0.6, T["sun"], 0.06), (1, T["sun"], 0)])
            + brad(c, [(0, "#fff6d8"), (0.45, "#f8d77a"), (1, T["sun"])]))
    return (f"<defs>{defs}</defs>"
            f'<circle cx="{fmt(sx)}" cy="{fmt(sy)}" r="120" fill="url(#{b})"/>'
            f'<circle cx="{fmt(sx)}" cy="{fmt(sy)}" r="24" fill="url(#{c})"/>')


# ---------- forest ----------

def pine(x, base, h, w, rng) -> str:
    """Jagged layered pine silhouette as one closed path, trunk included. Used for the far row."""
    tiers = rng.randint(4, 6)
    top = base - h
    crown_base = base - h * 0.03
    right, left = [], []
    for i in range(tiers):
        f = (i + 1) / tiers
        y = top + (crown_base - top) * f
        half = w / 2 * (0.28 + 0.72 * f) * rng.uniform(0.88, 1.08)
        inner = half * rng.uniform(0.42, 0.58)
        y_in = y - (crown_base - top) / tiers * rng.uniform(0.25, 0.4)
        right += [(x + half, y), (x + inner, y_in)] if i < tiers - 1 else [(x + half, y)]
        lh = half * rng.uniform(0.9, 1.1)
        left += [(x - lh, y), (x - inner * rng.uniform(0.9, 1.1), y_in)] if i < tiers - 1 else [(x - lh, y)]
    tw = max(2.0, w * 0.06)
    pts = [(x, top)] + right + [(x + tw, crown_base), (x + tw, base + 10), (x - tw, base + 10), (x - tw, crown_base)]
    return poly(*pts, *reversed(left))


def bough_pine(x, base, h, w, rng) -> str:
    """Pine with curved, drooping boughs, traced as one outline: down the right side, up the left."""
    tiers = max(4, int(h / 15)) + rng.randint(0, 2)
    top = base - h
    crown_base = base - h * 0.04
    step = (crown_base - top) / tiers
    lean = rng.uniform(-0.03, 0.03) * h
    tw = max(2.0, w * 0.05)

    def side(sign):
        segs = [(None, (x + lean * 0.9 + sign * 0.8, top + step * 0.3))]
        for i in range(tiers):
            f = (i + 1) / tiers
            y = top + step * (i + 1) + rng.uniform(-0.15, 0.15) * step
            hw = w / 2 * (0.1 + 0.9 * f) * rng.uniform(0.85, 1.15)
            cx = x + lean * (1 - f)
            tip = (cx + sign * hw, y + step * rng.uniform(0.1, 0.35))
            inner = (cx + sign * hw * rng.uniform(0.25, 0.4), y + step * 0.1)
            # upper edge arches out and droops to the tip; the underside tucks back toward the trunk
            segs.append(((cx + sign * hw * 0.55, y - step * rng.uniform(0.4, 0.65)), tip))
            segs.append(((cx + sign * hw * 0.68, y + step * 0.15), inner))
        segs += [(None, (x + sign * tw, crown_base)), (None, (x + sign * tw, base + 10))]
        return segs

    def seg(c, e):
        return f"L {fmt(e[0])} {fmt(e[1])}" if c is None else f"Q {fmt(c[0])} {fmt(c[1])} {fmt(e[0])} {fmt(e[1])}"

    start = (x + lean, top)
    right, left = side(1), side(-1)
    cmds = [f"M {fmt(start[0])} {fmt(start[1])}"] + [seg(c, e) for c, e in right]
    ends = [start] + [e for _, e in left]
    cmds.append(f"L {fmt(ends[-1][0])} {fmt(ends[-1][1])}")
    cmds += [seg(left[i][0], ends[i]) for i in range(len(left) - 1, -1, -1)]
    return " ".join(cmds) + " Z"


def forest(seed, x0, x1, base, hmin, hmax, density, tree, ground=True, taper_from=None) -> str:
    """Path data for a row of pines; the taper shrinks trees toward x0 so the title side stays calm."""
    rng = random.Random(seed)
    parts = []
    x = x0
    while x < x1:
        h = rng.uniform(hmin, hmax)
        if taper_from is not None and x < taper_from:
            h *= max(0.15, (x - x0) / (taper_from - x0))
        w = h * rng.uniform(0.36, 0.46)
        parts.append(tree(x, base + rng.uniform(-4, 4), h, w, rng))
        x += w * density * rng.uniform(0.6, 1.1)
    if ground:
        lead = 260 if taper_from is not None else 0
        parts.append(f"M {fmt(x0)} {H} Q {fmt(x0 + lead * 0.5)} {fmt(base)} {fmt(x0 + lead)} {fmt(base)} "
                     f"L {fmt(x1 + 40)} {fmt(base)} L {fmt(x1 + 40)} {H} Z")
    return " ".join(parts)


def layer(d, color, top, base, rim=0.0, haze_amt=1.0) -> str:
    """A forest row: solid at the crowns, fading into mist at the base, rim-lit on the sun side.

    The rim is the row drawn in sunlight with the row itself shifted down-left over it, so a thin
    edge of light shows on the right and top of every tree.
    """
    g, p = gid("lg"), gid("lp")
    defs = (ulin(g, 0, top, 0, base + 14, [(0, color), (0.6, color), (1, mix(color, T["haze"], haze_amt))])
            + f'<path id="{p}" d="{d}"/>')
    out = [f"<defs>{defs}</defs><g>"]
    if rim:
        out.append(f'<use href="#{p}" fill="{T["sun"]}" opacity="{rim}"/>')
        out.append(f'<use href="#{p}" fill="url(#{g})" transform="translate(-1.2 1)"/>')
    else:
        out.append(f'<use href="#{p}" fill="url(#{g})"/>')
    out.append("</g>")
    return "".join(out)


def mist(cx, cy, rx, ry, op) -> str:
    g = gid("mist")
    return (f'<defs>{brad(g, [(0, T["haze"], op), (0.55, T["haze"], op * 0.6), (1, T["haze"], 0)])}</defs>'
            f'<ellipse cx="{fmt(cx)}" cy="{fmt(cy)}" rx="{fmt(rx)}" ry="{fmt(ry)}" fill="url(#{g})"/>')


def ground() -> str:
    g = gid("gnd")
    return (f'<defs>{ulin(g, 0, GROUND - 12, 0, H, [(0, "#121d17"), (1, "#060a08")])}</defs>'
            f'<path fill="url(#{g})" d="M 800 480 Q 860 {GROUND} 980 {GROUND} Q 1300 {GROUND - 8} 1640 {GROUND - 4} L 1640 480 Z"/>'
            f'<path fill="none" stroke="{T["sun"]}" stroke-opacity="0.18" stroke-width="1.5" '
            f'd="M 880 {GROUND + 3} Q 920 {GROUND} 980 {GROUND} Q 1300 {GROUND - 8} 1640 {GROUND - 4}"/>')


def grass(x0, x1, seed) -> str:
    """Tufts of curved blades along the ground line; a quarter catch the light."""
    rng = random.Random(seed)
    dark, lit = [], []
    x = x0
    while x < x1:
        y = GROUND - 2 - 4 * (x - 980) / 660 if x > 980 else GROUND + 2
        for _ in range(rng.randint(3, 6)):
            h = rng.uniform(5, 15)
            lean = rng.uniform(-6, 6)
            bx = x + rng.uniform(-3, 3)
            d = (f"M {fmt(bx - 1.2)} {fmt(y + 2)} Q {fmt(bx + lean * 0.3)} {fmt(y - h * 0.6)} {fmt(bx + lean)} {fmt(y - h)} "
                 f"Q {fmt(bx + lean * 0.3 + 1)} {fmt(y - h * 0.5)} {fmt(bx + 1.2)} {fmt(y + 2)} Z")
            (lit if rng.random() < 0.25 else dark).append(d)
        x += rng.uniform(10, 26)
    return f'<path fill="{T["grass"]}" d="{" ".join(dark)}"/><path fill="{T["grass_lit"]}" d="{" ".join(lit)}"/>'


def fern(bx, by, length, angle, curl) -> str:
    """One fern frond: a curved stem with paired leaflets shrinking toward the tip."""
    a = math.radians(angle)
    p0 = (bx, by)
    p2 = (bx + length * math.cos(a), by + length * math.sin(a))
    nx, ny = -math.sin(a), math.cos(a)
    p1 = ((p0[0] + p2[0]) / 2 + nx * curl, (p0[1] + p2[1]) / 2 + ny * curl)

    def at(t):
        u = 1 - t
        x = u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0]
        y = u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]
        dx = 2 * u * (p1[0] - p0[0]) + 2 * t * (p2[0] - p1[0])
        dy = 2 * u * (p1[1] - p0[1]) + 2 * t * (p2[1] - p1[1])
        n = math.hypot(dx, dy)
        return x, y, dx / n, dy / n

    leaves = []
    n = 16
    for i in range(1, n):
        t = i / n
        x, y, tx, ty = at(t)
        size = length * 0.2 * (1 - t) ** 0.8 + 2
        for s in (-1, 1):
            # leaflet points outward and slightly toward the tip
            lx, ly = -ty * s, tx * s
            ex, ey = x + (lx * 0.9 + tx * 0.45) * size, y + (ly * 0.9 + ty * 0.45) * size + size * 0.25
            mx, my = (x + ex) / 2, (y + ey) / 2
            w = size * 0.22
            leaves.append(f"M {fmt(x)} {fmt(y)} Q {fmt(mx + tx * w)} {fmt(my + ty * w)} {fmt(ex)} {fmt(ey)} "
                          f"Q {fmt(mx - tx * w)} {fmt(my - ty * w)} {fmt(x)} {fmt(y)} Z")
    stem = f"M {fmt(p0[0])} {fmt(p0[1])} Q {fmt(p1[0])} {fmt(p1[1])} {fmt(p2[0])} {fmt(p2[1])}"
    return (f'<path fill="none" stroke="{T["fern"]}" stroke-width="2" d="{stem}"/>'
            f'<path fill="{T["fern"]}" d="{" ".join(leaves)}"/>')


def ferns() -> str:
    """A clump in the bottom-right corner and a small one between the two stations."""
    out = [fern(1606, 486, ln, ang, curl) for ang, ln, curl in ((-150, 120, -20), (-125, 140, -16), (-100, 110, 10), (-165, 90, -18))]
    out += [fern(1212, GROUND + 4, ln, ang, curl) for ang, ln, curl in ((-60, 70, 10), (-95, 80, -8), (-125, 60, -10))]
    return "".join(out)


# ---------- props, lit from the sun (upper right) ----------

AXE_HANDLE = ("M -13 -364 C -15 -250 -10 -140 -16 -40 C -18 -14 -24 -4 -30 6 L 22 6 "
              "C 14 -6 12 -20 12 -40 C 10 -140 14 -250 13 -364 Z")
AXE_HEAD = ("M -24 -352 L 30 -352 Q 92 -352 160 -404 Q 204 -312 160 -220 Q 92 -280 30 -278 L -24 -278 "
            "Q -32 -278 -32 -286 L -32 -344 Q -32 -352 -24 -352 Z")
AXE_LOWER_CHEEK = ("M -32 -300 L 30 -300 Q 96 -298 166 -240 Q 162 -228 160 -220 Q 92 -280 30 -278 "
                   "L -24 -278 Q -32 -278 -32 -286 Z")
AXE_BEVEL = "M 138 -384 Q 176 -312 138 -240"
AXE_EDGE = (182.0, -312.0)  # outermost point of the cutting edge; local +x points out of the edge


def outline(width) -> str:
    return (f' stroke="{T["outline"]}" stroke-opacity="{T["outline_op"]}" '
            f'stroke-width="{fmt(width)}" stroke-linejoin="round"')


def shadow(cx, cy, rx, ry) -> str:
    return f'<ellipse cx="{fmt(cx)}" cy="{fmt(cy)}" rx="{fmt(rx)}" ry="{fmt(ry)}" fill="#000" opacity="{T["shadow_op"]}"/>'


def arc(cx, cy, r, deg0, deg1) -> str:
    a0, a1 = math.radians(deg0), math.radians(deg1)
    return (f"M {fmt(cx + r * math.cos(a0))} {fmt(cy + r * math.sin(a0))} "
            f"A {fmt(r)} {fmt(r)} 0 0 1 {fmt(cx + r * math.cos(a1))} {fmt(cy + r * math.sin(a1))}")


def axe(edge_at, angle_deg, scale, mirror=False) -> str:
    """Place the axe so its edge point lands on edge_at, rotated by angle_deg."""
    m = -1 if mirror else 1
    a = math.radians(angle_deg)
    ex, ey = m * scale * AXE_EDGE[0], scale * AXE_EDGE[1]
    tx = edge_at[0] - (ex * math.cos(a) - ey * math.sin(a))
    ty = edge_at[1] - (ex * math.sin(a) + ey * math.cos(a))
    transform = f"translate({fmt(tx)} {fmt(ty)}) rotate({fmt(angle_deg)}) scale({fmt(m * scale)} {fmt(scale)})"
    gh, gs = gid("hdl"), gid("stl")
    defs = (lin(gh, [(0, T["wood_dark"]), (0.45, T["wood_hi"]), (1, T["wood"])], 0, 0, 1, 0)
            + lin(gs, [(0, T["steel_hi"]), (0.55, T["steel"]), (1, T["steel_lo"])]))
    ow = 2.0 / scale
    return (f'<defs>{defs}</defs><g transform="{transform}">'
            f'<path fill="url(#{gh})"{outline(ow)} d="{AXE_HANDLE}"/>'
            f'<path fill="url(#{gs})"{outline(ow)} d="{AXE_HEAD}"/>'
            f'<path fill="{T["steel_lo"]}" opacity="0.5" d="{AXE_LOWER_CHEEK}"/>'
            f'<path fill="none" stroke="{T["steel_hi"]}" stroke-width="{fmt(3.2 / scale)}" stroke-linecap="round" '
            f'opacity="0.85" d="M -22 -344 L 30 -344 Q 88 -344 152 -392"/>'
            f'<path fill="none" stroke="{T["accent"]}" stroke-width="{fmt(6 / scale * scale ** 0.5)}" '
            f'stroke-linecap="round" d="{AXE_BEVEL}"/></g>')


def grindstone(cx, cy, r, ground_y) -> str:
    """Wheel grindstone on an A-frame over a water trough."""
    gw, gt = gid("whl"), gid("trg")
    defs = (f'<radialGradient id="{gw}" cx="0.66" cy="0.3" r="0.85">'
            f'<stop offset="0" stop-color="{T["stone_hi"]}"/><stop offset="0.55" stop-color="{T["stone"]}"/>'
            f'<stop offset="1" stop-color="{T["stone_lo"]}"/></radialGradient>'
            + lin(gt, [(0, T["wood_hi"]), (1, T["wood_dark"])]))
    out = [f"<defs>{defs}</defs>", shadow(cx, ground_y + 1, r * 1.25, r * 0.12)]
    lw = r * 0.15
    out.append(f'<path fill="none" stroke="{T["wood_dark"]}" stroke-width="{fmt(lw)}" stroke-linecap="round" '
               f'd="M {fmt(cx + r * 0.15)} {fmt(cy)} L {fmt(cx + r * 0.95)} {fmt(ground_y)}"/>')
    out.append(f'<path fill="none" stroke="{T["wood"]}" stroke-width="{fmt(lw)}" stroke-linecap="round" '
               f'd="M {fmt(cx - r * 0.15)} {fmt(cy)} L {fmt(cx - r * 0.95)} {fmt(ground_y)}"/>')
    brace_y = cy + (ground_y - cy) * 0.62
    out.append(f'<path stroke="{T["wood"]}" stroke-width="{fmt(r * 0.1)}" stroke-linecap="round" '
               f'd="M {fmt(cx - r * 0.72)} {fmt(brace_y)} L {fmt(cx + r * 0.72)} {fmt(brace_y)}"/>')
    trough = poly((cx - r * 0.85, cy + r * 0.62), (cx + r * 0.85, cy + r * 0.62),
                  (cx + r * 0.75, cy + r * 1.08), (cx - r * 0.75, cy + r * 1.08))
    out.append(f'<path fill="url(#{gt})"{outline(1.4)} d="{trough}"/>')
    # stone: shaded disc, dark band on the shadow side, bright arc on the lit side
    out.append(f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(r)}" fill="url(#{gw})"{outline(1.6)}/>')
    out.append(f'<path fill="none" stroke="{T["stone_lo"]}" stroke-width="{fmt(r * 0.16)}" opacity="0.55" '
               f'd="{arc(cx, cy, r * 0.9, 20, 200)}"/>')
    out.append(f'<path fill="none" stroke="{T["stone_hi"]}" stroke-width="{fmt(r * 0.06)}" stroke-linecap="round" '
               f'opacity="0.9" d="{arc(cx, cy, r * 0.86, -150, -30)}"/>')
    out.append(f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(r * 0.62)}" fill="none" stroke="{T["stone_lo"]}" '
               f'stroke-width="{fmt(r * 0.025)}" opacity="0.6"/>')
    wy = cy + r * 0.78
    water = poly((cx - r * 0.8, wy), (cx + r * 0.8, wy), (cx + r * 0.75, cy + r * 1.08), (cx - r * 0.75, cy + r * 1.08))
    out.append(f'<path fill="{T["water"]}" d="{water}"/>')
    out.append(f'<path stroke="{T["stone_hi"]}" stroke-width="1.5" opacity="0.6" '
               f'd="M {fmt(cx - r * 0.6)} {fmt(wy + 3)} L {fmt(cx + r * 0.6)} {fmt(wy + 3)}"/>')
    out.append(f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(r * 0.15)}" fill="{T["wood_dark"]}"{outline(1.2)}/>')
    out.append(f'<circle cx="{fmt(cx + r * 0.04)}" cy="{fmt(cy - r * 0.04)}" r="{fmt(r * 0.05)}" fill="{T["wood_hi"]}"/>')
    # rotation arrow on the stone's face
    r2 = r * 0.64
    a0, a1 = math.radians(200), math.radians(110)
    p0 = (cx + r2 * math.cos(a0), cy - r2 * math.sin(a0))
    p1 = (cx + r2 * math.cos(a1), cy - r2 * math.sin(a1))
    out.append(f'<path fill="none" stroke="{T["accent"]}" stroke-width="3.5" stroke-linecap="round" '
               f'd="M {fmt(p0[0])} {fmt(p0[1])} A {fmt(r2)} {fmt(r2)} 0 0 1 {fmt(p1[0])} {fmt(p1[1])}"/>')
    out.append(f'<path fill="none" stroke="{T["accent"]}" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" '
               f'd="M {fmt(p1[0] - 10)} {fmt(p1[1] - 7)} L {fmt(p1[0])} {fmt(p1[1])} L {fmt(p1[0] - 9)} {fmt(p1[1] + 8)}"/>')
    # grit speckle across the face
    rng = random.Random(9)
    for _ in range(80):
        a, d = rng.uniform(0, math.tau), r * 0.95 * math.sqrt(rng.uniform(0.05, 0.9))
        out.append(f'<circle cx="{fmt(cx + d * math.cos(a))}" cy="{fmt(cy + d * math.sin(a))}" '
                   f'r="{fmt(rng.uniform(0.5, 1.3))}" fill="{rng.choice((T["stone_lo"], T["stone_hi"]))}" '
                   f'opacity="{fmt(rng.uniform(0.25, 0.6))}"/>')
    # crank on the axle: iron arm, wooden grip
    ex, ey = cx + r * 0.3, cy + r * 0.32
    out.append(f'<path fill="none" stroke="{T["steel_lo"]}" stroke-width="6" stroke-linecap="round" '
               f'd="M {fmt(cx)} {fmt(cy)} L {fmt(ex)} {fmt(ey)}"/>')
    out.append(f'<path fill="none" stroke="{T["steel_hi"]}" stroke-width="1.6" stroke-linecap="round" opacity="0.7" '
               f'd="M {fmt(cx + 1)} {fmt(cy - 2)} L {fmt(ex + 1)} {fmt(ey - 2)}"/>')
    out.append(f'<path fill="none" stroke="{T["wood_dark"]}" stroke-width="9" stroke-linecap="round" '
               f'd="M {fmt(ex)} {fmt(ey)} L {fmt(ex + 9)} {fmt(ey + 7)}"/>')
    out.append(f'<path fill="none" stroke="{T["wood_hi"]}" stroke-width="2.5" stroke-linecap="round" opacity="0.8" '
               f'd="M {fmt(ex + 1)} {fmt(ey - 2)} L {fmt(ex + 9)} {fmt(ey + 4)}"/>')
    out.append(f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(r * 0.06)}" fill="{T["steel_hi"]}"/>')
    # pegs where the brace joins the legs
    t = (brace_y - cy) / (ground_y - cy)
    for s in (-1, 1):
        out.append(f'<circle cx="{fmt(cx + s * (r * 0.15 + r * 0.8 * t))}" cy="{fmt(brace_y)}" r="2.6" '
                   f'fill="{T["wood_hi"]}" opacity="0.9"/>')
    return "".join(out)


def sparks(px, py) -> str:
    """Sparks thrown off where the bevel meets the wheel; the rim runs downward on this side."""
    rng = random.Random(3)
    g = gid("spk")
    out = [f'<defs>{brad(g, [(0, T["glint"], 0.9), (0.3, T["sun"], 0.45), (1, T["sun"], 0)])}</defs>',
           f'<circle cx="{fmt(px)}" cy="{fmt(py)}" r="20" fill="url(#{g})"/>']
    streaks = []
    for _ in range(14):
        a = math.radians(rng.uniform(25, 85))
        d0, d1 = rng.uniform(4, 10), rng.uniform(14, 40)
        x0, y0 = px + d0 * math.cos(a), py + d0 * math.sin(a)
        x1, y1 = px + d1 * math.cos(a), py + d1 * math.sin(a) + (d1 / 40) ** 2 * 6
        col = rng.choice((T["glint"], "#ffd36b", "#f2b640"))
        streaks.append(f'<path stroke="{col}" stroke-width="{fmt(rng.uniform(0.9, 1.8))}" '
                       f'opacity="{fmt(rng.uniform(0.55, 1))}" d="M {fmt(x0)} {fmt(y0)} L {fmt(x1)} {fmt(y1)}"/>')
    out.append(f'<g fill="none" stroke-linecap="round">{"".join(streaks)}</g>')
    out.append(f'<path fill="{T["glint"]}" d="M {fmt(px)} {fmt(py - 9)} L {fmt(px + 1.6)} {fmt(py - 1.6)} L {fmt(px + 9)} {fmt(py)} '
               f'L {fmt(px + 1.6)} {fmt(py + 1.6)} L {fmt(px)} {fmt(py + 9)} L {fmt(px - 1.6)} {fmt(py + 1.6)} '
               f'L {fmt(px - 9)} {fmt(py)} L {fmt(px - 1.6)} {fmt(py - 1.6)} Z"/>')
    return "".join(out)


def felled(x, ground) -> str:
    """The clean cut: a stump with the axe stuck in its top, the felled log beside it, a few chips."""
    rng = random.Random(7)
    sw, sh = STUMP_W, STUMP_H
    top = ground - sh
    gs, gl = gid("stp"), gid("log")
    out = [f'<defs>{lin(gs, [(0, T["wood_dark"]), (0.6, T["wood"]), (1, T["wood_hi"])], 0, 0, 1, 0)}'
           f'{lin(gl, [(0, T["wood_hi"]), (0.35, T["wood"]), (1, T["wood_dark"])])}</defs>']
    lx0, lx1, lr = x + 70, x + 330, 21
    out.append(shadow((lx0 + lx1) / 2, ground + 1, (lx1 - lx0) / 2 + 10, 5))
    out.append(shadow(x, ground + 1, sw * 0.75, 5))
    out.append(f'<path fill="url(#{gl})"{outline(1.4)} d="M {fmt(lx0)} {fmt(ground - 2 * lr)} '
               f'L {fmt(lx1)} {fmt(ground - 2 * lr + 6)} Q {fmt(lx1 + 8)} {fmt(ground - lr)} {fmt(lx1)} {fmt(ground)} '
               f'L {fmt(lx0)} {fmt(ground)} Z"/>')
    bark = (f"M {fmt(lx0 + 30)} {fmt(ground - lr * 1.25)} L {fmt(lx1 - 20)} {fmt(ground - lr * 1.15)} "
            f"M {fmt(lx0 + 60)} {fmt(ground - lr * 0.55)} L {fmt(lx1 - 50)} {fmt(ground - lr * 0.5)} "
            f"M {fmt(lx0 + 110)} {fmt(ground - lr * 1.65)} L {fmt(lx1 - 90)} {fmt(ground - lr * 1.55)}")
    out.append(f'<path fill="none" stroke="{T["wood_dark"]}" stroke-width="1.6" opacity="0.8" stroke-linecap="round" d="{bark}"/>')
    out.append(f'<ellipse cx="{fmt(lx0)}" cy="{fmt(ground - lr)}" rx="{fmt(lr * 0.42)}" ry="{fmt(lr)}" fill="{T["cut"]}"{outline(1.2)}/>')
    for k, w in ((0.62, 1.4), (0.25, 1.2)):
        out.append(f'<ellipse cx="{fmt(lx0)}" cy="{fmt(ground - lr)}" rx="{fmt(lr * 0.42 * k)}" ry="{fmt(lr * k)}" '
                   f'fill="none" stroke="{T["wood"]}" stroke-width="{fmt(w)}"/>')
    out.append(f'<path fill="url(#{gs})"{outline(1.4)} d="M {fmt(x - sw / 2)} {fmt(top)} L {fmt(x + sw / 2)} {fmt(top)} '
               f'L {fmt(x + sw / 2 + 6)} {fmt(ground)} L {fmt(x - sw / 2 - 6)} {fmt(ground)} Z"/>')
    grooves = " ".join(f"M {fmt(x + dx)} {fmt(top + 8)} L {fmt(x + dx * 1.12)} {fmt(ground - 2)}" for dx in (-26, -12, 2, 16, 29))
    out.append(f'<path fill="none" stroke="{T["wood_dark"]}" stroke-width="1.6" opacity="0.75" d="{grooves}"/>')
    out.append(f'<ellipse cx="{fmt(x)}" cy="{fmt(top)}" rx="{fmt(sw / 2)}" ry="9" fill="{T["cut"]}"{outline(1.2)}/>')
    for k, ry, w in ((0.3, 5, 1.4), (0.12, 2, 1.2)):
        out.append(f'<ellipse cx="{fmt(x)}" cy="{fmt(top)}" rx="{fmt(sw * k)}" ry="{ry}" fill="none" '
                   f'stroke="{T["wood"]}" stroke-width="{fmt(w)}"/>')
    # axe stuck in the stump: edge down, handle out to the right
    out.append(axe((x - 6, top + 5), -100, 0.36, mirror=True))
    for _ in range(9):
        cx = x + rng.uniform(-110, 60)
        cy = ground - rng.uniform(0, 4)
        out.append(f'<rect x="{fmt(cx)}" y="{fmt(cy)}" width="{fmt(rng.uniform(5, 10))}" height="3" '
                   f'transform="rotate({fmt(rng.uniform(-40, 40))} {fmt(cx)} {fmt(cy)})" fill="{T["cut"]}"/>')
    return "".join(out)


def stump_detail(x, ground) -> str:
    """Root flare at the stump's base, bark checks between the grooves, and sunlight on its right edge."""
    sw, top = STUMP_W, ground - STUMP_H
    out = []
    for s in (-1, 1):
        bx = x + s * (sw / 2 + 4)
        out.append(f'<path fill="{T["wood_dark"]}" d="M {fmt(bx - s * 4)} {fmt(top + 18)} Q {fmt(bx + s * 2)} {fmt(ground - 6)} '
                   f'{fmt(bx + s * 22)} {fmt(ground + 1)} L {fmt(bx - s * 8)} {fmt(ground + 1)} Z"/>')
        out.append(f'<path fill="none" stroke="{T["wood"]}" stroke-width="1.2" opacity="0.7" '
                   f'd="M {fmt(bx - s * 2)} {fmt(top + 22)} Q {fmt(bx + s * 3)} {fmt(ground - 6)} {fmt(bx + s * 18)} {fmt(ground)}"/>')
    rng = random.Random(4)
    checks = []
    for dx in (-30, -18, -6, 7, 19):
        for _ in range(2):
            y0 = rng.uniform(top + 12, ground - 14)
            checks.append(f"M {fmt(x + dx)} {fmt(y0)} L {fmt(x + dx + 8)} {fmt(y0 + rng.uniform(-2, 2))}")
    out.append(f'<path fill="none" stroke="{T["wood_dark"]}" stroke-width="1.4" opacity="0.8" d="{" ".join(checks)}"/>')
    out.append(f'<path fill="none" stroke="{T["sun"]}" stroke-opacity="0.35" stroke-width="2" '
               f'd="M {fmt(x + sw / 2 + 1)} {fmt(top + 6)} L {fmt(x + sw / 2 + 6)} {fmt(ground - 4)}"/>')
    return "".join(out)


# ---------- scene ----------

def scene() -> tuple[str, str]:
    bg = [sky(), hours(), sun()]
    # forest, far to near: hazier with distance, mist pooling at each row's base; the far row keeps
    # the cheap jagged pine because distance hides bough detail
    bg.append(layer(forest(5, 660, 1640, 404, 45, 90, 0.5, pine, taper_from=860), mix(T["g1"], T["haze"], 0.45), 300, 404))
    bg.append(mist(1220, 408, 640, 26, 0.45))
    bg.append(layer(forest(11, 600, 1640, 420, 70, 130, 0.55, bough_pine, taper_from=900), T["g1"], 290, 420, rim=0.14))
    bg.append(mist(1240, 428, 620, 24, 0.4))
    bg.append(layer(forest(23, 760, 1640, 440, 90, 160, 0.6, bough_pine, taper_from=980), T["g2"], 280, 440, rim=0.18, haze_amt=0.6))
    bg.append(mist(1300, 446, 520, 18, 0.35))
    bg.append(layer(forest(37, 1530, 1640, 452, 110, 170, 0.55, bough_pine, ground=False), T["g3"], 280, 452, rim=0.22, haze_amt=0.3))
    bg.append(ground())

    # sharpening station under the gold hours: axe stood against the wheel, edge on the stone
    gx, gr = 1030, 58
    gy = GROUND - gr * 2.0
    edge = (gx + gr - 1, gy - 6)
    fg = [grindstone(gx, gy, gr, GROUND), axe(edge, -6, 0.37, mirror=True), sparks(*edge)]
    # the clean cut under the plain hours
    fg += [felled(1330, GROUND), stump_detail(1330, GROUND), grass(960, 1600, 2), ferns()]
    return "\n".join(bg), "\n".join(fg)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        fonts = {}
        for name, url in FONT_URLS.items():
            fonts[name] = Path(tmp) / f"{name}.ttf"
            urllib.request.urlretrieve(url, fonts[name])
        FACES["serif"] = Face(fonts["serif"])
        FACES["sans"] = Face(fonts["sans"], wght=400)
        FACES["bold"] = Face(fonts["sans"], wght=800)
        background, foreground = scene()
        heading = title()
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
           f'aria-label="First Four Hours. Skills for AI agents. Sharpen the axe first.">\n'
           f"{background}\n{heading}\n{foreground}\n</svg>\n")
    OUT.write_text(svg, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.name} ({len(svg.encode()) // 1024} KB)")


if __name__ == "__main__":
    main()
