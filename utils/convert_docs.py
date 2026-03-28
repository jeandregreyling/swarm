"""
convert_docs.py — Seven's Swarm (RL-022 docs)
Convert LibreOffice HTML files in swarm_docs/html/ to .docx in swarm_docs/

Handles LibreOffice HTML structure:
  - Centred title block (24pt blue title, 18pt subtitle, grey italic description)
  - h1 / h2 headings → Heading 1 / Heading 2 styles
  - Tables with blue (#2E75B6) header rows → Word tables with shading + borders
  - ul/li → List Bullet,  ol/li → List Number
  - Warning/error callout paragraphs (yellow/red background)
  - Normal paragraphs
"""

import sys
import re
from pathlib import Path
from lxml import etree as lxmletree

from bs4 import BeautifulSoup, Tag, NavigableString

from docx import Document
from docx.shared import Pt, RGBColor, Cm, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

HTML_DIR = Path(__file__).parent / 'swarm_docs' / 'html'
DOCX_DIR = Path(__file__).parent / 'swarm_docs'

BLUE_HEADER = (0x2E, 0x75, 0xB6)   # #2E75B6
DARK_BLUE   = (0x1F, 0x4E, 0x79)   # #1F4E79
GREY        = (0x66, 0x66, 0x66)    # #666666


# ── XML helpers ───────────────────────────────────────────────────────────────

def _set_cell_shading(cell, fill_hex: str):
    """Apply a solid fill colour to a table cell."""
    tc   = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd  = OxmlElement('w:shd')
    shd.set(qn('w:val'),   'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'),  fill_hex.upper())
    # Remove any existing shd
    for old in tcPr.findall(qn('w:shd')):
        tcPr.remove(old)
    tcPr.append(shd)


def _set_cell_borders(cell, color_hex: str = 'CCCCCC'):
    """Set all four borders on a table cell."""
    tc   = cell._tc
    tcPr = tc.get_or_add_tcPr()
    borders = OxmlElement('w:tcBorders')
    for side in ('top', 'left', 'bottom', 'right'):
        el = OxmlElement(f'w:{side}')
        el.set(qn('w:val'),   'single')
        el.set(qn('w:sz'),    '4')       # 0.5pt
        el.set(qn('w:space'), '0')
        el.set(qn('w:color'), color_hex.upper())
        borders.append(el)
    for old in tcPr.findall(qn('w:tcBorders')):
        tcPr.remove(old)
    tcPr.append(borders)


# ── Text helpers ──────────────────────────────────────────────────────────────

def _get_text(tag) -> str:
    """Flatten all text inside a BS4 tag."""
    if isinstance(tag, NavigableString):
        return str(tag)
    return tag.get_text(separator=' ', strip=False)


def _clean(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def _parse_color(style_str: str):
    """Extract #rrggbb from an inline style string, return (r,g,b) or None."""
    m = re.search(r'color\s*:\s*#([0-9a-fA-F]{6})', style_str or '')
    if m:
        h = m.group(1)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return None


def _parse_fontsize(style_str: str):
    """Extract font-size in pt from inline style, return float or None."""
    m = re.search(r'font-size\s*:\s*([\d.]+)pt', style_str or '')
    if m:
        return float(m.group(1))
    return None


# ── Title block ───────────────────────────────────────────────────────────────

def _add_title_block(doc: Document, paras: list):
    """
    Render the header block (centred title / subtitle / description / metadata).
    paras: list of <p> BS4 tags before the first h1.
    """
    title_done = subtitle_done = desc_done = False

    for p in paras:
        text = _clean(_get_text(p))
        if not text:
            continue

        style_str = p.get('style', '')
        align = p.get('align', '')
        font  = p.find('font')
        fstyle = font.get('style', '') if font else ''
        fcolor = font.get('color', '') if font else ''
        fsize  = font.get('size', '') if font else ''

        # Detect by font size attribute (LibreOffice uses size="6" for 24pt)
        size_num = int(fsize) if fsize.isdigit() else 0
        pt_size  = _parse_fontsize(fstyle)

        is_big_title = (size_num >= 6 or (pt_size and pt_size >= 20))
        is_subtitle  = (size_num == 5 or (pt_size and 15 <= pt_size < 20))
        is_center    = (align == 'center' or 'center' in style_str)

        if is_big_title and not title_done:
            wp = doc.add_paragraph()
            wp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = wp.add_run(text)
            run.bold = True
            run.font.size = Pt(24)
            run.font.color.rgb = RGBColor(*BLUE_HEADER)
            run.font.name = 'Arial'
            title_done = True

        elif is_subtitle and not subtitle_done and title_done:
            wp = doc.add_paragraph()
            wp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = wp.add_run(text)
            run.font.size = Pt(18)
            run.font.color.rgb = RGBColor(*DARK_BLUE)
            run.font.name = 'Arial'
            subtitle_done = True

        elif is_center and title_done and not desc_done:
            # Description / italic tagline
            em = p.find('i') or p.find('em')
            wp = doc.add_paragraph()
            wp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = wp.add_run(text)
            run.italic = bool(em)
            run.font.size = Pt(11)
            run.font.color.rgb = RGBColor(*GREY)
            run.font.name = 'Arial'
            desc_done = True

        elif is_center and title_done:
            # Metadata / quote lines
            wp = doc.add_paragraph()
            wp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            em = p.find('i') or p.find('em')
            run = wp.add_run(text)
            run.italic = bool(em)
            run.font.size = Pt(10)
            run.font.color.rgb = RGBColor(*GREY)
            run.font.name = 'Arial'

    doc.add_paragraph()   # spacer


# ── Table ─────────────────────────────────────────────────────────────────────

def _add_table(doc: Document, table_tag):
    rows_tags = table_tag.find_all('tr')
    if not rows_tags:
        return

    # Column count from first row
    col_count = len(rows_tags[0].find_all(['td', 'th']))
    if col_count == 0:
        return

    tbl = doc.add_table(rows=0, cols=col_count)
    tbl.style = 'Table Grid'

    for tr in rows_tags:
        cells_tags = tr.find_all(['td', 'th'])
        row = tbl.add_row()

        # Detect header row: any cell has bgcolor=#2e75b6 or tag is th
        is_header = any(
            c.name == 'th' or (c.get('bgcolor', '').lower() in ('#2e75b6', '2e75b6'))
            for c in cells_tags
        )

        for j, td in enumerate(cells_tags):
            if j >= col_count:
                break
            cell  = row.cells[j]
            ctext = _clean(_get_text(td))
            cell.paragraphs[0].clear()

            para = cell.paragraphs[0]
            run  = para.add_run(ctext)
            run.font.name = 'Arial'
            run.font.size = Pt(10)

            if is_header:
                run.bold = True
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                _set_cell_shading(cell, '2E75B6')
            else:
                _set_cell_shading(cell, 'FFFFFF')

            _set_cell_borders(cell, 'CCCCCC')

    doc.add_paragraph()   # spacer after table


# ── List ──────────────────────────────────────────────────────────────────────

def _add_list(doc: Document, list_tag, ordered: bool):
    style = 'List Number' if ordered else 'List Bullet'
    for li in list_tag.find_all('li', recursive=False):
        text = _clean(_get_text(li))
        if text:
            p = doc.add_paragraph(style=style)
            run = p.add_run(text)
            run.font.name = 'Arial'
            run.font.size = Pt(11)


# ── Callout box ───────────────────────────────────────────────────────────────

def _add_callout(doc: Document, text: str, bg: str):
    """Render a yellow/red warning box as a shaded paragraph."""
    p  = doc.add_paragraph()
    # Use a run with italic for the text
    run = p.add_run(text)
    run.font.name = 'Arial'
    run.font.size = Pt(10)
    run.italic = True
    if 'f8d7da' in bg or 'f8d7' in bg:
        run.font.color.rgb = RGBColor(0x72, 0x1C, 0x24)
    else:
        run.font.color.rgb = RGBColor(0x85, 0x64, 0x04)


# ── Main body processor ───────────────────────────────────────────────────────

def _process_body(doc: Document, body):
    children = [c for c in body.children
                if isinstance(c, Tag) and c.name not in ('style', 'script')]

    # ── Collect title-block paragraphs (before first h1) ──────────────────────
    title_paras = []
    content_start = 0
    for i, child in enumerate(children):
        if child.name == 'h1':
            content_start = i
            break
        if child.name == 'p':
            title_paras.append(child)
    else:
        content_start = len(children)

    _add_title_block(doc, title_paras)

    # ── Process content elements ───────────────────────────────────────────────
    for child in children[content_start:]:
        tag = child.name

        if tag == 'h1':
            text = _clean(_get_text(child))
            if text:
                p = doc.add_heading(text, level=1)
                p.style.font.color.rgb = RGBColor(*BLUE_HEADER)

        elif tag == 'h2':
            text = _clean(_get_text(child))
            if text:
                p = doc.add_heading(text, level=2)

        elif tag == 'table':
            _add_table(doc, child)

        elif tag in ('ul',):
            _add_list(doc, child, ordered=False)

        elif tag in ('ol',):
            _add_list(doc, child, ordered=True)

        elif tag == 'p':
            style_str = child.get('style', '')
            text = _clean(_get_text(child))
            if not text:
                continue

            # Callout boxes (yellow/red background)
            if 'fff3cd' in style_str or 'f8d7da' in style_str:
                _add_callout(doc, text, style_str)
                continue

            # Skip separator lines (border-bottom only)
            if 'border-bottom' in style_str and not text:
                continue

            p = doc.add_paragraph()
            run = p.add_run(text)
            run.font.name = 'Arial'
            run.font.size = Pt(11)


# ── File converter ────────────────────────────────────────────────────────────

def convert_file(html_path: Path, docx_path: Path):
    with open(html_path, encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'lxml')

    body = soup.find('body')
    if body is None:
        raise ValueError('No <body> found')

    doc = Document()

    # Global Normal style defaults
    normal = doc.styles['Normal']
    normal.font.name = 'Arial'
    normal.font.size = Pt(11)

    # Page margins
    for section in doc.sections:
        section.top_margin    = Cm(2.54)
        section.bottom_margin = Cm(2.54)
        section.left_margin   = Cm(2.54)
        section.right_margin  = Cm(2.54)

    _process_body(doc, body)

    doc.save(docx_path)
    print(f'  ✓  {html_path.name} → {docx_path.name}')


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    html_files = sorted(HTML_DIR.glob('*.html'))
    if not html_files:
        print(f'No HTML files found in {HTML_DIR}')
        sys.exit(1)

    print(f'Converting {len(html_files)} HTML files...\n')
    for html_path in html_files:
        docx_path = DOCX_DIR / (html_path.stem + '.docx')
        try:
            convert_file(html_path, docx_path)
        except Exception as e:
            print(f'  ✗  {html_path.name}: {e}')

    print(f'\nDone. Files in {DOCX_DIR}:')
    for f in sorted(DOCX_DIR.glob('*.docx')):
        print(f'  {f.name}')


if __name__ == '__main__':
    main()
