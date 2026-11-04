"""PDF to page-aware chunks. Every chunk keeps its page number so answers can cite it."""
import re
from collections import Counter

from config import CHUNK_MAX, CHUNK_TARGET, MIN_CHARS_PER_PAGE

CLAUSE_RE = re.compile(r"^(\d+(\.\d+)+[.)]?\s|\d+[.)]\s|\(?[a-z]\)\s|\([ivx]+\)\s|\(\d+\)\s)")


def norm_line(s: str) -> str:
    return re.sub(r"\d+", "#", s.strip().lower())


def is_heading(s: str) -> bool:
    s = s.strip()
    if not (3 <= len(s) <= 90) or s.endswith((".", ",", ";", ":")):
        return False
    if not any(c.isalpha() for c in s):
        return False
    if s.isupper():
        return True
    numbered = re.match(r"^(\d+(\.\d+)*|[A-Z]\.|Section\s+\d+)\s+[A-Z]", s)
    return bool(numbered) and len(s.split()) <= 10


def strip_boilerplate(pages: list[list[str]]) -> list[list[str]]:
    """Drop headers and footers: long-ish lines repeated on 40 percent or more of pages."""
    n = len(pages)
    if n < 5:
        return pages
    counts: Counter = Counter()
    for lines in pages:
        for key in {norm_line(x) for x in lines if 8 <= len(x) < 100}:
            counts[key] += 1
    cutoff = max(3, int(0.4 * n))
    bad = {k for k, c in counts.items() if c >= cutoff}
    return [[x for x in lines if not (8 <= len(x) < 100 and norm_line(x) in bad)] for lines in pages]


def paragraphs(lines: list[str], section: str) -> tuple[list[tuple[str, str]], str]:
    out: list[tuple[str, str]] = []
    cur: list[str] = []

    def flush():
        if cur:
            out.append((section, " ".join(cur)))
            cur.clear()

    for line in lines:
        if not line:
            flush()
            continue
        if is_heading(line):
            flush()
            section = line
            continue
        if CLAUSE_RE.match(line):
            flush()
        cur.append(line)
    flush()
    return out, section


def split_long(text: str) -> list[str]:
    parts, buf = [], ""
    for sent in re.split(r"(?<=[.;:])\s+", text):
        if buf and len(buf) + len(sent) + 1 > CHUNK_MAX:
            parts.append(buf)
            buf = sent
        else:
            buf = (buf + " " + sent).strip()
    if buf:
        parts.append(buf)
    return parts


def pack(paras: list[tuple[str, str]]) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    buf: list[str] = []
    size = 0
    cur_sec = None

    def flush():
        nonlocal buf, size
        if buf:
            chunks.append((cur_sec, " ".join(buf)))
            buf, size = [], 0

    for sec, text in paras:
        pieces = split_long(text) if len(text) > CHUNK_MAX else [text]
        for piece in pieces:
            if sec != cur_sec:
                flush()
                cur_sec = sec
            if size + len(piece) > CHUNK_TARGET:
                flush()
            buf.append(piece)
            size += len(piece)
    flush()
    return chunks


def table_chunks(page) -> list[str]:
    """Tables hold sub-limits and room rent caps, so they get their own chunks."""
    out: list[str] = []
    try:
        tables = page.find_tables().tables
    except Exception:
        return out
    for t in tables:
        rows = t.extract()
        lines = [" | ".join((c or "").replace("\n", " ").strip() for c in r) for r in rows if any(r)]
        if len(" ".join(lines)) < 40:
            continue
        header, body = lines[0], lines[1:] or []
        group, size = [header], len(header)
        for row in body:
            if size + len(row) > CHUNK_MAX and len(group) > 1:
                out.append("\n".join(group))
                group, size = [header], len(header)
            group.append(row)
            size += len(row)
        out.append("\n".join(group))
    return out


def build_chunks(pages_lines: list[list[str]], page_objs=None, skip_pages=frozenset()) -> list[dict]:
    pages_lines = strip_boilerplate(pages_lines)
    chunks: list[dict] = []
    section = ""
    for i, lines in enumerate(pages_lines):
        if (i + 1) in skip_pages:
            continue  # cover page, table of contents, blank pages
        paras, section = paragraphs(lines, section)
        for sec, text in pack(paras):
            if len(text) >= 40:
                chunks.append({"page": i + 1, "section": sec or "", "type": "text", "text": text})
        if page_objs is not None:
            for t in table_chunks(page_objs[i]):
                chunks.append({"page": i + 1, "section": "Table", "type": "table", "text": t})
    return chunks


def clean_raw(raw: str, strip_regex: str | None) -> str:
    if strip_regex:
        raw = re.sub(strip_regex, "", raw)
    return re.sub(r"`(?=\d)", "\u20b9", raw)  # some extractors render the rupee sign as a backtick


def parse_pdf(path, skip_pages=frozenset(), strip_regex: str | None = None) -> dict:
    import fitz  # imported lazily so build_chunks can be tested without it

    doc = fitz.open(path)
    pages_lines, sparse = [], []
    for i, page in enumerate(doc):
        raw = clean_raw(page.get_text("text", sort=True), strip_regex)
        pages_lines.append([ln.strip() for ln in raw.splitlines()])
        if (i + 1) not in skip_pages and len(raw.strip()) < MIN_CHARS_PER_PAGE:
            sparse.append(i + 1)
    chunks = build_chunks(pages_lines, list(doc), skip_pages)
    return {"n_pages": len(doc), "sparse_pages": sparse, "chunks": chunks}
