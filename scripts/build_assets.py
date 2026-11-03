"""Build the SVG assets used by the profile README.

All text is outlined to paths, because GitHub serves README images
without access to web fonts. The palette is sampled from the avatar.

Usage:
    python scripts/build_assets.py path/to/BricolageGrotesque.ttf

Requires fonttools and uharfbuzz. The font is Bricolage Grotesque
(SIL Open Font License), available from Google Fonts.
"""

import math
import pathlib
import sys

import uharfbuzz as hb
from fontTools.misc.transform import Transform
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

BLUE = "#097fe8"
BLUE_DEEP = "#0567c4"
INK = "#0b0d0e"
INK_SOFT = "#3b4147"
WHITE = "#ffffff"

ASSETS = pathlib.Path(__file__).resolve().parent.parent / "assets"


def num(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")


class Type:
    def __init__(self, path):
        self.face = hb.Face(hb.Blob.from_file_path(path))
        self.upem = self.face.upem

    def _font(self, wght, opsz):
        font = hb.Font(self.face)
        font.set_variations({"wght": wght, "opsz": opsz, "wdth": 100})
        return font

    def shape(self, text, size, wght=800, opsz=72, tracking=0.0):
        """Return the font, a list of (glyph id, x, advance) in px, and the run width."""
        font = self._font(wght, opsz)
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(font, buf, {"kern": True})
        scale = size / self.upem
        glyphs, x = [], 0.0
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            advance = pos.x_advance * scale
            glyphs.append((info.codepoint, x + pos.x_offset * scale, advance))
            x += advance + tracking
        return font, glyphs, x - tracking

    def path(self, text, size, x, y, anchor="start", **kw):
        """Outline a single line of text. Returns (path data, width)."""
        font, glyphs, width = self.shape(text, size, **kw)
        if anchor == "middle":
            x -= width / 2
        elif anchor == "end":
            x -= width
        scale = size / self.upem
        pen = SVGPathPen(None, ntos=num)
        for gid, gx, _ in glyphs:
            font.draw_glyph_with_pen(gid, TransformPen(pen, (scale, 0, 0, -scale, x + gx, y)))
        return pen.getCommands(), width

    def glyph_bounds(self, text, index, size, x, y, **kw):
        """Bounds (xmin, ymin, xmax, ymax) in px of one glyph of a run drawn at (x, y)."""
        font, glyphs, _ = self.shape(text, size, **kw)
        gid, gx, _ = glyphs[index]
        scale = size / self.upem
        pen = BoundsPen(None)
        font.draw_glyph_with_pen(gid, TransformPen(pen, (scale, 0, 0, -scale, x + gx, y)))
        return pen.bounds

    def circle_path(self, text, size, radius, start_deg=-90, **kw):
        """Outline text around a circle centred on the origin, spread to fill it exactly."""
        _, glyphs, width = self.shape(text, size, **kw)
        tracking = (2 * math.pi * radius - width) / len(glyphs)
        font, glyphs, _ = self.shape(text, size, tracking=tracking, **kw)
        scale = size / self.upem
        pen = SVGPathPen(None, ntos=num)
        for gid, gx, advance in glyphs:
            phi = math.radians(start_deg) + (gx + advance / 2) / radius
            t = (
                Transform()
                .translate(radius * math.cos(phi), radius * math.sin(phi))
                .rotate(phi + math.pi / 2)
                .translate(-advance / 2, 0)
                .scale(scale, -scale)
            )
            font.draw_glyph_with_pen(gid, TransformPen(pen, tuple(t)))
        return pen.getCommands()


def dot(cx, cy, r):
    return f"M{num(cx - r)} {num(cy)}a{num(r)} {num(r)} 0 1 0 {num(2 * r)} 0a{num(r)} {num(r)} 0 1 0 {num(-2 * r)} 0"


def halftone(width, height, step, radius_at):
    """A field of dots on an offset grid; radius_at(x, y) gives each dot's radius."""
    parts = []
    for row, y in enumerate(range(0, height + step, step)):
        offset = step / 2 if row % 2 else 0
        x = offset
        while x <= width + step:
            r = radius_at(x, y)
            if r > 0.6:
                parts.append(dot(x, y, r))
            x += step
    return "".join(parts)


def falloff(cx, cy, reach, r_max):
    def radius_at(x, y):
        d = math.hypot(x - cx, y - cy)
        return max(0.0, r_max * (1 - d / reach))

    return radius_at


def sparkle(size):
    s, k = size, size * 0.22
    return f"M0 {num(-s)}C{num(k)} {num(-k)} {num(k)} {num(-k)} {num(s)} 0C{num(k)} {num(k)} {num(k)} {num(k)} 0 {num(s)}C{num(-k)} {num(k)} {num(-k)} {num(k)} {num(-s)} 0C{num(-k)} {num(-k)} {num(-k)} {num(-k)} 0 {num(-s)}Z"


FEZ_BODY = "M-34 0C-35 -28 -33 -56 -29 -78Q0 -86 29 -78C33 -56 35 -28 34 0Q0 9 -34 0Z"

MOTION_OFF ="@media (prefers-reduced-motion: reduce) { .m { animation: none !important; } }"


def build_banner(t):
    W, H = 1280, 440
    card_x, card_y, card_w, card_h = 56, 48, 770, 340
    text_x = card_x + 52

    name_size, name_y = 150, 268
    name_d, name_w = t.path("Arman.", name_size, text_x, name_y, wght=800, opsz=96)
    a_x0, apex_y, a_x1, _ = t.glyph_bounds("Arman.", 0, name_size, text_x, name_y, wght=800, opsz=96)
    apex_x = (a_x0 + a_x1) / 2

    hello_d, _ = t.path("Selam, I'm", 40, apex_x + 76, 150, wght=700, opsz=36)
    line1_d, _ = t.path("I build stuff. Apps, AI agents, dashboards,", 25, text_x, 324, wght=500, opsz=24)
    line2_d, _ = t.path("automations: whatever the problem needs.", 25, text_x, 356, wght=500, opsz=24)

    squiggle_y = name_y + 22
    squiggle = f"M{num(text_x + 4)} {num(squiggle_y)}"
    seg = 22
    for i in range(int((name_w - 40) // seg)):
        squiggle += f"q{seg / 2} {-9 if i % 2 == 0 else 9} {seg} 0"

    badge_cx, badge_cy, badge_r = 1062, 214, 148
    ring_d = t.circle_path("FEZ ON • SHIP IT • FEZ ON • SHIP IT • ", 24, 112, wght=800, opsz=24)

    dots = halftone(W, H, 14, falloff(1180, 400, 560, 5.2))
    dots_tl = halftone(W, H, 14, falloff(0, 0, 230, 4.2))

    fez_dx, fez_dy = apex_x + 4, apex_y + 6

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="title desc">
<title id="title">Selam, I'm Arman.</title>
<desc id="desc">I build stuff. Apps, AI agents, dashboards, automations: whatever the problem needs.</desc>
<style>
.m {{ transform-box: view-box; transform-origin: 0 0; }}
.swing {{ animation: swing 2.6s ease-in-out infinite alternate; }}
.spin {{ animation: spin 28s linear infinite; }}
.glint {{ animation: glint 4.5s ease-in-out infinite; }}
.twinkle {{ animation: twinkle 2.4s ease-in-out infinite; }}
.draw {{ stroke-dasharray: 900; animation: draw 1.6s cubic-bezier(.65,0,.35,1) .3s backwards; }}
@keyframes swing {{ from {{ transform: rotate(-18deg); }} to {{ transform: rotate(6deg); }} }}
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}
@keyframes glint {{ 0%, 55% {{ transform: translateX(-120px); }} 80%, 100% {{ transform: translateX(140px); }} }}
@keyframes twinkle {{ 0%, 100% {{ transform: scale(1) rotate(0deg); }} 50% {{ transform: scale(.55) rotate(45deg); }} }}
@keyframes draw {{ from {{ stroke-dashoffset: 900; }} to {{ stroke-dashoffset: 0; }} }}
{MOTION_OFF}
</style>
<defs>
  <clipPath id="frame"><rect width="{W}" height="{H}" rx="28"/></clipPath>
  <pattern id="dots" width="5" height="5" patternUnits="userSpaceOnUse">
    <rect width="5" height="5" fill="{WHITE}"/><circle cx="2.5" cy="2.5" r="1.25" fill="{INK}"/>
  </pattern>
  <clipPath id="fez-body"><path d="{FEZ_BODY}"/></clipPath>
  <pattern id="dots-dense" width="4" height="4" patternUnits="userSpaceOnUse">
    <rect width="4" height="4" fill="{WHITE}"/><circle cx="2" cy="2" r="1.35" fill="{INK}"/>
  </pattern>
  <clipPath id="lenses"><path d="M-80 -22h70v30q0 14 -14 14h-42q-14 0 -14 -14zM10 -22h70v30q0 14 -14 14h-42q-14 0 -14 -14z"/></clipPath>
</defs>
<g clip-path="url(#frame)">
  <rect width="{W}" height="{H}" fill="{BLUE}"/>
  <path d="{dots}{dots_tl}" fill="{BLUE_DEEP}"/>

  <!-- pencil tucked behind the badge -->
  <g transform="translate({badge_cx} {badge_cy}) rotate(-34)">
    <rect x="-236" y="-17" width="430" height="34" rx="4" fill="{INK}" transform="translate(1.4 11.2)"/>
    <rect x="-236" y="-17" width="430" height="34" rx="4" fill="url(#dots)" stroke="{INK}" stroke-width="4.5"/>
    <path d="M-236 -6H194M-236 6H194" stroke="{INK}" stroke-width="2.5"/>
    <rect x="-236" y="-17" width="38" height="34" rx="4" fill="{WHITE}" stroke="{INK}" stroke-width="4.5"/>
    <path d="M194 -17L246 0L194 17Z" fill="{WHITE}" stroke="{INK}" stroke-width="4.5" stroke-linejoin="round"/>
    <path d="M230 -5.5L246 0L230 5.5Z" fill="{INK}"/>
  </g>

  <!-- badge -->
  <g transform="translate({badge_cx} {badge_cy})">
    <circle r="{badge_r}" fill="{INK}" transform="translate(10 10)"/>
    <circle r="{badge_r}" fill="{WHITE}" stroke="{INK}" stroke-width="5"/>
    <g class="m spin"><path d="{ring_d}" fill="{INK}"/></g>
    <circle r="96" fill="{BLUE}" stroke="{INK}" stroke-width="4.5"/>
    <g transform="translate(0 8)">
      <path d="M-80 -22h70v30q0 14 -14 14h-42q-14 0 -14 -14zM10 -22h70v30q0 14 -14 14h-42q-14 0 -14 -14z" fill="{INK}"/>
      <path d="M-12 -16h24" stroke="{INK}" stroke-width="7" stroke-linecap="round"/>
      <path d="M-80 -18l-10 -6M80 -18l10 -6" stroke="{INK}" stroke-width="6" stroke-linecap="round"/>
      <g clip-path="url(#lenses)">
        <g class="m glint"><path d="M-20 -40h14l-30 80h-14zM2 -40h6l-30 80h-6z" fill="{WHITE}" opacity=".9"/></g>
      </g>
    </g>
  </g>

  <!-- card -->
  <rect x="{card_x + 12}" y="{card_y + 12}" width="{card_w}" height="{card_h}" rx="22" fill="{INK}"/>
  <rect x="{card_x}" y="{card_y}" width="{card_w}" height="{card_h}" rx="22" fill="{WHITE}" stroke="{INK}" stroke-width="5"/>

  <path d="{hello_d}" fill="{INK}"/>
  <path class="m draw" d="{squiggle}" fill="none" stroke="{BLUE}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="{name_d}" fill="{INK}"/>
  <path d="{line1_d}{line2_d}" fill="{INK_SOFT}"/>

  <!-- fez perched on the A -->
  <g transform="translate({num(fez_dx)} {num(fez_dy)}) rotate(-8)">
    <path d="{FEZ_BODY}" fill="url(#dots)"/>
    <rect x="12" y="-90" width="30" height="100" fill="url(#dots-dense)" clip-path="url(#fez-body)"/>
    <path d="{FEZ_BODY}" fill="none" stroke="{INK}" stroke-width="5" stroke-linejoin="round"/>
    <ellipse cx="0" cy="-78" rx="29" ry="7" fill="url(#dots)" stroke="{INK}" stroke-width="4.5"/>
    <circle cx="0" cy="-79" r="4.5" fill="{INK}"/>
    <path d="M0 -79Q18 -85 29 -77" fill="none" stroke="{INK}" stroke-width="5.5" stroke-linecap="round"/>
    <g transform="translate(29 -77)">
      <g class="m swing">
        <path d="M0 0Q7 6 7 24" fill="none" stroke="{INK}" stroke-width="5.5" stroke-linecap="round"/>
        <path d="M2 22h10l6 30q-11 5 -22 0z" fill="{INK}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>
      </g>
    </g>
  </g>

  <!-- sparkles -->
  <g transform="translate(884 70)"><path class="m twinkle" d="{sparkle(16)}" fill="{WHITE}" stroke="{INK}" stroke-width="3" stroke-linejoin="round"/></g>
  <g transform="translate(1240 172)"><path class="m twinkle" style="animation-delay:-.8s" d="{sparkle(20)}" fill="{WHITE}" stroke="{INK}" stroke-width="3" stroke-linejoin="round"/></g>
  <g transform="translate(906 404)"><path class="m twinkle" style="animation-delay:-1.6s" d="{sparkle(12)}" fill="{WHITE}" stroke="{INK}" stroke-width="3" stroke-linejoin="round"/></g>
  <g transform="translate(1226 404)"><path class="m twinkle" style="animation-delay:-1.1s" d="{sparkle(9)}" fill="{WHITE}" stroke="{INK}" stroke-width="2.5" stroke-linejoin="round"/></g>
</g>
</svg>
"""
    (ASSETS / "banner.svg").write_text(svg)


STACK = [
    ("Swift", "#f05138"),
    ("SwiftUI", "#0a84ff"),
    ("TypeScript", "#3178c6"),
    ("React", "#58c4dc"),
    ("Next.js", INK),
    ("Tailwind CSS", "#38bdf8"),
    ("Python", "#ffd43b"),
    ("C# / .NET", "#512bd4"),
    ("Azure", "#0078d4"),
    ("Power Platform", "#742774"),
    ("Copilot Studio", "#0e9f8f"),
    ("Claude Code", "#d97757"),
]
PER_ROW = 4


def build_stack(t):
    W, H = 1280, 258
    size, height, gap = 26, 54, 22
    rows = [STACK[i : i + PER_ROW] for i in range(0, len(STACK), PER_ROW)]
    tilts = [-3, 2, -1.5, 2.5, -2, 1.5, -2.5, 2, -1, 3, -2, 1.5]
    stickers, i = [], 0
    for row_index, row in enumerate(rows):
        widths = [t.shape(label, size, wght=700, opsz=24)[2] + 74 for label, _ in row]
        x = (W - sum(widths) - gap * (len(row) - 1)) / 2
        cy = 46 + row_index * 82
        for (label, color), w in zip(row, widths):
            text_d, _ = t.path(label, size, 50, 9, wght=700, opsz=24)
            stickers.append(
                f"""<g transform="translate({num(x)} {num(cy)}) rotate({tilts[i]} {num(w / 2)} 0)">
  <g class="m bob" style="animation-delay:{-0.37 * i:.2f}s">
    <rect x="0" y="{-height / 2}" width="{num(w)}" height="{height}" rx="{height / 2}" fill="{BLUE}" transform="translate(5 5)"/>
    <rect x="0" y="{-height / 2}" width="{num(w)}" height="{height}" rx="{height / 2}" fill="{WHITE}" stroke="{INK}" stroke-width="3.5"/>
    <circle cx="30" cy="0" r="9" fill="{color}" stroke="{INK}" stroke-width="2.5"/>
    <path d="{text_d}" fill="{INK}"/>
  </g>
</g>"""
            )
            x += w + gap
            i += 1

    labels = ", ".join(label for label, _ in STACK)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="title">
<title id="title">{labels.replace("&", "&amp;")}</title>
<style>
.m {{ transform-box: view-box; transform-origin: 0 0; }}
.bob {{ animation: bob 3.2s ease-in-out infinite; }}
@keyframes bob {{ 0%, 100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-5px); }} }}
{MOTION_OFF}
</style>
{chr(10).join(stickers)}
</svg>
"""
    (ASSETS / "stack.svg").write_text(svg)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    t = Type(sys.argv[1])
    ASSETS.mkdir(exist_ok=True)
    build_banner(t)
    build_stack(t)


if __name__ == "__main__":
    main()
