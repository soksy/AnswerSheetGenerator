#!/usr/bin/env python3
"""
Answer Sheet Generator
Generates a printable PDF answer entry sheet from a YAML descriptor file.

Usage:
    python generate_answer_sheet.py sections.yaml [output.pdf] [--sections START-END]

YAML format:
    sections:
      - name: "Section Name"
        questions: 10
        answers: 4      # number of choices, 1-10; labels are A, B, C, ... up to that count

Sections are paginated automatically: each page holds at most MAX_Q_TOTAL
question rows, and a section is never split across pages.
"""

import argparse
import string
import sys
import yaml
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

# ── Layout constants (all in points, 1mm = 2.835pt) ──────────────────────────
PAGE_W, PAGE_H = A4                  # 595.3 x 841.9 pt
MARGIN_TOP    = 20 * mm
MARGIN_BOTTOM = 15 * mm
MARGIN_LEFT   = 15 * mm
MARGIN_RIGHT  = 15 * mm

NUM_COLS   = 3
MAX_Q_TOTAL = 45                     # max question rows per page
MAX_PER_COL = 15                     # rows per column

# Row / typography
ROW_H        = 13.5 * mm            # height per question row
SECTION_H    = 7.5 * mm             # height for a section sub-heading row
CIRCLE_R     = 2.8 * mm             # bubble radius
FONT_MAIN    = "Helvetica"
FONT_BOLD    = "Helvetica-Bold"

# Candidate name field (top-right of each page)
NAME_BOX_W = 65 * mm
NAME_BOX_H = 8 * mm


def load_yaml(path: str) -> list[dict]:
    with open(path) as f:
        data = yaml.safe_load(f)
    sections = data.get("sections", [])
    for s in sections:
        n = s.get("answers")
        if not isinstance(n, int) or not (1 <= n <= 10):
            raise ValueError(
                f"Section '{s['name']}': 'answers' must be an integer from 1 to 10, got {n}"
            )
    return sections


def parse_section_range(spec: str) -> tuple[int, int]:
    """Parse a 1-indexed, inclusive section range such as '3-7' or '5'."""
    spec = spec.strip()
    if "-" in spec:
        start_s, _, end_s = spec.partition("-")
    else:
        start_s = end_s = spec
    try:
        start, end = int(start_s), int(end_s)
    except ValueError:
        raise ValueError(f"Invalid section range: {spec!r} (expected e.g. '3-7' or '5')")
    if start < 1 or end < start:
        raise ValueError(f"Invalid section range: {spec!r} (expected e.g. '3-7' or '5')")
    return start, end


def select_sections(sections: list[dict], section_range: tuple[int, int] | None) -> list[dict]:
    """Return the subset of sections within a 1-indexed inclusive range."""
    if section_range is None:
        return sections
    start, end = section_range
    if start > len(sections):
        raise ValueError(
            f"Section range start ({start}) exceeds the number of sections ({len(sections)})"
        )
    return sections[start - 1:end]


def paginate_sections(sections: list[dict]) -> list[list[dict]]:
    """
    Group sections into pages so each page holds at most MAX_Q_TOTAL question
    rows. A section is never split across pages; if a single section's
    question count exceeds MAX_Q_TOTAL it is given its own page (and
    truncated when rendered, since it cannot fit either way).
    """
    pages = []
    current = []
    current_q = 0

    for sec in sections:
        n = sec['questions']
        if current and current_q + n > MAX_Q_TOTAL:
            pages.append(current)
            current = []
            current_q = 0
        current.append(sec)
        current_q += n

    if current:
        pages.append(current)

    return pages


def build_row_list(sections: list[dict]) -> list[dict]:
    """
    Convert one page's sections into a flat list of rows.
    Each row is either:
      {'type': 'heading', 'label': str}
      {'type': 'question', 'num': int, 'answers': int}
    A section whose question count alone exceeds MAX_Q_TOTAL is truncated
    to fit, since it cannot be split across pages.
    """
    rows = []
    total_q = 0
    for sec in sections:
        rows.append({'type': 'heading', 'label': sec['name']})
        n = min(sec['questions'], MAX_Q_TOTAL - total_q)
        if n < sec['questions']:
            print(
                f"Warning: section '{sec['name']}' has {sec['questions']} questions, "
                f"which exceeds the {MAX_Q_TOTAL}-per-page limit. Truncated to {n} "
                f"questions to keep the section on one page."
            )
        for i in range(1, n + 1):
            rows.append({'type': 'question', 'num': i, 'answers': sec['answers']})
        total_q += n
    return rows


def distribute_columns(rows: list[dict]) -> list[list[dict]]:
    """
    Split rows into up to 3 columns of ≤ MAX_PER_COL question rows each.
    A heading row doesn't count toward the question-row limit.
    """
    columns = [[], [], []]
    col = 0
    q_in_col = 0

    for row in rows:
        if col >= NUM_COLS:
            break
        # Would adding this question overflow the current column?
        if row['type'] == 'question' and q_in_col >= MAX_PER_COL:
            col += 1
            q_in_col = 0
            if col >= NUM_COLS:
                break
        columns[col].append(row)
        if row['type'] == 'question':
            q_in_col += 1

    return columns


def col_height(col_rows: list[dict]) -> float:
    h = 0.0
    for r in col_rows:
        h += SECTION_H if r['type'] == 'heading' else ROW_H
    return h


def draw_outer_border(c: canvas.Canvas):
    """Draw a thin rectangle around the content area."""
    x = MARGIN_LEFT - 4 * mm
    y = MARGIN_BOTTOM - 4 * mm
    w = PAGE_W - MARGIN_LEFT - MARGIN_RIGHT + 8 * mm
    h = PAGE_H - MARGIN_TOP - MARGIN_BOTTOM + 8 * mm
    c.setStrokeColor(colors.HexColor("#3A86C8"))
    c.setLineWidth(1.5)
    c.rect(x, y, w, h)


def draw_title(c: canvas.Canvas):
    c.setFont(FONT_BOLD, 13)
    c.setFillColor(colors.black)
    c.drawString(MARGIN_LEFT, PAGE_H - MARGIN_TOP - 2 * mm, "Answer Sheet")

    instructions = [
        "Mark your answers here.",
        "Fill in the circle for your chosen answer. Use a pencil.",
        "If you make a mistake, erase completely and try again.",
    ]
    c.setFont(FONT_MAIN, 8)
    c.setFillColor(colors.HexColor("#444444"))
    y = PAGE_H - MARGIN_TOP - 5 * mm
    for line in instructions:
        c.drawString(MARGIN_LEFT, y, line)
        y -= 4.5 * mm


def draw_name_field(c: canvas.Canvas):
    """Draw a labelled box for the candidate to write their name."""
    box_x = PAGE_W - MARGIN_RIGHT - NAME_BOX_W
    box_y = PAGE_H - MARGIN_TOP - NAME_BOX_H - 1 * mm

    c.setFont(FONT_BOLD, 10)
    c.setFillColor(colors.black)
    c.drawRightString(box_x - 2 * mm, box_y + NAME_BOX_H / 2 - 1.2 * mm, "Name:")

    c.setStrokeColor(colors.black)
    c.setLineWidth(0.8)
    c.rect(box_x, box_y, NAME_BOX_W, NAME_BOX_H, fill=0, stroke=1)


def draw_column_dividers(c: canvas.Canvas, col_x: list[float], content_top: float):
    """Draw vertical dividers between columns."""
    c.setStrokeColor(colors.HexColor("#AAAAAA"))
    c.setLineWidth(0.5)
    col_w = (PAGE_W - MARGIN_LEFT - MARGIN_RIGHT) / NUM_COLS
    for i in range(1, NUM_COLS):
        x = MARGIN_LEFT + i * col_w - 0.5 * mm
        c.line(x, MARGIN_BOTTOM, x, content_top)


def draw_columns(c: canvas.Canvas, columns: list[list[dict]], content_top: float):
    col_w = (PAGE_W - MARGIN_LEFT - MARGIN_RIGHT) / NUM_COLS

    for ci, col_rows in enumerate(columns):
        x_base = MARGIN_LEFT + ci * col_w
        y = content_top

        for row in col_rows:
            if row['type'] == 'heading':
                y -= SECTION_H
                draw_section_heading(c, x_base, y, col_w, row['label'])
            else:
                y -= ROW_H
                draw_question_row(c, x_base, y, row['num'], row['answers'], col_w)


def draw_section_heading(c: canvas.Canvas, x: float, y: float,
                         col_w: float, label: str):
    """Render a coloured sub-heading band."""
    pad = 3 * mm
    bar_h = SECTION_H - 1.5 * mm
    c.setFillColor(colors.HexColor("#3A86C8"))
    c.setStrokeColor(colors.white)
    c.setLineWidth(0)
    c.rect(x + pad * 0.3, y + 1 * mm, col_w - pad * 0.6, bar_h, fill=1, stroke=0)

    c.setFont(FONT_BOLD, 8)
    c.setFillColor(colors.white)
    c.drawString(x + pad, y + 2.8 * mm, label)


def draw_question_row(c: canvas.Canvas, x: float, y: float,
                      num: int, num_answers: int, col_w: float):
    """Render one question row: number + bubble row + empty bubble row."""
    labels = string.ascii_uppercase[:num_answers]

    # ── Question number ───────────────────────────────────────────────────────
    c.setFont(FONT_BOLD, 8)
    c.setFillColor(colors.black)
    num_str = str(num)
    num_w = 6 * mm
    c.drawRightString(x + num_w + 1 * mm, y + ROW_H * 0.32 - 1.2 * mm, num_str)

    # ── Column spacing for bubbles ────────────────────────────────────────────
    bubble_start_x = x + num_w + 7 * mm
    row_right_edge = x + col_w - 2 * mm
    max_gap = 6.5 * mm              # centre-to-centre spacing when it fits
    if num_answers > 1:
        bubble_gap = min(max_gap, (row_right_edge - bubble_start_x) / (num_answers - 1))
    else:
        bubble_gap = max_gap
    bubble_r = bubble_gap * (CIRCLE_R / max_gap)   # shrink bubbles to match a tighter gap

    label_y  = y + ROW_H * 0.72    # y for letter labels
    circle_y = y + ROW_H * 0.32    # y for bubbles (centre)

    c.setFont(FONT_MAIN, 7)
    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.6)

    for i, lbl in enumerate(labels):
        cx = bubble_start_x + i * bubble_gap

        # Letter label
        c.setFillColor(colors.black)
        c.drawCentredString(cx, label_y, lbl)

        # Open circle bubble
        c.setFillColor(colors.white)
        c.circle(cx, circle_y, bubble_r, fill=1, stroke=1)

    # Light separator line below the row
    c.setStrokeColor(colors.HexColor("#DDDDDD"))
    c.setLineWidth(0.3)
    c.line(x + 2 * mm, y, row_right_edge, y)


def generate(yaml_path: str, output_path: str, section_range: tuple[int, int] | None = None):
    sections = load_yaml(yaml_path)
    sections = select_sections(sections, section_range)
    if not sections:
        raise ValueError("No sections to render.")

    pages = paginate_sections(sections)

    c = canvas.Canvas(output_path, pagesize=A4)
    c.setTitle("Answer Sheet")
    c.setAuthor("Answer Sheet Generator")

    # Work out where the content area starts (below title block)
    content_top = PAGE_H - MARGIN_TOP - 22 * mm   # leave room for title

    total_q = 0
    total_sections = 0
    for page_num, page_sections in enumerate(pages):
        rows = build_row_list(page_sections)
        columns = distribute_columns(rows)

        draw_outer_border(c)
        draw_title(c)
        draw_name_field(c)
        draw_column_dividers(c, [], content_top)
        draw_columns(c, columns, content_top)

        total_sections += sum(r['type'] == 'heading' for r in rows)
        total_q += sum(r['type'] == 'question' for r in rows)

        if page_num < len(pages) - 1:
            c.showPage()

    c.save()
    print(f"Answer sheet written to: {output_path}")

    # Summary
    print(f"  Pages    : {len(pages)}")
    print(f"  Sections : {total_sections}")
    print(f"  Questions: {total_q}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate a printable bubble-sheet PDF from a YAML section list."
    )
    parser.add_argument("yaml_path", help="Path to the sections YAML file")
    parser.add_argument(
        "output_path", nargs="?", default="answer_sheet.pdf",
        help="Output PDF path (default: answer_sheet.pdf)",
    )
    parser.add_argument(
        "-s", "--sections", dest="section_range", metavar="START-END",
        help="1-indexed inclusive range of sections to render, e.g. '3-7' or '5'",
    )
    args = parser.parse_args()

    section_range = None
    if args.section_range:
        try:
            section_range = parse_section_range(args.section_range)
        except ValueError as e:
            parser.error(str(e))

    try:
        generate(args.yaml_path, args.output_path, section_range)
    except (ValueError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()