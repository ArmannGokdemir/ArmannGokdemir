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

# The glasses slide down to look at the viewer on an irregular schedule.
# One long cycle with uneven gaps reads as random; CSS has no real randomness.
PEEK_CYCLE = 100  # seconds, so keyframe percentages below are also seconds
PEEKS = [(3.0, 4.6), (13.0, 15.8), (21.5, 22.6), (40.0, 43.4), (47.0, 48.0), (49.2, 50.6), (66.0, 68.4), (83.5, 84.6), (91.0, 93.6)]
BLINKS = [14.6, 41.8, 67.2, 92.4]


def pct(v):
    return f"{v:.2f}".rstrip("0").rstrip(".") + "%"


def schedule(rest, active, spans, ramp=0.4):
    frames = [f"0% {{ transform: {rest}; }}"]
    for start, end in spans:
        frames.append(
            f"{pct(start)} {{ transform: {rest}; }} {pct(start + ramp)}, {pct(end)} {{ transform: {active}; }} {pct(end + ramp)} {{ transform: {rest}; }}"
        )
    frames.append(f"100% {{ transform: {rest}; }}")
    return " ".join(frames)


def blink_frames():
    frames = ["0% { transform: scaleY(1); }"]
    for at in BLINKS:
        frames.append(f"{pct(at)} {{ transform: scaleY(1); }} {pct(at + 0.12)} {{ transform: scaleY(.1); }} {pct(at + 0.24)} {{ transform: scaleY(1); }}")
    frames.append("100% { transform: scaleY(1); }")
    return " ".join(frames)


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
    ring_d = t.circle_path("BUILD IT • SHIP IT • BUILD IT • SH— OOH, NEW IDEA! • ", 24, 112, wght=800, opsz=24)

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
.peek {{ animation: peek {PEEK_CYCLE}s ease-in-out infinite; }}
.brow {{ animation: brow {PEEK_CYCLE}s ease-in-out infinite; }}
.blink {{ animation: blink {PEEK_CYCLE}s linear infinite; }}
@keyframes peek {{ {schedule("translateY(0)", "translateY(18px)", PEEKS)} }}
@keyframes brow {{ {schedule("translateY(0) rotate(0deg)", "translateY(-8px) rotate(-6deg)", PEEKS)} }}
@keyframes blink {{ {blink_frames()} }}
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
    <!-- eyes sit behind the lenses and show when the glasses slide down -->
    <g transform="translate(-45 0)"><g class="m blink">
      <ellipse rx="15" ry="11" fill="{WHITE}" stroke="{INK}" stroke-width="3.5"/>
      <circle r="5.5" fill="{INK}"/><circle cx="-1.8" cy="-2" r="1.6" fill="{WHITE}"/>
    </g></g>
    <g transform="translate(45 0)"><g class="m blink">
      <ellipse rx="15" ry="11" fill="{WHITE}" stroke="{INK}" stroke-width="3.5"/>
      <circle r="5.5" fill="{INK}"/><circle cx="-1.8" cy="-2" r="1.6" fill="{WHITE}"/>
    </g></g>
    <path d="M-70 -28Q-48 -40 -24 -31" fill="none" stroke="{INK}" stroke-width="8" stroke-linecap="round"/>
    <g transform="translate(47 -32)"><g class="m brow">
      <path d="M-23 1Q1 -8 23 4" fill="none" stroke="{INK}" stroke-width="8" stroke-linecap="round"/>
    </g></g>
    <g transform="translate(0 8)"><g class="m peek">
      <path d="M-80 -22h70v30q0 14 -14 14h-42q-14 0 -14 -14zM10 -22h70v30q0 14 -14 14h-42q-14 0 -14 -14z" fill="{INK}"/>
      <path d="M-12 -16h24" stroke="{INK}" stroke-width="7" stroke-linecap="round"/>
      <path d="M-80 -18l-10 -6M80 -18l10 -6" stroke="{INK}" stroke-width="6" stroke-linecap="round"/>
      <g clip-path="url(#lenses)">
        <g class="m glint"><path d="M-20 -40h14l-30 80h-14zM2 -40h6l-30 80h-6z" fill="{WHITE}" opacity=".9"/></g>
      </g>
    </g></g>
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


YELLOW = "#ffd23f"

# (idea, how far it got before the next idea showed up, in percent)
IDEAS = [
    ("A to-do app, but this time it’s different", 64),
    ("An AI agent that writes my standup", 88),
    ("A smart fridge that judges my snacks", 41),
    ("Rewrite everything in Rust", 12),
    ("A menu bar app for my menu bar apps", 93),
    ("Uber, but for çay", 57),
    ("Finish the last idea", 3),
]
FIRST_IDEA_NUMBER = 212
SLOT = 5.0  # seconds each idea gets before it is abandoned


def lightbulb():
    return (
        f'<path d="M0 -17a13 13 0 0 1 8 23v5h-16v-5a13 13 0 0 1 8 -23z" fill="{WHITE}" stroke="{INK}" stroke-width="3.5" stroke-linejoin="round"/>'
        f'<path d="M-6 15h12M-4 20h8" stroke="{INK}" stroke-width="3.5" stroke-linecap="round"/>'
        f'<path d="M0 -25v-6M18 -16l5 -4M-18 -16l-5 -4" stroke="{INK}" stroke-width="3" stroke-linecap="round"/>'
    )


def build_ticker(t):
    W, H = 1280, 240
    card_x, card_y, card_w, card_h = 24, 18, 1218, 194
    left = card_x + 40
    bar_x, bar_y, bar_w, bar_h = left, 156, 880, 28
    name_size, name_y = 46, 130
    cycle = SLOT * len(IDEAS)

    def at(seconds):
        return pct(seconds / cycle * 100)

    def at_slot(seconds):
        return pct(seconds / SLOT * 100)

    pill_text_d, pill_text_w = t.path("NOW BUILDING", 17, left + 36, 64, wght=800, opsz=24)
    pill_w = pill_text_w + 54
    sticker_d, sticker_w = t.path("OOH, NEW IDEA!", 26, 0, 0, wght=800, opsz=24)

    styles, ideas = [], []
    for i, (idea, progress) in enumerate(IDEAS):
        delay = f"animation-delay:{num(i * SLOT)}s"
        name_d, name_w = t.path(idea, name_size, left, name_y, wght=800, opsz=48)
        number_d, _ = t.path(f"IDEA #{FIRST_IDEA_NUMBER + i}", 17, left + pill_w + 18, 64, wght=700, opsz=24)
        verdict_d, _ = t.path(f"{progress}% · abandoned", 22, bar_x + bar_w + 22, bar_y + 21, wght=700, opsz=24)

        strike_y = name_y - name_size * 0.3
        strike = f"M{num(left - 8)} {num(strike_y + 3)}"
        steps = max(2, int((name_w + 16) // 38))
        step_w = (name_w + 16) / steps
        for k in range(steps):
            strike += f"q{num(step_w / 2)} {-7 if k % 2 == 0 else 7} {num(step_w)} {-1 if k % 2 == 0 else 1}"

        # A white cover slides right to reveal the striped fill, so the stripes never stretch.
        filled = bar_w * progress / 100
        styles.append(
            f"@keyframes fill-{i} {{ 0%, {at(0.5)} {{ transform: translateX(0); }} {at(1.3)} {{ transform: translateX({num(filled * 0.35)}px); }} "
            f"{at(1.8)} {{ transform: translateX({num(filled * 0.38)}px); }} {at(2.6)} {{ transform: translateX({num(filled * 0.86)}px); }} "
            f"{at(3.0)}, 100% {{ transform: translateX({num(filled)}px); }} }}"
        )
        later = "" if i == 0 else " later"
        ideas.append(
            f"""<g class="m idea{later}" style="{delay}">
  <path d="{number_d}" fill="{INK_SOFT}"/>
  <path d="{name_d}" fill="{INK}"/>
  <path class="m strike" style="{delay}" d="{strike}" fill="none" stroke="{INK}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
  <g transform="translate({bar_x} {bar_y})" clip-path="url(#bar)">
    <rect width="{bar_w}" height="{bar_h}" fill="url(#stripes)"/>
    <g class="m" style="animation: fill-{i} {num(cycle)}s ease-in-out infinite backwards; {delay}" transform="translate({num(filled)} 0)">
      <rect width="{bar_w}" height="{bar_h}" fill="{WHITE}"/><path d="M0 0V{bar_h}" stroke="{INK}" stroke-width="4"/>
    </g>
  </g>
  <path class="m verdict" style="{delay}" d="{verdict_d}" fill="{INK}"/>
</g>"""
        )

    titles = "; ".join(f"{idea} ({progress}%)" for idea, progress in IDEAS)
    sticker_x, sticker_y = card_x + card_w - 150, 58
    sticker_box_w = sticker_w + 86

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="title desc">
<title id="title">Now building, then abandoning for a new idea</title>
<desc id="desc">{titles}</desc>
<style>
.m {{ transform-box: view-box; transform-origin: 0 0; }}
.idea {{ animation: idea {num(cycle)}s ease-out infinite backwards; }}
.strike {{ stroke-dasharray: 1400; animation: strike {num(cycle)}s ease-in-out infinite backwards; }}
.verdict {{ animation: verdict {num(cycle)}s linear infinite backwards; }}
.pop {{ animation: pop {num(SLOT)}s ease-out infinite; }}
.live {{ animation: live 1.1s steps(1) infinite; }}
@keyframes idea {{ 0% {{ opacity: 0; transform: translateY(14px); }} {at(0.35)}, {at(SLOT - 0.4)} {{ opacity: 1; transform: translateY(0); }} {at(SLOT - 0.05)}, 100% {{ opacity: 0; transform: translateY(0); }} }}
@keyframes strike {{ 0%, {at(3.0)} {{ stroke-dashoffset: 1400; }} {at(3.35)}, 100% {{ stroke-dashoffset: 0; }} }}
@keyframes verdict {{ 0%, {at(3.15)} {{ opacity: 0; }} {at(3.35)}, 100% {{ opacity: 1; }} }}
@keyframes pop {{ 0%, {at_slot(3.25)} {{ opacity: 0; transform: scale(0); }} {at_slot(3.45)} {{ opacity: 1; transform: scale(1.25); }} {at_slot(3.6)}, {at_slot(4.55)} {{ opacity: 1; transform: scale(1); }} {at_slot(4.85)}, 100% {{ opacity: 0; transform: scale(.9); }} }}
@keyframes live {{ 50% {{ opacity: .15; }} }}
{chr(10).join(styles)}
@media (prefers-reduced-motion: reduce) {{ .m {{ animation: none !important; }} .later {{ display: none; }} }}
</style>
<defs>
  <pattern id="stripes" width="18" height="18" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
    <rect width="18" height="18" fill="{BLUE}"/><rect width="7" height="18" fill="{BLUE_DEEP}"/>
  </pattern>
  <clipPath id="bar"><rect width="{bar_w}" height="{bar_h}" rx="{bar_h / 2}"/></clipPath>
</defs>
<rect x="{card_x + 10}" y="{card_y + 10}" width="{card_w}" height="{card_h}" rx="22" fill="{BLUE}"/>
<rect x="{card_x}" y="{card_y}" width="{card_w}" height="{card_h}" rx="22" fill="{WHITE}" stroke="{INK}" stroke-width="5"/>
<rect x="{left}" y="44" width="{num(pill_w)}" height="30" rx="15" fill="{INK}"/>
<circle class="m live" cx="{left + 19}" cy="59" r="6" fill="{BLUE}"/>
<path d="{pill_text_d}" fill="{WHITE}"/>
<rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="{bar_h / 2}" fill="{WHITE}"/>
{chr(10).join(ideas)}
<rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="{bar_h / 2}" fill="none" stroke="{INK}" stroke-width="4"/>
<g transform="translate({sticker_x} {sticker_y}) rotate(-7)"><g class="m pop">
  <rect x="{num(-sticker_box_w / 2 + 6)}" y="-26" width="{num(sticker_box_w)}" height="58" rx="14" fill="{INK}"/>
  <rect x="{num(-sticker_box_w / 2)}" y="-32" width="{num(sticker_box_w)}" height="58" rx="14" fill="{YELLOW}" stroke="{INK}" stroke-width="4"/>
  <g transform="translate({num(-sticker_box_w / 2 + 34)} -4)">{lightbulb()}</g>
  <path d="{sticker_d}" fill="{INK}" transform="translate({num(-sticker_box_w / 2 + 64)} 6)"/>
</g></g>
</svg>
"""
    (ASSETS / "ticker.svg").write_text(svg)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    t = Type(sys.argv[1])
    ASSETS.mkdir(exist_ok=True)
    build_banner(t)
    build_ticker(t)


if __name__ == "__main__":
    main()
