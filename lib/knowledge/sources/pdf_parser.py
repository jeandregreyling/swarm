"""lib/knowledge/sources/pdf_parser.py — Extract text from PDF files.

Tries pypdf first, then pdfminer.six.  If neither is installed the function
returns a message explaining which package to `pip install`.
"""
import logging

logger = logging.getLogger('seven.knowledge.pdf')


def extract_from_bytes(pdf_bytes):
    """
    Extract plain text from raw PDF bytes.
    Returns (title: str, text: str).
    """
    # ── pypdf (pure-Python, modern) ──────────────────────────────────────────
    try:
        import pypdf
        import io

        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        title = ''
        if reader.metadata:
            title = (getattr(reader.metadata, 'title', None) or
                     reader.metadata.get('/Title', '')) or ''
            title = str(title).strip()

        parts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                parts.append(t)

        text = '\n\n'.join(parts)
        return (title or 'PDF Document'), text[:500_000]

    except ImportError:
        pass
    except Exception as exc:
        logger.warning(f'[PDF] pypdf error: {exc}')

    # ── pdfminer.six (fallback) ──────────────────────────────────────────────
    try:
        import io
        from pdfminer.high_level import extract_text_to_fp
        from pdfminer.layout import LAParams

        out = io.StringIO()
        extract_text_to_fp(io.BytesIO(pdf_bytes), out, laparams=LAParams())
        text = out.getvalue()
        return 'PDF Document', text[:500_000]

    except ImportError:
        pass
    except Exception as exc:
        logger.warning(f'[PDF] pdfminer error: {exc}')

    return (
        'PDF Document',
        '[PDF text extraction requires pypdf or pdfminer.six]\n'
        'Run: pip install pypdf\n'
        'Then re-ingest this document.'
    )


def extract_from_path(path):
    """Extract text from a PDF at `path` on disk. Returns (title, text)."""
    with open(path, 'rb') as fh:
        return extract_from_bytes(fh.read())
