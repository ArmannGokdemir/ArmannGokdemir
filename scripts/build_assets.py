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
PEEKS = [(7.2, 10.6), (13.0, 15.8), (21.5, 22.6), (40.0, 43.4), (47.0, 48.0), (49.2, 50.6), (60.2, 63.0), (83.5, 84.6), (91.0, 93.6)]
BLINKS = [9.2, 14.6, 41.8, 61.6, 92.4]


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


# The ring text is a train of letters moving along one closed route: a few
# turns around the badge, then a run around the name card and back. The
# end of the text leads, so "NEW IDEA" is what runs off first.
RING_TEXT = "BUILD IT • SHIP— OOH, NEW IDEA • "
RING_SIZE = 30
RING_R = 112
TURNS = 2  # full turns around the badge between strolls
STROLLS = [7.0, 60.0]  # seconds into PEEK_CYCLE; each lines up with a peek
STROLL_TIME = 13.0
# Typing stalls on "SHIP", then the rest comes out in a rush.
TYPE_STEP, TYPE_PAUSE, TYPE_RUSH = 0.09, 0.8, 0.05
TYPE_STALL_AT = len(RING_TEXT.split("—")[0].replace(" ", ""))


def bezier_length(points, samples=400):
    def at(u):
        n = len(points) - 1
        x = y = 0.0
        for k, (px, py) in enumerate(points):
            c = math.comb(n, k) * (1 - u) ** (n - k) * u**k
            x, y = x + c * px, y + c * py
        return x, y

    total, prev = 0.0, at(0)
    for s in range(1, samples + 1):
        cur = at(s / samples)
        total += math.dist(prev, cur)
        prev = cur
    return total


class Route:
    """Path data plus its running length, so letters can be timed by distance."""

    def __init__(self, x, y):
        self.d, self.pos, self.length = [f"M{num(x)} {num(y)}"], (x, y), 0.0

    def half_turn(self, r, to):
        self.d.append(f"A{r} {r} 0 0 1 {num(to[0])} {num(to[1])}")
        self.length += math.pi * r
        self.pos = to

    def line(self, to):
        self.d.append(f"L{num(to[0])} {num(to[1])}")
        self.length += math.dist(self.pos, to)
        self.pos = to

    def curve(self, *points):
        letter = "Q" if len(points) == 2 else "C"
        self.d.append(letter + " ".join(f"{num(x)} {num(y)}" for x, y in points))
        self.length += bezier_length([self.pos, *points])
        self.pos = points[-1]

    def stroll(self, top):
        # Leave the badge at the bottom heading left, run clockwise round the
        # name card through the margins, and come back in at the top.
        self.curve((1000, self.pos[1]), (962, 414), (900, 414))
        self.line((70, 414))
        self.curve((28, 414), (28, 372))
        self.line((28, 72))
        self.curve((28, 30), (70, 30))
        self.line((880, 30))
        self.curve((960, 30), (990, top[1]), top)


def ring_route(cx, cy, r):
    bottom, top = (cx, cy + r), (cx, cy - r)
    route, marks = Route(*bottom), []
    for _ in range(2):  # the loop is drawn twice so offsets never wrap
        for _ in STROLLS:
            for _ in range(TURNS):
                route.half_turn(r, top)
                route.half_turn(r, bottom)
            start = route.length
            route.stroll(top)
            marks.append((start, route.length))
            route.half_turn(r, bottom)
    return "".join(route.d), route.length / 2, marks[: len(STROLLS)]


def ring_train(t, cx, cy):
    """Letters of RING_TEXT, each riding the route at its own offset."""
    circumference = 2 * math.pi * RING_R
    route_d, loop, marks = ring_route(cx, cy, RING_R)

    _, glyphs, width = t.shape(RING_TEXT, RING_SIZE, wght=800, opsz=24)
    tracking = (circumference - width) / len(glyphs)
    font, glyphs, _ = t.shape(RING_TEXT, RING_SIZE, wght=800, opsz=24, tracking=tracking)
    scale = RING_SIZE / t.upem

    # Distance of the text's first letter along the route over one cycle.
    # Slow while circling, eased and fast while strolling.
    start = 0.75 * circumference
    times, distances = [0.0], [start]
    for at, (leave, back) in zip(STROLLS, marks):
        times += [at, at + STROLL_TIME]
        distances += [leave - circumference, back]
    times.append(float(PEEK_CYCLE))
    distances.append(start + loop)
    key_times = ";".join(f"{v / PEEK_CYCLE:.4f}" for v in times)
    splines = ";".join(".42 0 .58 1" if k % 2 else "0 0 1 1" for k in range(len(times) - 1))

    letters = []
    typed = 0
    for gid, gx, advance in glyphs:
        pen = SVGPathPen(None, ntos=num)
        font.draw_glyph_with_pen(gid, TransformPen(pen, (scale, 0, 0, -scale, -advance / 2, 0)))
        shape = pen.getCommands()
        if not shape:
            continue
        offset = gx + advance / 2
        points = ";".join(f"{(d + offset) / (2 * loop):.5f}" for d in distances)
        if typed < TYPE_STALL_AT:
            delay = 0.6 + typed * TYPE_STEP
        else:
            delay = 0.6 + TYPE_STALL_AT * TYPE_STEP + TYPE_PAUSE + (typed - TYPE_STALL_AT) * TYPE_RUSH
        letters.append(
            f'<g><animateMotion dur="{PEEK_CYCLE}s" repeatCount="indefinite" rotate="auto" calcMode="spline" '
            f'keyTimes="{key_times}" keyPoints="{points}" keySplines="{splines}"><mpath xlink:href="#ring-route"/></animateMotion>'
            f'<g class="m type" style="animation-delay:{delay:.2f}s"><path d="{shape}" fill="{INK}"/></g></g>'
        )
        typed += 1

    static_d = t.circle_path(RING_TEXT, RING_SIZE, RING_R, start_deg=90 + math.degrees(start / RING_R), wght=800, opsz=24)
    return route_d, "\n".join(letters), static_d, tracking


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
    route_d, ring_letters, ring_static_d, _ = ring_train(t, badge_cx, badge_cy)

    dots = halftone(W, H, 14, falloff(1180, 400, 560, 5.2))
    dots_tl = halftone(W, H, 14, falloff(0, 0, 230, 4.2))

    fez_dx, fez_dy = apex_x + 4, apex_y + 6

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="title desc">
<title id="title">Selam, I'm Arman.</title>
<desc id="desc">I build stuff. Apps, AI agents, dashboards, automations: whatever the problem needs.</desc>
<style>
.m {{ transform-box: view-box; transform-origin: 0 0; }}
.swing {{ animation: swing 2.6s ease-in-out infinite alternate; }}
.type {{ animation: type .3s cubic-bezier(.3,1.6,.6,1) backwards; }}
@keyframes type {{ from {{ opacity: 0; transform: scale(.2); }} to {{ opacity: 1; transform: scale(1); }} }}
.ring-static {{ display: none; }}
@media (prefers-reduced-motion: reduce) {{ .ring-static {{ display: inline; }} .ring-live {{ display: none; }} }}
.glint {{ animation: glint 4.5s ease-in-out infinite; }}
.twinkle {{ animation: twinkle 2.4s ease-in-out infinite; }}
.draw {{ stroke-dasharray: 900; animation: draw 1.6s cubic-bezier(.65,0,.35,1) .3s backwards; }}
@keyframes swing {{ from {{ transform: rotate(-18deg); }} to {{ transform: rotate(6deg); }} }}
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
  <path id="ring-route" d="{route_d}"/>
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
    <path class="ring-static" d="{ring_static_d}" fill="{INK}"/>
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
  <g transform="translate(870 372)"><path class="m twinkle" style="animation-delay:-1.6s" d="{sparkle(12)}" fill="{WHITE}" stroke="{INK}" stroke-width="3" stroke-linejoin="round"/></g>
  <g transform="translate(1226 404)"><path class="m twinkle" style="animation-delay:-1.1s" d="{sparkle(9)}" fill="{WHITE}" stroke="{INK}" stroke-width="2.5" stroke-linejoin="round"/></g>

  <!-- ring text: typed in, circles the badge, now and then strolls round the card -->
  <g class="ring-live">
{ring_letters}
  </g>
</g>
</svg>
"""
    (ASSETS / "banner.svg").write_text(svg)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    t = Type(sys.argv[1])
    ASSETS.mkdir(exist_ok=True)
    build_banner(t)


if __name__ == "__main__":
    main()
