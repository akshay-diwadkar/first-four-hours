"""Regenerate the README banners: assets/banner-light.svg and assets/banner-dark.svg.

GitHub shows README images through <img>, which cannot load web fonts, so this script
converts all text to outline paths. The committed SVGs depend on no fonts.

    pip install fonttools uharfbuzz
    python assets/make_banner.py

The script downloads the two OFL fonts (DM Serif Display, Nunito Sans) from the
google/fonts repository into a temporary directory. Nothing else is fetched or kept.
"""

import tempfile
import urllib.request
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ASSETS = Path(__file__).resolve().parent
FONT_URLS = {
    "serif": "https://raw.githubusercontent.com/google/fonts/main/ofl/dmserifdisplay/DMSerifDisplay-Regular.ttf",
    "sans": "https://raw.githubusercontent.com/google/fonts/main/ofl/nunitosans/NunitoSans%5BYTLC%2Copsz%2Cwdth%2Cwght%5D.ttf",
}

W, H = 1600, 480
X = 112
THEMES = {
    "dark": dict(bg="#0d0d0d", fg="#f5efe6", muted="#d9d1c5", accent="#c9a227"),
    "light": dict(bg="#faf7f2", fg="#141414", muted="#3a3631", accent="#a8851a"),
}

# Line drawing: an axe in side profile with a puck whetstone held against the edge bevel,
# and an arrow showing the circular sharpening stroke. Local origin is the handle's base.
AXE = """<g transform="translate(1185 452) rotate(-18) scale(0.86)" fill="none" stroke-linecap="round" stroke-linejoin="round">
  <g transform="translate(218 -312) rotate(18)">
    <circle r="50" fill="{bg}" stroke="{fg}" stroke-width="5"/>
    <path d="M -50 0 A 50 50 0 0 0 50 0 Z" fill="{fg}" opacity="0.14"/>
    <path d="M -50 0 L 50 0" stroke="{fg}" stroke-width="3"/>
    <path d="M 30 -70 A 76 76 0 0 1 30 70" stroke="{accent}" stroke-width="5"/>
    <path d="M 16 62 L 30 70 L 26 54" stroke="{accent}" stroke-width="5"/>
  </g>
  <path d="M -13 -364 C -15 -250 -10 -140 -16 -40 C -18 -14 -24 -4 -30 6 L 22 6 C 14 -6 12 -20 12 -40 C 10 -140 14 -250 13 -364 Z" stroke="{fg}" stroke-width="5" fill="{bg}"/>
  <path d="M -24 -352 L 30 -352 Q 92 -352 160 -404 Q 204 -312 160 -220 Q 92 -280 30 -278 L -24 -278 Q -32 -278 -32 -286 L -32 -344 Q -32 -352 -24 -352 Z" stroke="{fg}" stroke-width="5" fill="{bg}"/>
  <path d="M 138 -384 Q 176 -312 138 -240" stroke="{accent}" stroke-width="4"/>
</g>
"""


def fmt(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


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

    def path(self, text: str, x: float, y: float, size: float, tracking: float = 0.0) -> str:
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.hbfont, buf, {"kern": True, "liga": True})
        s = size / self.upem
        commands = []
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            pen = SVGPathPen(self.glyphs, ntos=fmt)
            offset = (s, 0, 0, -s, x + pos.x_offset * s, y - pos.y_offset * s)
            self.glyphs[self.order[info.codepoint]].draw(TransformPen(pen, offset))
            commands.append(pen.getCommands())
            x += pos.x_advance * s + tracking * size
        return " ".join(c for c in commands if c)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        fonts = {}
        for name, url in FONT_URLS.items():
            fonts[name] = Path(tmp) / f"{name}.ttf"
            urllib.request.urlretrieve(url, fonts[name])
        serif = Face(fonts["serif"])
        sans = Face(fonts["sans"], wght=400)
        sans_bold = Face(fonts["sans"], wght=700)

        kicker = sans_bold.path("SKILLS FOR AI AGENTS", X, 104, 22, tracking=0.28)
        title1 = serif.path("First Four", X, 262, 150)
        title2 = serif.path("Hours", X, 382, 150)
        tagline = sans.path("Sharpen the axe first.", X + 4, 444, 40)

    for theme, t in THEMES.items():
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="First Four Hours. Skills for AI agents. Sharpen the axe first.">
<rect width="{W}" height="{H}" fill="{t['bg']}"/>
<path fill="{t['fg']}" d="{kicker}"/>
<rect x="{X}" y="126" width="72" height="4" fill="{t['accent']}"/>
<path fill="{t['fg']}" d="{title1}"/>
<path fill="{t['fg']}" d="{title2}"/>
<path fill="{t['muted']}" d="{tagline}"/>
{AXE.format(**t)}</svg>
"""
        out = ASSETS / f"banner-{theme}.svg"
        out.write_text(svg, encoding="utf-8", newline="\n")
        print(f"wrote {out.name} ({len(svg.encode())} bytes)")


if __name__ == "__main__":
    main()
