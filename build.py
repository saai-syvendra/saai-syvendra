#!/usr/bin/env python3
"""Builds the GitHub profile images in assets/: subsets the site's fonts to the
glyphs each SVG uses, measures every string with HarfBuzz and lays the text out
at fixed x positions.

    pip install fonttools "brotli>=1.2.1" uharfbuzz
    python build.py [path to the saai-syvendra.github.io checkout]

GitHub shows each SVG as an <img>, which loads no external fonts and runs no
scripts, so each SVG embeds its fonts as base64 woff2 and animates in CSS only.
"""

import base64
import re
import sys
from html import escape
from io import BytesIO
from pathlib import Path

import uharfbuzz as hb
from fontTools import subset
from fontTools.ttLib import TTFont

SITE = Path(sys.argv[1] if len(sys.argv) > 1 else "~/Projects/saai-syvendra.github.io")
FONT_DIR = SITE.expanduser() / "node_modules/@fontsource"
OUT = Path(__file__).resolve().parent / "assets"

NAVY = "#100c54"
TEAL = "#38a2a3"
PEN = "#0f9b8e"
SCRATCH = "#222222"
CHIP = "#c8f9cc"
GREY = "#555555"
MONO = "ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,'Liberation Mono',monospace"

# One draw of the pen pass, as percentages of the 8 s cycle. All ink holds to
# HOLD, is gone by GONE, and redraws from 0%.
CYCLE = "8s"
HOLD, GONE = 85, 93


class Font:
    # The .woff files, not .woff2, so reading needs no brotli decoder.
    def __init__(self, family, weight, file):
        self.family, self.weight = family, weight
        self.path = FONT_DIR / file
        data = self.path.read_bytes()
        tt = TTFont(BytesIO(data))
        self.upem = tt["head"].unitsPerEm
        self.ascent = tt["hhea"].ascent / self.upem
        self.descent = -tt["hhea"].descent / self.upem
        tt.flavor = None
        raw = BytesIO()
        tt.save(raw)
        self.hb = hb.Font(hb.Face(raw.getvalue()))

    def width(self, text, size):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.hb, buf)
        return sum(p.x_advance for p in buf.glyph_positions) / self.upem * size

    def woff2(self, text):
        opts = subset.Options()
        opts.flavor = "woff2"
        opts.hinting = False
        opts.desubroutinize = True
        font = subset.load_font(str(self.path), opts)
        sub = subset.Subsetter(opts)
        sub.populate(text=text + " ")
        sub.subset(font)
        out = BytesIO()
        subset.save_font(font, out, opts)
        return base64.b64encode(out.getvalue()).decode()


OSWALD = Font("Oswald", 700, "oswald/files/oswald-latin-700-normal.woff")
NUNITO = Font("Nunito", 400, "nunito/files/nunito-latin-400-normal.woff")
NUNITO_BOLD = Font("Nunito", 700, "nunito/files/nunito-latin-700-normal.woff")
CAVEAT = Font("Caveat", 700, "caveat/files/caveat-latin-700-normal.woff")


def center_y(font, size, baseline):
    """The middle of the text's content area, where CSS centres an inline box."""
    return baseline - (font.ascent - font.descent) / 2 * size


def fit(d, left, top, width, height, vw, vh):
    """Maps a path drawn in a (vw x vh) viewBox with preserveAspectRatio="none"
    onto a box, so the site's stroke paths keep their shape at any size."""
    out, nums = [], []

    def flush():
        for i in range(0, len(nums), 2):
            x = left + nums[i] * width / vw
            y = top + nums[i + 1] * height / vh
            out.append(f"{x:.1f} {y:.1f}")
        nums.clear()

    for tok in re.findall(r"[A-Za-z]|-?[\d.]+", d):
        if tok.isalpha():
            flush()
            out.append(tok)
        else:
            nums.append(float(tok))
    flush()
    return " ".join(out)


class Svg:
    def __init__(self, width, height, label):
        self.w, self.h, self.label = width, height, label
        self.body, self.css = [], []
        self.used = {}

    def text(self, font, size, fill, x, y, s, cls="", **attrs):
        self.used[font] = self.used.get(font, "") + s
        extra = "".join(f' {k.replace("_", "-")}="{v}"' for k, v in attrs.items())
        cls = f' class="{cls}"' if cls else ""
        self.body.append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="{font.family}" font-weight="{font.weight}" '
            f'font-size="{size}" fill="{fill}"{cls}{extra}>{escape(s)}</text>'
        )

    def add(self, markup):
        self.body.append(markup)

    def save(self, name):
        faces = "".join(
            f'@font-face{{font-family:"{f.family}";font-weight:{f.weight};'
            f'src:url(data:font/woff2;base64,{f.woff2(s)}) format("woff2")}}'
            for f, s in self.used.items()
        )
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{escape(self.label)}">'
            f"<title>{escape(self.label)}</title><style>{faces}{''.join(self.css)}</style>"
            + "".join(self.body)
            + "</svg>\n"
        )
        (OUT / name).write_text(svg)
        print(f"{name}: {len(svg.encode()) / 1024:.1f} KB")


def draw_keyframes(name, start, end):
    # Hidden until its start, since a round cap leaves a dot at a fully dashed-off start.
    return (
        f"@keyframes {name}{{0%,{start - 0.01}%{{opacity:0;stroke-dashoffset:1}}"
        f"{start}%{{opacity:1;stroke-dashoffset:1;animation-timing-function:ease-out}}"
        f"{end}%,{HOLD}%{{opacity:1;stroke-dashoffset:0}}"
        f"{GONE}%,100%{{opacity:0;stroke-dashoffset:0}}}}"
    )


def write_keyframes(name, start, end):
    # The site's pen-write: a clip that uncovers the handwriting left to right in
    # ten steps. The insets overshoot so Caveat's swashes aren't clipped.
    shown = "clip-path:inset(-30% -10% -30% -10%)"
    return (
        f"@keyframes {name}{{0%,{start}%{{clip-path:inset(-30% 100% -30% -10%);"
        f"animation-timing-function:steps(10,end)}}"
        f"{end}%,{HOLD}%{{{shown};opacity:1}}{GONE}%,100%{{{shown};opacity:0}}}}"
    )


def paper(svg, radius):
    svg.add(
        '<defs><pattern id="grid" width="55" height="55" patternUnits="userSpaceOnUse">'
        '<path d="M0 14h55M0 41.5h55M14 0v55M41.5 0v55" stroke="#E1E1E1" stroke-width="0.6"/>'
        "</pattern></defs>"
        f'<rect x="0.5" y="0.5" width="{svg.w - 1}" height="{svg.h - 1}" rx="{radius}" '
        'fill="#f5f4ec" stroke="#E1E1E1"/>'
        f'<rect x="0.5" y="0.5" width="{svg.w - 1}" height="{svg.h - 1}" rx="{radius}" fill="url(#grid)"/>'
    )


def chip(svg, x, y, icon, label, font=None, size=15):
    """The site's copy chip: green fill, 2px navy border, a lucide icon, a label."""
    h, pad, icon_size, gap = 34, 10, 18, 7
    if font:
        tw = font.width(label, size)
    else:
        tw = 0.6 * size * len(label)  # system monospace, pinned with textLength
    w = pad + icon_size + gap + tw + pad
    svg.add(f'<rect x="{x + 1}" y="{y + 1}" width="{w - 2:.1f}" height="{h - 2}" rx="7" '
            f'fill="{CHIP}" stroke="{NAVY}" stroke-width="2"/>')
    s = icon_size / 24
    svg.add(f'<g transform="translate({x + pad} {y + (h - icon_size) / 2}) scale({s})" fill="none" '
            f'stroke="{NAVY}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{icon}</g>')
    tx = x + pad + icon_size + gap
    if font:
        svg.text(font, size, NAVY, tx, y + h / 2 + (font.ascent - font.descent) / 2 * size, label)
    else:
        svg.add(f'<text x="{tx}" y="{y + h / 2 + 0.35 * size:.1f}" font-family="{MONO}" font-size="{size}" '
                f'fill="{NAVY}" textLength="{tw:.1f}" lengthAdjust="spacingAndGlyphs">{escape(label)}</text>')
    return x + w


MAIL = '<rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>'
TERMINAL = '<polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/>'

# hero-pen.tsx strokes and their viewBoxes.
SCRATCH_1 = "M0 13 Q50 9 100 8"
SCRATCH_2 = "M100 13 Q50 11 0 7"
CIRCLE = "M58 5 C92 3 108 14 104 28 C100 42 70 47 46 46 C20 45 4 38 5 25 C6 12 26 6 50 5 C58 5 66 6 72 8"


def banner():
    W, H, X0 = 720, 352, 48
    body = 20
    k = body / 16  # the hero's pen sizes are tuned for a 16px paragraph
    hand = 1.25 * body  # font-hand text-xl inside a text-base paragraph
    svg = Svg(W, H, "Hi there! I'm Saai Syvendra. I build AI agents for a living, then talk "
                    "about them on stage. Winner of HackerRank Orchestrate, May 2026, #1 of 12,885.")
    paper(svg, 12)

    svg.text(OSWALD, 38, NAVY, X0, 84, "Hi there! I'm")
    svg.text(OSWALD, 58, TEAL, X0, 150, "Saai Syvendra")

    x = chip(svg, X0, 174, MAIL, "saai@syvendra.com", NUNITO_BOLD)
    chip(svg, x + 8, 174, TERMINAL, "ssh ssh.syvendra.com")

    space = NUNITO.width(" ", body)
    line_box = 1.5 * body  # Tailwind's default leading

    # I build AI agents [for fun -> for a living], then talk about them on stage.
    y = 258
    x = X0
    first = "I build AI agents"
    svg.text(NUNITO, body, NAVY, x, y, first)
    x += NUNITO.width(first, body) + space
    fun = NUNITO.width("for fun", body)
    svg.text(NUNITO, body, NAVY, x, y, "for fun")
    sh = 14 * k
    st = center_y(NUNITO, body, y) - sh / 2
    for d, cls in ((SCRATCH_1, "s1"), (SCRATCH_2, "s2")):
        svg.add(f'<path class="ink {cls}" pathLength="1" d="{fit(d, x - 2 * k, st, fun + 4 * k, sh, 100, 20)}" '
                f'fill="none" stroke="{SCRATCH}" stroke-width="{1.8 * k:.2f}" stroke-linecap="round"/>')
    x += fun + space
    living = CAVEAT.width("for a living", hand)
    cy = center_y(CAVEAT, hand, y)
    svg.add(f'<g transform="rotate(-2 {x + living / 2:.1f} {cy:.1f})">')
    svg.text(CAVEAT, hand, PEN, x, y, "for a living", cls="ink w1")
    svg.add("</g>")
    x += living
    svg.text(NUNITO, body, NAVY, x, y, ", then talk about them on stage.")

    # Winner of (HackerRank Orchestrate), May 2026  <- #1 of 12,885!
    y = 314
    x = X0
    svg.text(NUNITO, body, NAVY, x, y, "Winner of")
    x += NUNITO.width("Winner of", body) + space
    won = NUNITO_BOLD.width("HackerRank Orchestrate", body)
    svg.text(NUNITO_BOLD, body, NAVY, x, y, "HackerRank Orchestrate")
    box_top = center_y(NUNITO, body, y) - line_box / 2
    svg.add(f'<path class="ink c1" pathLength="1" '
            f'd="{fit(CIRCLE, x - 12 * k, box_top - 8 * k, won + 24 * k, line_box + 16 * k, 110, 50)}" '
            f'fill="none" stroke="{PEN}" stroke-width="{2 * k:.2f}" stroke-linecap="round"/>')
    x += won
    svg.text(NUNITO, body, NAVY, x, y, ", May 2026")
    x += NUNITO.width(", May 2026", body) + 22
    note = "<- #1 of 12,885!"
    nw = CAVEAT.width(note, hand)
    cy = center_y(CAVEAT, hand, y)
    assert x + nw <= W - X0, f"banner: the note ends at {x + nw:.0f}, past {W - X0}"
    svg.add(f'<g transform="rotate(-2 {x + nw / 2:.1f} {cy:.1f})">')
    svg.text(CAVEAT, hand, PEN, x, y, note, cls="ink w2")
    svg.add("</g>")

    svg.css += [
        f".ink{{animation-duration:{CYCLE};animation-iteration-count:infinite;animation-timing-function:linear}}",
        ".s1{animation-name:s1;stroke-dasharray:1}.s2{animation-name:s2;stroke-dasharray:1}",
        ".c1{animation-name:c1;stroke-dasharray:1}.w1{animation-name:w1}.w2{animation-name:w2}",
        draw_keyframes("s1", 6, 10),
        draw_keyframes("s2", 9, 12),
        write_keyframes("w1", 12, 18),
        draw_keyframes("c1", 20, 28),
        write_keyframes("w2", 29, 36),
        "@media (prefers-reduced-motion:reduce){.ink{animation:none}}",
    ]
    svg.save("banner.svg")


def pin(cx, cy):
    """src/shared/ui/pin.tsx: 20px across including its 3px white ring."""
    return (f'<g filter="url(#pin-shadow)"><circle cx="{cx}" cy="{cy}" r="10" fill="#ffffff"/>'
            f'<circle cx="{cx}" cy="{cy}" r="7" fill="#ef4444"/></g>'
            f'<circle cx="{cx}" cy="{cy}" r="3" fill="#b91c1c"/>')


def card(name, title, lines, tagline):
    """The /talks card on grid paper: 4px dashed navy border, 8px radius, a pin in each top corner."""
    W, H, X = 300, 196, 28
    svg = Svg(W, H, f"{title}: {' '.join(lines)} ({tagline})")
    # Absolute pins sit 5px inside the 4px border: centre = 4 + 5 + 10.
    pin_c = 19
    svg.add('<defs><filter id="pin-shadow" x="-50%" y="-50%" width="200%" height="200%">'
            '<feDropShadow dx="0" dy="2" stdDeviation="1.6" flood-color="#000" flood-opacity="0.22"/>'
            "</filter></defs>")
    # The paper runs under the whole border, so the gaps between dashes show
    # paper, not GitHub's page: on its dark theme navy dashes would vanish.
    paper(svg, 8)
    w, h, r = W - 4, H - 4, 6
    # About 10 on, 6 off, as Chrome dashes the site's 4px border, sized to
    # divide the perimeter so the pattern closes without a stub.
    perimeter = 2 * (w + h) - 8 * r + 2 * 3.14159 * r
    period = perimeter / round(perimeter / 16)
    svg.add(f'<rect x="2" y="2" width="{w}" height="{h}" rx="{r}" fill="none" stroke="{NAVY}" '
            f'stroke-width="4" stroke-dasharray="{period * 0.625:.2f} {period * 0.375:.2f}"/>')
    svg.add(pin(pin_c, pin_c) + pin(W - pin_c, pin_c))

    svg.text(OSWALD, 32, NAVY, X, 78, title)
    size, max_w = 17, W - 2 * X
    for i, line in enumerate(lines):
        y = 110 + i * 23
        if "≠" in line:
            # Nunito has no ≠: set its = and strike it.
            before, after = line.split("≠")
            svg.text(NUNITO, size, GREY, X, y, before + "=" + after)
            ex = X + NUNITO.width(before, size) + NUNITO.width("=", size) / 2
            ey = y - 0.33 * size
            svg.add(f'<line x1="{ex + 0.16 * size:.1f}" y1="{ey - 0.3 * size:.1f}" x2="{ex - 0.16 * size:.1f}" '
                    f'y2="{ey + 0.3 * size:.1f}" stroke="{GREY}" stroke-width="{0.075 * size:.2f}" stroke-linecap="round"/>')
            width = NUNITO.width(before + "=" + after, size)
        else:
            svg.text(NUNITO, size, GREY, X, y, line)
            width = NUNITO.width(line, size)
        assert width <= max_w, f"{name}: '{line}' is {width:.0f}px, over {max_w}px"

    hand = 26
    tw = CAVEAT.width(tagline, hand)
    ty = H - 26
    cy = center_y(CAVEAT, hand, ty)
    svg.add(f'<g transform="rotate(-2 {X + tw / 2:.1f} {cy:.1f})">')
    svg.text(CAVEAT, hand, PEN, X, ty, tagline)
    svg.add("</g>")
    svg.save(f"card-{name}.svg")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    banner()
    card("myspace", "My Space", ["Stories about what I build", "and learn"], "stories, not tutorials")
    card("talks", "Talks", ["LLM ≠ Agent, and the slides"], "invite me to speak ->")
    card("speeches", "Speeches", ["Toastmasters, written out", "in full"], "some of them even won!")
