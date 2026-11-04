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


SUBCLAUSE_RE = re.compile(r"^(\d+(?:\.\d+)+)\s+\S")      # 4.12 Circumcision ...
TABLE_MARK = "\x00TABLE"
APPENDIX_RE = re.compile(r"^(Appendix|Annexure|Schedule)\s+[IVX\d]+\b", re.I)


def clause_label(line: str) -> str:
    """Short section label from the first words of a numbered clause line."""
    words = line.split()
    label = " ".join(words[:8])
    return label[:70].rstrip(" ,;:(")


def paragraphs(lines: list[str], section: str, state: dict | None = None) -> tuple[list[tuple[str, str]], str]:
    """Split page lines into (section, text) paragraphs.

    state carries across pages: whether the current section has body text yet, and
    whether we are inside an appendix (where upper case table labels are not headings).
    """
    state = state if state is not None else {"has_body": True, "appendix": False}
    out: list[tuple[str, str]] = []
    cur: list[str] = []

    def flush():
        if cur:
            out.append((section, " ".join(cur)))
            state["has_body"] = True
            cur.clear()

    def new_section(label: str):
        nonlocal section
        if re.match(r"^\d+\s+[A-Z]", label) or APPENDIX_RE.match(label):
            state["part"] = label  # top level part, e.g. "4 Exclusions", "5 Conditions", "Appendix II"
        state.setdefault("part_of", {})[label] = state.get("part", "")
        # A numbered heading with no body is itself the clause (e.g. "4.18 OPD treatment"),
        # so keep it as text instead of losing it.
        if not state["has_body"] and SUBCLAUSE_RE.match(section or ""):
            out.append((section, section))
        section = label
        state["has_body"] = False

    for line in lines:
        if not line:
            flush()
            continue
        if line.startswith(TABLE_MARK):
            flush()
            state.setdefault("table_sections", {})[line] = section
            continue
        if APPENDIX_RE.match(line):
            flush()
            new_section(line[:70])
            state["appendix"] = True
            continue
        if is_heading(line) and not (state["appendix"] and not SUBCLAUSE_RE.match(line)):
            flush()
            new_section(line)
            state["appendix"] = state["appendix"] and not SUBCLAUSE_RE.match(line)
            continue
        if SUBCLAUSE_RE.match(line) and not state["appendix"]:
            # A numbered clause that opens with body text on the same line starts its own section.
            flush()
            new_section(clause_label(line))
        elif CLAUSE_RE.match(line):
            flush()
        cur.append(line)
    flush()
    return out, section


def split_long(text: str) -> list[str]:
    """Split by sentence; fall back to word windows for lists with no punctuation."""
    parts, buf = [], ""
    for sent in re.split(r"(?<=[.;:])\s+", text):
        if len(sent) > CHUNK_MAX:
            words, sent_parts, cur = sent.split(), [], ""
            for w in words:
                if cur and len(cur) + len(w) + 1 > CHUNK_TARGET:
                    sent_parts.append(cur)
                    cur = w
                else:
                    cur = (cur + " " + w).strip()
            if cur:
                sent_parts.append(cur)
        else:
            sent_parts = [sent]
        for s in sent_parts:
            if buf and len(buf) + len(s) + 1 > CHUNK_MAX:
                parts.append(buf)
                buf = s
            else:
                buf = (buf + " " + s).strip()
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
        text = re.sub(r"\s+", " ", text).strip()
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


def find_tables(page) -> list:
    try:
        return [t for t in page.find_tables().tables if t.row_count >= 2]
    except Exception:
        return []


def _cell_text(page, cell, strip_regex) -> str:
    import fitz
    if not cell:
        return ""
    txt = clean_raw(page.get_text("text", clip=fitz.Rect(cell)), strip_regex)
    return re.sub(r"\s+", " ", txt).strip()


def table_chunks(page, tables, strip_regex=None) -> list[tuple[int, str | None, str]]:
    """Tables hold sub-limits and room rent caps, so they get their own chunks.

    Cell text is read with a clip rectangle per cell, which keeps word spacing
    (Table.extract() drops spaces on justified text in some PDFs).
    Returns (section_label or None, text). A row that opens with a numbered clause
    starts its own chunk and names the section.
    """
    out: list[tuple[int, str | None, str]] = []
    for ti, t in enumerate(tables):
        rows = []
        for r in t.rows:
            cells = [_cell_text(page, c, strip_regex) for c in r.cells]
            if any(cells):
                rows.append(" | ".join(c for c in cells if c))
        if len(" ".join(rows)) < 40:
            continue
        header = rows[0] if len(rows[0]) < 150 and not SUBCLAUSE_RE.match(rows[0]) else None
        body = rows[1:] if header else rows
        group, size, label = ([header] if header else []), len(header or ""), None

        def flush():
            nonlocal group, size, label
            if group and (len(group) > 1 or not header):
                out.append((ti, label, "\n".join(group)))
            group, size, label = ([header] if header else []), len(header or ""), None

        for row in body:
            starts_clause = bool(SUBCLAUSE_RE.match(row))
            if (starts_clause and size > len(header or "")) or (size + len(row) > CHUNK_MAX and len(group) > 1):
                flush()
            if starts_clause and label is None:
                label = clause_label(row.split(" | ")[0])
            group.append(row)
            size += len(row)
        flush()
    return out


def _inside(block, rects) -> bool:
    cx, cy = (block[0] + block[2]) / 2, (block[1] + block[3]) / 2
    return any(r[0] - 2 <= cx <= r[2] + 2 and r[1] - 2 <= cy <= r[3] + 2 for r in rects)


def build_chunks(pages_lines: list[list[str]], page_tables=None, skip_pages=frozenset()) -> list[dict]:
    """page_tables: optional list (one per page) of [(section_or_None, text)] table chunks."""
    pages_lines = strip_boilerplate(pages_lines)
    chunks: list[dict] = []
    section = ""
    state = {"has_body": True, "appendix": False}
    for i, lines in enumerate(pages_lines):
        if (i + 1) in skip_pages:
            continue  # cover page, table of contents, blank pages
        state["table_sections"] = {}
        paras, section = paragraphs(lines, section, state)
        for sec, text in pack(paras):
            if len(text) >= 30:
                chunks.append({"page": i + 1, "section": sec or "", "type": "text", "text": text,
                               "part": state.get("part_of", {}).get(sec, state.get("part", ""))})
        if page_tables is not None:
            for k, (label, t) in enumerate(page_tables[i]):
                tsec = state["table_sections"].get(f"{TABLE_MARK}{k}", section)
                sec = label or tsec or "Table"
                chunks.append({"page": i + 1, "section": sec, "type": "table", "text": t,
                               "part": state.get("part_of", {}).get(tsec, state.get("part", ""))})
    return chunks


def clean_raw(raw: str, strip_regex: str | None) -> str:
    if strip_regex:
        raw = re.sub(strip_regex, "", raw)
    return re.sub(r"`(?=\d)", "₹", raw)  # some extractors render the rupee sign as a backtick


def parse_pdf(path, skip_pages=frozenset(), strip_regex: str | None = None) -> dict:
    import fitz  # imported lazily so build_chunks can be tested without it

    doc = fitz.open(path)
    pages_lines, page_tables, sparse = [], [], []
    for i, page in enumerate(doc):
        tables = find_tables(page) if (i + 1) not in skip_pages else []
        rects = [tuple(t.bbox) for t in tables]
        # Text outside tables only, so two-column tables do not interleave into prose.
        tchunks = table_chunks(page, tables, strip_regex)
        items = []
        for blk in page.get_text("dict", sort=True)["blocks"]:
            if blk.get("type") != 0:
                continue
            prev_y1 = None
            for ln in blk["lines"]:
                bb = ln["bbox"]
                if _inside(bb, rects):
                    continue
                txt = "".join(sp["text"] for sp in ln["spans"])
                # a visible vertical gap means a paragraph break
                gap = prev_y1 is not None and bb[1] - prev_y1 > 6
                items.append((bb[1], bb[0], ("\n" if gap else "") + txt + "\n"))
                prev_y1 = bb[3]
        # join lines first, then strip, so multi-line strip patterns still match
        items = [(y, x, t) for y, x, t in items]
        # one marker per table chunk, placed where its table starts on the page
        for k, (tidx, _, _) in enumerate(tchunks):
            r = rects[tidx]
            items.append((r[1], r[0], f"{TABLE_MARK}{k}\n"))
        items.sort(key=lambda x: (round(x[0], 1), x[1]))
        text, k_items = "", []
        for _, _, txt in items:
            text += txt if not txt.startswith(TABLE_MARK) else "\n" + txt + "\n"
        text = clean_raw(text, strip_regex)
        pages_lines.append([ln.strip() for ln in text.splitlines()])
        page_tables.append([(label, text) for _, label, text in tchunks])
        full = page.get_text("text")
        if (i + 1) not in skip_pages and len(full.strip()) < MIN_CHARS_PER_PAGE:
            sparse.append(i + 1)
    chunks = build_chunks(pages_lines, page_tables, skip_pages)
    return {"n_pages": len(doc), "sparse_pages": sparse, "chunks": chunks}
