"""Regenerate the README banner: assets/banner.svg.

The banner is a dusk forest scene. The sun's path across the sky is a six-hour clock: hours 1-4 are
gold and sit over a grindstone with the axe on the wheel (sharpen), hours 5-6 are plain and sit over
a stump with the axe in it and the felled log (chop).

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
)

# The sun's path: an elliptical arc split into six hours.
ARC_CX, ARC_CY, ARC_RX, ARC_RY = 1190, 470, 340, 380
ARC_A0, ARC_A1 = 164.0, 34.0


def fmt(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def poly(*pts) -> str:
    return "M " + " L ".join(f"{fmt(x)} {fmt(y)}" for x, y in pts) + " Z"


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


# ---------- forest ----------

def pine(x, base, h, w, rng) -> str:
    """Jagged layered pine silhouette as one closed path, trunk included."""
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


def forest_layer(seed, x0, x1, base, hmin, hmax, density, fill, ground=True, taper_from=None) -> str:
    """A row of pines; the taper shrinks trees toward x0 so the title side stays calm."""
    rng = random.Random(seed)
    parts = []
    x = x0
    while x < x1:
        h = rng.uniform(hmin, hmax)
        if taper_from is not None and x < taper_from:
            h *= max(0.15, (x - x0) / (taper_from - x0))
        w = h * rng.uniform(0.36, 0.46)
        parts.append(pine(x, base + rng.uniform(-4, 4), h, w, rng))
        x += w * density * rng.uniform(0.6, 1.1)
    if ground:
        lead = 260 if taper_from is not None else 0
        parts.append(f"M {fmt(x0)} {H} Q {fmt(x0 + lead * 0.5)} {fmt(base)} {fmt(x0 + lead)} {fmt(base)} "
                     f"L {fmt(x1 + 40)} {fmt(base)} L {fmt(x1 + 40)} {H} Z")
    return f'<path fill="{fill}" d="{" ".join(parts)}"/>'


# ---------- props, lit from the sun (upper right) ----------

AXE_HANDLE = ("M -13 -364 C -15 -250 -10 -140 -16 -40 C -18 -14 -24 -4 -30 6 L 22 6 "
              "C 14 -6 12 -20 12 -40 C 10 -140 14 -250 13 -364 Z")
AXE_HEAD = ("M -24 -352 L 30 -352 Q 92 -352 160 -404 Q 204 -312 160 -220 Q 92 -280 30 -278 L -24 -278 "
            "Q -32 -278 -32 -286 L -32 -344 Q -32 -352 -24 -352 Z")
AXE_LOWER_CHEEK = ("M -32 -300 L 30 -300 Q 96 -298 166 -240 Q 162 -228 160 -220 Q 92 -280 30 -278 "
                   "L -24 -278 Q -32 -278 -32 -286 Z")
AXE_BEVEL = "M 138 -384 Q 176 -312 138 -240"
AXE_EDGE = (182.0, -312.0)  # outermost point of the cutting edge; local +x points out of the edge

_ids = itertools.count(1)


def gid(prefix: str) -> str:
    return f"{prefix}{next(_ids)}"


def lin(id_, stops, x1=0, y1=0, x2=0, y2=1) -> str:
    st = "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in stops)
    return f'<linearGradient id="{id_}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">{st}</linearGradient>'


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
    return "".join(out)


def felled(x, ground) -> str:
    """The clean cut: a stump with the axe stuck in its top, the felled log beside it, a few chips."""
    rng = random.Random(7)
    sw, sh = 76, 44
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


# ---------- scene ----------

def arc_pt(hour: float, grow: float = 0.0):
    a = math.radians(ARC_A0 - (ARC_A0 - ARC_A1) * hour / 6)
    return ARC_CX + (ARC_RX + grow) * math.cos(a), ARC_CY - (ARC_RY + grow) * math.sin(a)


def arc_path(h0: float, h1: float) -> str:
    pts = [arc_pt(h0 + (h1 - h0) * i / 40) for i in range(41)]
    return "M " + " L ".join(f"{fmt(x)} {fmt(y)}" for x, y in pts)


def scene() -> tuple[str, str]:
    bg = [f'<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{T["sky0"]}"/>'
          f'<stop offset="1" stop-color="{T["sky1"]}"/></linearGradient></defs><rect width="{W}" height="{H}" fill="url(#sky)"/>']
    # the six hours: gold for sharpening, dotted for chopping
    bg.append(f'<path fill="none" stroke="{T["accent"]}" stroke-width="4" stroke-linecap="round" d="{arc_path(0, 4)}"/>')
    bg.append(f'<path fill="none" stroke="{T["muted"]}" stroke-width="3" stroke-linecap="round" stroke-dasharray="1 11" '
              f'opacity="0.7" d="{arc_path(4, 6)}"/>')
    for h in range(7):
        x, y = arc_pt(h)
        if h <= 4:
            bg.append(f'<circle cx="{fmt(x)}" cy="{fmt(y)}" r="7" fill="{T["accent"]}"/>')
        else:
            bg.append(f'<circle cx="{fmt(x)}" cy="{fmt(y)}" r="6" fill="{T["sky0"]}" stroke="{T["muted"]}" stroke-width="2.5"/>')
    for h in range(1, 7):
        x, y = arc_pt(h - 0.5, 24)
        bg.append(label(str(h), x, y + 6, 15, T["accent"] if h <= 4 else T["muted"], tracking=0))
    sx, sy = arc_pt(5)
    bg.append(f'<circle cx="{fmt(sx)}" cy="{fmt(sy)}" r="54" fill="{T["sun"]}" opacity="0.12"/>')
    bg.append(f'<circle cx="{fmt(sx)}" cy="{fmt(sy)}" r="38" fill="{T["sun"]}" opacity="0.2"/>')
    bg.append(f'<circle cx="{fmt(sx)}" cy="{fmt(sy)}" r="24" fill="{T["sun"]}"/>')
    lx, ly = arc_pt(2.2, -50)
    bg.append(label("SHARPEN · 4 HOURS", lx + 20, ly + 24, 15, T["accent"], tracking=0.22))
    lx, ly = arc_pt(5.5, -44)
    bg.append(label("CHOP · 2", lx - 6, ly + 18, 15, T["muted"], anchor="end", tracking=0.22))
    # forest, far to near, and the ground
    bg.append(forest_layer(11, 600, 1640, 420, 70, 130, 0.55, T["g1"], taper_from=900))
    bg.append(forest_layer(23, 760, 1640, 440, 90, 160, 0.6, T["g2"], taper_from=980))
    bg.append(forest_layer(37, 1530, 1640, 452, 110, 170, 0.55, T["g3"], ground=False))
    bg.append(f'<path fill="{T["ground"]}" d="M 800 480 Q 860 {GROUND} 980 {GROUND} Q 1300 {GROUND - 8} 1640 {GROUND - 4} L 1640 480 Z"/>')

    # sharpening station under the gold hours: axe stood against the wheel, edge on the stone
    gx, gr = 1030, 58
    gy = GROUND - gr * 2.0
    fg = [grindstone(gx, gy, gr, GROUND), axe((gx + gr - 1, gy - 6), -6, 0.37, mirror=True)]
    # the clean cut under the plain hours
    fg.append(felled(1330, GROUND))
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
