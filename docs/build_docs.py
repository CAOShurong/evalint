#!/usr/bin/env python3
"""Generate README.md, figures included, by running the tool for real.

Every number and every pixel in the README comes from running evalint over
docs/example-results.csv, so the documentation cannot drift away from the code
without CI noticing.

    python docs/build_docs.py            # regenerate
    python docs/build_docs.py --check    # fail if it would change (for CI)

Images need Pillow, which is not a runtime dependency:

    python -m pip install pillow
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "docs" / "readme_template.md"
README = ROOT / "README.md"
EXAMPLE = "docs/example-results.csv"
RAW = "https://raw.githubusercontent.com/CAOShurong/evalint/main/docs"

SGR = re.compile(r"\x1b\[([0-9;]*)m")
BACKGROUND = "#161719"
DEFAULT_INK = "#c8c9c4"

INK = {
    "grid": "#2a2c30",
    "axis": "#565a61",
    "label": "#9aa0a6",
    "title": "#d6d8db",
    "broken": "#d7625f",
    "suspect": "#d1a24a",
    "healthy": "#5fa46f",
    "flat": "#585c63",
}

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\consola.ttf",
    r"C:\Windows\Fonts\cour.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    "/System/Library/Fonts/Menlo.ttc",
]


def run_tool(arguments: list[str], *, colour: bool) -> str:
    command = [
        sys.executable,
        "-X",
        "utf8",
        "-m",
        "evalint",
        *arguments,
        "--color",
        "always" if colour else "never",
    ]
    merged = dict(os.environ)
    merged["PYTHONPATH"] = str(ROOT / "src")
    merged["PYTHONIOENCODING"] = "utf-8"
    merged.pop("NO_COLOR", None)
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=merged,
    )
    # Exit 2 means the demo set has problems, which is the point of the demo
    # rather than a build failure.
    if result.returncode not in (0, 2):
        raise SystemExit(
            f"evalint {' '.join(arguments)} failed ({result.returncode}):\n"
            f"{result.stderr}"
        )
    return result.stdout.rstrip("\n")


def load_font(size: int):
    from PIL import ImageFont

    for path in FONT_CANDIDATES:
        candidate = pathlib.Path(path)
        if candidate.exists():
            try:
                return ImageFont.truetype(str(candidate), size)
            except OSError:  # pragma: no cover - broken font file
                continue
    raise SystemExit("no monospace font found; edit FONT_CANDIDATES")


# -- terminal capture ------------------------------------------------------


def parse_sgr(line: str) -> list[tuple[str, str]]:
    """Split an ANSI line into (text, colour) runs."""
    runs: list[tuple[str, str]] = []
    colour = DEFAULT_INK
    position = 0
    for match in SGR.finditer(line):
        if match.start() > position:
            runs.append((line[position : match.start()], colour))
        codes = [c for c in match.group(1).split(";") if c]
        if not codes or codes == ["0"]:
            colour = DEFAULT_INK
        elif codes[0] == "38" and len(codes) >= 3 and codes[1] == "5":
            colour = _from_256(int(codes[2]))
        position = match.end()
    if position < len(line):
        runs.append((line[position:], colour))
    return runs


def _from_256(index: int) -> str:
    """Convert an xterm-256 index to a hex colour.

    The report emits 256-colour codes because they work on far more terminals
    than truecolor; the figure has to render the palette a user actually sees.
    """
    if index < 16:  # pragma: no cover - the report does not emit these
        return DEFAULT_INK
    if index < 232:
        index -= 16
        levels = (0, 95, 135, 175, 215, 255)
        red = levels[index // 36]
        green = levels[(index % 36) // 6]
        blue = levels[index % 6]
        return f"#{red:02x}{green:02x}{blue:02x}"
    grey = 8 + (index - 232) * 10
    return f"#{grey:02x}{grey:02x}{grey:02x}"


def render_png(text: str, out: pathlib.Path, *, font_size: int = 15) -> None:
    from PIL import Image, ImageDraw

    font = load_font(font_size)
    advance = font.getlength("M")
    line_height = int(font_size * 1.45)
    pad = 18

    lines = text.split("\n")
    columns = max((len(SGR.sub("", line)) for line in lines), default=1)
    width = int(columns * advance) + pad * 2
    height = line_height * len(lines) + pad * 2

    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    for row, line in enumerate(lines):
        x = float(pad)
        y = pad + row * line_height
        for chunk, colour in parse_sgr(line):
            draw.text((x, y), chunk, font=font, fill=colour)
            x += font.getlength(chunk)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, optimize=True)


# -- the item map ----------------------------------------------------------


def render_item_map(out: pathlib.Path) -> None:
    """Difficulty against discrimination, one dot per eval item.

    This is the figure the whole tool is a wrapper around. An item's position
    says what it does: up the middle is a good item, the far left and right
    edges are items everything or nothing passes, and below the zero line are
    the ones the weaker systems pass more often -- which is the shape of a
    wrong expected answer, not of a hard question.
    """
    from PIL import Image, ImageDraw

    sys.path.insert(0, str(ROOT / "src"))
    from evalint.importers import load
    from evalint.report import audit_matrix
    from evalint.stats import BROKEN_DISCRIMINATION

    matrix, _ = load(ROOT / EXAMPLE)
    audit = audit_matrix(matrix)

    width, height = 960, 530
    left, right, top, bottom = 78, width - 250, 54, height - 108
    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    label_font = load_font(13)
    title_font = load_font(15)
    small_font = load_font(12)

    def px(difficulty: float) -> float:
        return left + difficulty * (right - left)

    def py(discrimination: float) -> float:
        return bottom - ((discrimination + 1.0) / 2.0) * (bottom - top)

    # Grid and axes.
    for step in range(0, 11):
        x = px(step / 10)
        draw.line([(x, top), (x, bottom)], fill=INK["grid"])
    for value in (-1.0, -0.5, 0.0, 0.5, 1.0):
        y = py(value)
        draw.line([(left, y), (right, y)], fill=INK["grid"])
        draw.text(
            (left - 40, y - 7), f"{value:+.1f}", font=label_font, fill=INK["label"]
        )

    draw.line([(left, py(0.0)), (right, py(0.0))], fill=INK["axis"], width=2)
    threshold = py(BROKEN_DISCRIMINATION)
    for x in range(int(left), int(right), 8):
        draw.line([(x, threshold), (x + 4, threshold)], fill=INK["broken"])

    # One dot per item.
    counts = {"broken": 0, "suspect": 0, "healthy": 0}
    flat_at: dict[float, int] = {}
    broken_at: list[tuple[float, float]] = []
    for stat in audit.stats.values():
        if stat.discrimination is None:
            # Flat items have no discrimination to plot, so they sit in their
            # own lane. Dropping them from the figure would hide the single
            # largest category of wasted spend.
            flat_at[stat.difficulty] = flat_at.get(stat.difficulty, 0) + 1
            continue
        if stat.looks_broken:
            role, size = "broken", 4.5
            broken_at.append((stat.difficulty, stat.discrimination))
        elif stat.suspect:
            role, size = "suspect", 3.5
        else:
            role, size = "healthy", 3.0
        counts[role] += 1
        draw.ellipse(
            _dot(px(stat.difficulty), py(stat.discrimination), size), fill=INK[role]
        )

    # Items with identical scores land on identical coordinates, so a cluster
    # of ten draws as one dot. Labelling the count keeps the figure from
    # understating what it found.
    if len(broken_at) > 1:
        x = px(sum(d for d, _ in broken_at) / len(broken_at))
        y = py(sum(v for _, v in broken_at) / len(broken_at))
        draw.ellipse(_dot(x, y, 11.0), outline=INK["broken"])
        draw.text(
            (x + 16, y - 7),
            f"{len(broken_at)} items, all here",
            font=small_font,
            fill=INK["broken"],
        )

    # The flat lane.
    lane = bottom + 30
    draw.rectangle([left, bottom + 16, right, bottom + 44], outline=INK["grid"])
    for difficulty, count in sorted(flat_at.items()):
        x = px(difficulty)
        draw.ellipse(_dot(x, lane, 4.0), fill=INK["flat"])
        anchor = x + 10 if difficulty < 0.5 else x - 10
        draw.text(
            (anchor, lane - 7),
            f"{count}",
            font=small_font,
            fill=INK["label"],
            anchor="lt" if difficulty < 0.5 else "rt",
        )
    draw.text(
        (left + 8, bottom + 48),
        "flat: every system scores the same, so there is no discrimination to measure",
        font=small_font,
        fill=INK["flat"],
    )

    # Axis labels.
    draw.text(
        (left, height - 26),
        "difficulty  (0 = nothing passes it, 1 = everything does)",
        font=label_font,
        fill=INK["label"],
    )
    _vertical(draw, image, "discrimination", 22, int(py(0.55)), label_font)
    draw.text(
        (left, 18),
        f"{audit.summary.items} items x {audit.summary.systems} systems"
        f"   reliability {audit.summary.reliability:.2f}",
        font=title_font,
        fill=INK["title"],
    )

    # Legend, with the counts, so the picture and the report agree.
    legend = [
        (f"{counts['broken']} probably broken", INK["broken"]),
        (f"{counts['suspect']} inverted, unproven", INK["suspect"]),
        (f"{counts['healthy']} pulling their weight", INK["healthy"]),
        (f"{sum(flat_at.values())} flat, no signal", INK["flat"]),
    ]
    for index, (text, colour) in enumerate(legend):
        y = top + 6 + index * 24
        draw.ellipse(_dot(right + 26, y + 6, 4.0), fill=colour)
        draw.text((right + 38, y), text, font=small_font, fill=INK["label"])

    draw.text(
        (right + 22, top + 6 + len(legend) * 24 + 16),
        "\n".join(
            [
                "below the dashed line the",
                "worse systems pass an item",
                "more often than the better",
                "ones, which is the shape of",
                "a wrong expected answer",
            ]
        ),
        font=small_font,
        fill=INK["label"],
        spacing=5,
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, optimize=True)


def _dot(x: float, y: float, radius: float):
    return [x - radius, y - radius, x + radius, y + radius]


def _vertical(draw, image, text: str, x: int, y: int, font) -> None:
    """Rotated axis label. Pillow cannot draw rotated text directly, so it is
    drawn onto a scratch image and pasted."""
    from PIL import Image, ImageDraw

    scratch = Image.new("RGB", (160, 22), BACKGROUND)
    ImageDraw.Draw(scratch).text((0, 2), text, font=font, fill=INK["label"])
    image.paste(scratch.rotate(90, expand=True), (x, y))
    del draw


# -- assembly --------------------------------------------------------------

FIGURES = {
    "<!--SHOT_REPORT-->": ("report", [EXAMPLE]),
}

BLOCKS = {
    "<!--TEXT_REPORT-->": [EXAMPLE],
    "<!--TEXT_HELP-->": ["--help"],
}


def build(check: bool) -> int:
    if not TEMPLATE.exists():
        raise SystemExit(f"missing template: {TEMPLATE}")
    text = TEMPLATE.read_text(encoding="utf-8")

    for placeholder, (stem, arguments) in FIGURES.items():
        if placeholder not in text:
            raise SystemExit(f"template has no {placeholder}")
        captured = run_tool(arguments, colour=True)
        if not check:
            render_png(captured, ROOT / "docs" / f"{stem}.png")
        text = text.replace(placeholder, f"![{stem}]({RAW}/{stem}.png)")

    if "<!--SHOT_ITEM_MAP-->" in text:
        if not check:
            render_item_map(ROOT / "docs" / "item-map.png")
        text = text.replace("<!--SHOT_ITEM_MAP-->", f"![item map]({RAW}/item-map.png)")

    for placeholder, arguments in BLOCKS.items():
        if placeholder not in text:
            raise SystemExit(f"template has no {placeholder}")
        captured = run_tool(arguments, colour=False)
        text = text.replace(placeholder, f"```text\n{captured}\n```")

    if check:
        current = README.read_text(encoding="utf-8") if README.exists() else ""
        if current != text:
            print(
                "README.md is out of date. Run:\n\n    python docs/build_docs.py\n",
                file=sys.stderr,
            )
            return 1
        print("README.md is current")
        return 0

    README.write_text(text, encoding="utf-8", newline="\n")
    print(f"README.md: {len(text.splitlines())} lines")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if it would change")
    return build(parser.parse_args().check)


if __name__ == "__main__":
    raise SystemExit(main())
