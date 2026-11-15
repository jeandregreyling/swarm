"""lib/knowledge/sources/document_reader.py - one reader for whatever arrives (owner 15 Nov 2026).

read(filename, data) -> (text, None) or (None, why it could not be read, in plain words).

The older parsers here needed Python packages that are not installed (pypdf, python-docx, openpyxl ...), so PDF and Word files
quietly came back empty. This reader needs none of them: it uses the standard library for the zipped formats and the tools
already on this machine for the rest.

  spreadsheets   .xlsx .xlsm (own reader, keeps tab names)   .xls .ods (LibreOffice -> .xlsx)   .csv .tsv
  documents      .docx .odt (own reader)   .doc (catdoc, else LibreOffice)   .rtf (LibreOffice)   .pdf (pdftotext)
  slides         .pptx .odp (own reader)   .ppt (catppt, else LibreOffice)
  text           .txt .md .json .xml .log .yaml and anything that is text;  .html .htm (tags removed)
  mail           .eml (text and each attachment, read with this same reader)
  archives       .zip (each file inside, same reader; bounded)
Not readable: scanned PDFs and pictures (no OCR on this machine), rights-protected mail (.rpmsg), Outlook .msg, encrypted files.
Spreadsheet text has one block per tab: "## Sheet: <name> (<n> rows)" then one line per row, cells separated by tabs."""
import email
import email.policy
import io
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from xml.etree import ElementTree

MAX_BYTES = 40 * 1024 * 1024
MAX_ROWS = 20000
MAX_TEXT = 4_000_000
ZIP_FILES = 40
_S = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main', 'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
TEXT_TYPES = ('.txt', '.md', '.csv', '.tsv', '.json', '.xml', '.log', '.yaml', '.yml', '.ini', '.sql', '.py', '.abap')


def _local(tag):
    return tag.rsplit('}', 1)[-1]


# ------------------------------------------------------------------ spreadsheets
def _column(ref):
    n = 0
    for ch in re.match(r'[A-Z]+', ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def _sheet_links(book, names, path, root):
    """{cell ref: address} for a sheet's hyperlinks. Owner 15 Nov 2026: JD's SAP notes list links each note; the reader kept only
    the visible text, so a cell showing a title or "click here" lost the note number that sits in its address."""
    rels_path = path.rsplit('/', 1)[0] + '/_rels/' + path.rsplit('/', 1)[-1] + '.rels'
    targets = {}
    if rels_path in names:
        for rel in ElementTree.fromstring(book.read(rels_path)):
            if rel.get('Id') and rel.get('Target'):
                targets[rel.get('Id')] = rel.get('Target')
    links = {}
    box = root.find('m:hyperlinks', _S)
    for link in (box if box is not None else []):
        target, ref = targets.get(link.get('{%s}id' % _S['r']), ''), link.get('ref', '').split(':')[0]
        if target and ref:
            links[ref] = target
    return links


def _formula_link(formula):
    """The address in =HYPERLINK("address", "text"), else an empty string."""
    m = re.match(r'\s*HYPERLINK\(\s*"([^"]+)"', str(formula or ''), re.I)
    return m.group(1) if m else ''


def xlsx_text(data, max_rows=MAX_ROWS):
    book = zipfile.ZipFile(io.BytesIO(data))
    names = set(book.namelist())
    shared = []
    if 'xl/sharedStrings.xml' in names:
        for item in ElementTree.fromstring(book.read('xl/sharedStrings.xml')).findall('m:si', _S):
            shared.append(''.join(t.text or '' for t in item.iter('{%s}t' % _S['m'])))
    rels = {}
    if 'xl/_rels/workbook.xml.rels' in names:
        for rel in ElementTree.fromstring(book.read('xl/_rels/workbook.xml.rels')):
            rels[rel.get('Id')] = rel.get('Target')
    out = []
    sheets = ElementTree.fromstring(book.read('xl/workbook.xml')).find('m:sheets', _S)
    for sheet in (sheets if sheets is not None else []):
        target = rels.get(sheet.get('{%s}id' % _S['r']), '')
        path = target.lstrip('/') if target.startswith('/') else 'xl/' + target
        if path not in names:
            continue
        lines = []
        root = ElementTree.fromstring(book.read(path))
        links = _sheet_links(book, names, path, root)          # owner 15 Nov 2026: keep the address behind linked cells
        for row in root.iter('{%s}row' % _S['m']):
            cells = {}
            for c in row.findall('m:c', _S):
                v, kind, ref = c.find('m:v', _S), c.get('t'), c.get('r', 'A1')
                if kind == 'inlineStr':
                    value = ''.join(t.text or '' for t in c.iter('{%s}t' % _S['m']))
                elif v is None or v.text is None:
                    value = None
                elif kind == 's':
                    value = shared[int(v.text)] if int(v.text) < len(shared) else ''
                else:
                    value = v.text
                f = c.find('m:f', _S)
                target = links.get(ref) or (_formula_link(f.text) if f is not None else '')
                if value is None:
                    if not target:
                        continue
                    value = ''
                if target and target not in str(value):
                    value = f'{value} {target}'.strip()
                cells[_column(ref)] = ' '.join(str(value).split())
            if cells:
                lines.append('\t'.join(cells.get(i, '') for i in range(max(cells) + 1)))
            if len(lines) >= max_rows:
                lines.append(f'[stopped after {max_rows} rows]')
                break
        out.append(f"## Sheet: {sheet.get('name')} ({len(lines)} rows)\n" + '\n'.join(lines))
    return '\n\n'.join(out) or '(the workbook has no readable sheets)'


# ------------------------------------------------------------------ zipped documents
def _paragraphs(xml, para='p', text='t', breaks=('tab', 'br', 'cr'), row='tr', cell='tc'):
    """Text of a Word / slide XML part: one line per paragraph; table rows as tab-separated lines."""
    root = ElementTree.fromstring(xml)
    lines = []

    def para_text(node):
        out = []
        for el in node.iter():
            name = _local(el.tag)
            if name == text and el.text:
                out.append(el.text)
            elif name in breaks:
                out.append('\t' if name == 'tab' else '\n')
        return ''.join(out).strip()

    def walk(node, in_table=False):
        for child in node:
            name = _local(child.tag)
            if name == row:
                cells = [' '.join(filter(None, (para_text(p) for p in c.iter() if _local(p.tag) == para))) for c in child if _local(c.tag) == cell]
                if any(cells):
                    lines.append('\t'.join(cells))
            elif name == para and not in_table:
                line = para_text(child)
                if line:
                    lines.append(line)
            else:
                walk(child, in_table)
    walk(root)
    return '\n'.join(lines)


def docx_text(data):
    book = zipfile.ZipFile(io.BytesIO(data))
    parts = ['word/document.xml'] + sorted(n for n in book.namelist() if re.fullmatch(r'word/(footnotes|endnotes|header\d*|footer\d*)\.xml', n))
    return '\n\n'.join(filter(None, (_paragraphs(book.read(p)) for p in parts if p in book.namelist())))


def pptx_text(data):
    book = zipfile.ZipFile(io.BytesIO(data))
    order = lambda n: int(re.search(r'(\d+)\.xml$', n).group(1))
    out = []
    for n in sorted((x for x in book.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml', x)), key=order):
        body = _paragraphs(book.read(n))
        notes = f'ppt/notesSlides/notesSlide{order(n)}.xml'
        extra = _paragraphs(book.read(notes)) if notes in book.namelist() else ''
        out.append(f'## Slide {order(n)}\n{body}' + (f'\nNotes: {extra}' if extra else ''))
    return '\n\n'.join(out)


def odf_text(data):
    """OpenDocument text / slides (content.xml): paragraphs and headings; table rows tab-separated."""
    root = ElementTree.fromstring(zipfile.ZipFile(io.BytesIO(data)).read('content.xml'))
    lines = []

    def flat(node):
        return ''.join(node.itertext()).strip()

    def walk(node):
        for child in node:
            name = _local(child.tag)
            if name == 'table-row':
                cells = [flat(c) for c in child if _local(c.tag) == 'table-cell']
                if any(cells):
                    lines.append('\t'.join(cells))
            elif name in ('p', 'h'):
                if flat(child):
                    lines.append(flat(child))
            else:
                walk(child)
    walk(root)
    return '\n'.join(lines)


# ------------------------------------------------------------------ tools already on this machine
def _tool(cmd, data=None, timeout=120):
    done = subprocess.run(cmd, input=data, capture_output=True, timeout=timeout)
    return done.returncode, done.stdout


def pdf_text(data):
    if not shutil.which('pdftotext'):
        return None, 'pdftotext is not installed on this machine'
    code, out = _tool(['pdftotext', '-layout', '-enc', 'UTF-8', '-', '-'], data)
    text = out.decode('utf-8', errors='replace').replace('\x0c', '\n\n').strip()
    if code != 0:
        return None, 'the PDF is damaged or password-protected'
    if len(re.sub(r'\s', '', text)) < 20:
        return None, 'the PDF has no text layer (a scan or pictures): this machine has no OCR'
    return text, None


def office_convert(filename, data, to):
    """Convert with LibreOffice (headless, its own throw-away profile). Returns the converted bytes or None."""
    office = shutil.which('soffice') or shutil.which('libreoffice')
    if not office:
        return None
    with tempfile.TemporaryDirectory(prefix='hb-doc-') as tmp:
        src = os.path.join(tmp, 'in' + os.path.splitext(filename)[1].lower())
        with open(src, 'wb') as handle:
            handle.write(data)
        try:
            subprocess.run([office, f'-env:UserInstallation=file://{tmp}/profile', '--headless', '--norestore', '--convert-to', to, '--outdir', tmp, src],
                           capture_output=True, timeout=180)
        except subprocess.TimeoutExpired:
            return None
        out = os.path.join(tmp, 'in.' + to.split(':')[0])
        return open(out, 'rb').read() if os.path.isfile(out) else None


def _old_office(filename, data, tool, to, reader):
    if tool and shutil.which(tool[0]):
        with tempfile.NamedTemporaryFile(suffix=os.path.splitext(filename)[1]) as handle:
            handle.write(data)
            handle.flush()
            code, out = _tool(tool + [handle.name])
        text = out.decode('utf-8', errors='replace').strip()
        if code == 0 and len(text) > 20:
            return text, None
    converted = office_convert(filename, data, to)
    if converted:
        return reader(converted), None
    return None, 'could not be converted (LibreOffice gave nothing back; the file may be damaged or password-protected)'


# ------------------------------------------------------------------ mail and archives
def eml_text(data, depth=0):
    msg = email.message_from_bytes(data, policy=email.policy.default)
    out = [f"From: {msg.get('From', '')}", f"To: {msg.get('To', '')}", f"Subject: {msg.get('Subject', '')}", f"Date: {msg.get('Date', '')}", '']
    body = msg.get_body(preferencelist=('plain', 'html'))
    if body is not None:
        content = body.get_content()
        out.append(_strip_html(content) if body.get_content_type() == 'text/html' else content.strip())
    for part in msg.iter_attachments():
        name = part.get_filename() or part.get_content_type()
        text, why = read(name, part.get_payload(decode=True) or b'', depth + 1)
        out.append(f'\n--- Attachment: {name} ---\n' + (text if text is not None else f'(not read: {why})'))
    return '\n'.join(out)


def zip_text(data, depth=0):
    book = zipfile.ZipFile(io.BytesIO(data))
    out, total = [], 0
    for info in [i for i in book.infolist() if not i.is_dir()][:ZIP_FILES]:
        if info.file_size > MAX_BYTES or total + info.file_size > 3 * MAX_BYTES:
            out.append(f'--- {info.filename} ---\n(not read: too large)')
            continue
        total += info.file_size
        text, why = read(info.filename, book.read(info), depth + 1)
        out.append(f'--- {info.filename} ---\n' + (text if text is not None else f'(not read: {why})'))
    return '\n\n'.join(out)


def _strip_html(html):
    html = re.sub(r'<(script|style)[^>]*>[\s\S]*?</\1>', ' ', html, flags=re.IGNORECASE)
    text = re.sub(r'<(br|/p|/div|/tr|/li|/h\d)[^>]*>', '\n', html, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    import html as _html
    text = '\n'.join(line.strip() for line in re.sub(r'[ \t]+', ' ', _html.unescape(text)).splitlines())
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def _looks_like_text(data):
    sample = data[:4000]
    return b'\x00' not in sample and sum(b < 9 or 13 < b < 32 for b in sample) < len(sample) * 0.02


# ------------------------------------------------------------------ the one entry point
def read(filename, data, depth=0):
    """(text, None) or (None, why). Never raises for a bad file."""
    name = str(filename or '').lower().strip()
    ext = os.path.splitext(name)[1]
    if len(data) > MAX_BYTES:
        return None, f'too large ({len(data) // 1024 ** 2} MB; limit {MAX_BYTES // 1024 ** 2} MB)'
    if not data:
        return None, 'the file is empty'
    if depth > 2:
        return None, 'nested too deep'
    try:
        if ext == '.rpmsg':
            return None, "protected by the sender's organisation (Microsoft rights protection): only the sender's own sign-in can open it"
        if ext == '.msg':
            return None, 'an Outlook .msg file: save the attachment itself, or forward the mail, and send that'
        if data[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' and ext in ('.xlsx', '.docx', '.pptx', '.xlsm'):
            return None, 'the file is password-protected (encrypted): remove the password and send it again'
        if ext in ('.xlsx', '.xlsm'):
            text = xlsx_text(data)
        elif ext in ('.xls', '.ods', '.xlsb'):
            converted = office_convert(name, data, 'xlsx')
            if not converted:
                return None, 'could not be converted to .xlsx (LibreOffice gave nothing back; the file may be damaged or password-protected)'
            text = xlsx_text(converted)
        elif ext == '.docx':
            text = docx_text(data)
        elif ext == '.pptx':
            text = pptx_text(data)
        elif ext in ('.odt', '.odp'):
            text = odf_text(data)
        elif ext == '.pdf' or data[:5] == b'%PDF-':
            text, why = pdf_text(data)
            if text is None:
                return None, why
        elif ext == '.doc':
            text, why = _old_office(name, data, ['catdoc', '-w'], 'docx', docx_text)
            if text is None:
                return None, why
        elif ext == '.ppt':
            text, why = _old_office(name, data, ['catppt'], 'pptx', pptx_text)
            if text is None:
                return None, why
        elif ext == '.rtf':
            text, why = _old_office(name, data, None, 'docx', docx_text)
            if text is None:
                return None, why
        elif ext in ('.html', '.htm'):
            text = _strip_html(data.decode('utf-8-sig', errors='replace'))
        elif ext == '.eml':
            text = eml_text(data, depth)
        elif ext == '.zip':
            text = zip_text(data, depth)
        elif ext in TEXT_TYPES or _looks_like_text(data):
            text = data.decode('utf-8-sig', errors='replace')
        elif ext in ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tif', '.tiff', '.webp'):
            return None, 'a picture: this machine has no OCR to read text from images'
        else:
            return None, f'a file type HB does not read yet ({ext or "no extension"})'
    except zipfile.BadZipFile:
        return None, 'the file is damaged, or it is not really the type its name says'
    except subprocess.TimeoutExpired:
        return None, 'reading it took too long'
    except Exception as exc:
        return None, f'could not be read ({type(exc).__name__})'
    text = (text or '').strip()
    if not text:
        return None, 'the file has no readable text in it'
    return text[:MAX_TEXT], None
