# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A small single-script tool that generates a printable A4 PDF "bubble sheet" (multiple-choice answer sheet) from a YAML file describing test sections. Built with `reportlab` for PDF drawing and `PyYAML` for config parsing.

## Commands

Run from the project root using the venv's Python (Windows):

```powershell
.venv\Scripts\python.exe generate_answer_sheet.py sections.yaml [output.pdf] [-s START-END]
```

If `output.pdf` is omitted, output defaults to `answer_sheet.pdf`. The optional `-s`/`--sections` flag takes a 1-indexed inclusive section range (e.g. `-s 3-7` or `-s 5`) to render only a subset of the sections defined in the YAML.

Dependencies (`reportlab`, `PyYAML`) are already installed into `.venv`. There is no `requirements.txt`, `pyproject.toml`, lint config, or test suite in this repo — there is nothing to lint/test beyond running the generator and inspecting the resulting PDF.

## Architecture

Everything lives in `generate_answer_sheet.py`, structured as a pipeline:

1. **`load_yaml`** — parses `sections.yaml` into a list of section dicts (`name`, `questions`, `answers`). Validates that `answers` is `4` (labels A-D) or `7` (labels A-G). The number of sections and questions per section is otherwise unbounded.
2. **`select_sections`** — applies the optional `-s/--sections` 1-indexed inclusive range, slicing down to the subset of sections to render.
3. **`paginate_sections`** — groups sections into pages so each page holds at most `MAX_Q_TOTAL` (45) question rows total, without ever splitting a section across pages. (If a single section's question count alone exceeds `MAX_Q_TOTAL`, it gets its own page and is truncated when rendered, since it can't fit either way.)
4. **`build_row_list`** — for one page's sections, flattens them into an ordered list of row dicts: `{'type': 'heading', 'label': ...}` for each section title, followed by `{'type': 'question', 'num': i, 'answers': n}` for each question.
5. **`distribute_columns`** — splits a page's flat row list into `NUM_COLS` (3) columns, each holding at most `MAX_PER_COL` (15) question rows. Heading rows don't count against the per-column question limit but do consume vertical space.
6. **Drawing functions** (`draw_outer_border`, `draw_title`, `draw_column_dividers`, `draw_columns`, `draw_section_heading`, `draw_question_row`) — render one page using `reportlab.pdfgen.canvas`. All layout is computed from the constants at the top of the file (page margins, `ROW_H`, `SECTION_H`, `CIRCLE_R`, column count, etc.) — there is no separate layout/template system.
7. **`generate`** — orchestrates the pipeline above (load → select → paginate → build/draw per page), writes the PDF, and prints a summary (page/section/question counts).

When changing the visual layout (spacing, bubble size, column count, page capacity), adjust the constants block near the top of the file rather than hardcoding values inside the draw functions — the column/row math (`col_height`, `distribute_columns`, `build_row_list`) depends on those constants staying consistent with what the draw functions actually render.

`sections.yaml` is the live config for the current answer sheet (`answer_sheet.pdf` is its generated output) — when adding new sections or changing question counts, edit this file and regenerate.
