"""PDF to page-aware chunks. Every chunk keeps its page number so answers can cite it."""
import re
import unicodedata
from collections import Counter

from config import CHUNK_MAX, CHUNK_TARGET, MIN_CHARS_PER_PAGE

CLAUSE_RE = re.compile(r"^(\d+(\.\d+)+[.)]?\s|\d+[.)]\s|\(?[a-z]\)\s|\([ivx]+\)\s|\(\d+\)\s)")


def norm_line(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", s.strip().lower()))


def is_heading(s: str) -> bool:
    s = s.strip()
    if not (3 <= len(s) <= 90) or s.endswith((".", ",", ";", ":")):
        return False
    if not any(c.isalpha() for c in s):
        return False
    if s.isupper():
        return sum(c.isalpha() for c in s) >= 4 and not NOT_A_PART.match(s)  # "1L 2L" is a table header, not a heading
    if NOT_A_PART.match(s):
        return False
    numbered = re.match(r"^(\d+(\.\d+)*|[A-Z]\.|Section\s+\d+)\s+[A-Z]", s)
    return bool(numbered) and len(s.split()) <= 10


# "5 Lakhs to 10 Lakhs", "275 Lakhs", "90 Days Waiting Period" start with a number and a capital
# but are amounts or durations, not numbered headings or top level parts.
# Durations take a whole number only, so a clause such as "3.8 Day Care Centre" stays a clause.
NOT_A_PART = re.compile(r"^\d+(?:\.\d+)?\s*(?:Lakhs?|Lacs?|Crores?)\b|^\d+\s*(?:Days?|Months?|Years?|Yrs?|Times)\b"
                        r"|^\d+[LK]\b|^[₹\d][\d,.]*\s*/-", re.I)


def strip_boilerplate(pages: list[list[str]]) -> list[list[str]]:
    """Drop headers and footers: lines repeated on 40 percent or more of pages.

    The upper length bound is generous because some footers are one long line
    (SBI prints its registered office, CIN, phone and licence text as a single line).
    """
    n = len(pages)
    if n < 5:
        return pages
    counts: Counter = Counter()
    for lines in pages:
        for key in {norm_line(x) for x in lines if 8 <= len(x) < 400}:
            counts[key] += 1
    cutoff = max(3, int(0.4 * n))
    bad = {k for k, c in counts.items() if c >= cutoff}
    return [[x for x in lines if not (8 <= len(x) < 400 and norm_line(x) in bad)] for lines in pages]


EXCL_CODE = re.compile(r"Code\s*[-–:]?\s*Exc[lI]\s*\d+", re.I)
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
        if (re.match(r"^\d+\s+[A-Z]", label) and not NOT_A_PART.match(label)) or APPENDIX_RE.match(label):
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
        if SUBCLAUSE_RE.match(line) and not state["appendix"] and not NOT_A_PART.match(line):
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
    return re.sub(r"\s+", " ", join_wrapped_numbers(txt)).strip()


# A fragment that ends in a comma followed by fewer than three digits cannot be a whole
# number in Indian or Western grouping (the last group always has three digits), so it was
# wrapped by a narrow cell: "1,4" over "71" is 1,471. A fragment that starts with a comma
# continues the one above ("102" over ",34" over "4" is 102,344). Stacked values such as "5"
# over "7.5" match neither and are left apart.
_WRAPPED = re.compile(r"(\d,\d{0,2})[ \t]*\n[ \t]*(?=\d)|(\d)[ \t]*\n[ \t]*(?=,\d)")


def join_wrapped_numbers(txt: str) -> str:
    prev = None
    while prev != txt:
        prev, txt = txt, _WRAPPED.sub(lambda m: m.group(1) or m.group(2), txt)
    return txt


def plan_header(page, table, plans: list[str]) -> list[tuple[float, float, str]] | None:
    """Column x ranges of a header row that names two or more plans, e.g. PREMIUM | ELITE | ROYAL."""
    import fitz
    for r in table.rows[:2]:
        found = []
        for c in r.cells:
            if not c:
                continue
            tx = re.sub(r"\s", "", page.get_text("text", clip=fitz.Rect(c))).upper()
            hits = [p for p in plans if p.upper() in tx]
            if len(hits) == 1 and len(tx) < 25:
                found.append((c[0], c[2], hits[0]))
        if len(found) >= 2:
            return found
    return None


def plans_of_cell(cell, cols) -> list[str]:
    """Plans whose header column the cell covers by at least half; a merged cell can cover all."""
    out = []
    for x0, x1, plan in cols:
        overlap = min(cell[2], x1) - max(cell[0], x0)
        if overlap >= 0.5 * (x1 - x0) or (cell[0] >= x0 - 2 and cell[2] <= x1 + 2):
            out.append(plan)
    return out


def table_chunks(page, tables, strip_regex=None, plan_cols=None) -> list[tuple[int, str | None, str]]:
    """Tables hold sub-limits and room rent caps, so they get their own chunks.

    Cell text is read with a clip rectangle per cell, which keeps word spacing
    (Table.extract() drops spaces on justified text in some PDFs).
    Returns (section_label or None, text). A row that opens with a numbered clause
    starts its own chunk and names the section.
    """
    out: list[tuple[int, str | None, str]] = []
    for ti, t in enumerate(tables):
        cols = (plan_cols or {}).get(ti)
        rows = []
        for r in t.rows:
            cells = []
            for c in r.cells:
                txt = _cell_text(page, c, strip_regex)
                if txt and cols:
                    # plan aware: a value cell names the plan it belongs to, so the model
                    # cannot blend PREMIUM and ROYAL limits from one row
                    owners = plans_of_cell(c, cols)
                    if owners and not any(p.upper() in txt.upper().replace(" ", "") for p in owners):
                        txt = f"{'/'.join(owners)}: {txt}"
                cells.append(txt)
            if any(cells):
                rows.append(" | ".join(c for c in cells if c))
        if len(" ".join(rows)) < 40:
            continue
        header = rows[0] if len(rows[0]) < 150 and not SUBCLAUSE_RE.match(rows[0]) else None
        body = rows[1:] if header else rows
        # room left for one row once the table header and its newline are in the chunk
        room = CHUNK_MAX - (len(header) + 1 if header else 0)
        body = [piece for row in body for piece in split_row(row, room)]
        group, size, label = ([header] if header else []), len(header or ""), None

        def flush():
            nonlocal group, size, label
            if group and (len(group) > 1 or not header):
                out.append((ti, label, "\n".join(group)))
            group, size, label = ([header] if header else []), len(header or ""), None

        for row in body:
            starts_clause = bool(SUBCLAUSE_RE.match(row))
            # size counts the newline that joins each row
            if (starts_clause and size > len(header or "")) or (size + 1 + len(row) > CHUNK_MAX and len(group) > (1 if header else 0)):
                flush()
            if starts_clause and label is None:
                label = clause_label(row.split(" | ")[0])
            group.append(row)
            size += len(row) + (1 if len(group) > 1 else 0)
        flush()
    return out


def split_row(row: str, room: int) -> list[str]:
    """Split a table row longer than room by cell groups, repeating the row header cell.

    The first cell names the row (a benefit, an age band), so every piece keeps it and can be
    read on its own. A single cell longer than room is split by sentence or word.
    """
    if len(row) <= room:
        return [row]
    cells = row.split(" | ")
    head, rest = (cells[0], cells[1:]) if len(cells) > 1 and len(cells[0]) < room // 3 else ("", cells)
    prefix = head + " | " if head else ""
    limit = room - len(prefix)
    pieces, cur = [], []

    def cur_len():
        return len(" | ".join(cur))

    for cell in rest:
        parts = [cell] if len(cell) <= limit else _split_text(cell, limit)
        for p in parts:
            if cur and cur_len() + 3 + len(p) > limit:
                pieces.append(prefix + " | ".join(cur))
                cur = []
            cur.append(p)
    if cur:
        pieces.append(prefix + " | ".join(cur))
    return pieces


def _split_text(text: str, limit: int) -> list[str]:
    out, buf = [], ""
    for w in text.split():
        if buf and len(buf) + 1 + len(w) > limit:
            out.append(buf)
            buf = w
        else:
            buf = (buf + " " + w).strip()
    if buf:
        out.append(buf)
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
    # PDFs pad running headers with long runs of spaces ("Co. Ltd      Oriental ..."), so
    # collapse horizontal whitespace first and strip_regex can be written with single spaces
    # NFKC turns ligatures into letters ("ﬁ" -> "fi") and odd spaces into plain spaces
    raw = unicodedata.normalize("NFKC", raw)
    raw = re.sub(r"[ \t]+", " ", raw)
    if strip_regex:
        raw = re.sub(strip_regex, "", raw)
    # Some PDFs (Royal Sundaram) render the rupee sign as a backtick: "`5,000", "(`)", "Amount in `"
    return re.sub(r"`(?=\s?\d)|(?<=\()`(?=\))|(?<=\bin )`", "₹", raw)


def column_keys(page, boxes) -> list[tuple[int, int]]:
    """Reading order key per box: (half of a spread, text column), else (0, 0).

    Brochures such as Royal Sundaram's are landscape two-page spreads with two or three text
    columns per page. Sorting by y alone reads straight across the columns and mixes their
    lines, so on landscape pages each box is assigned to the left or right page and then to a
    column (boxes that overlap horizontally share a column), read left to right.
    """
    w, h = page.rect.width, page.rect.height
    if w <= h * 1.2:
        return [(0, 0)] * len(boxes)
    keys = [(0, 0)] * len(boxes)
    for half in (0, 1):
        idx = [i for i, b in enumerate(boxes) if ((b[0] + b[2]) / 2 >= w / 2) == bool(half)]
        cols: list[list[float]] = []  # [x0, x1] per column
        assign = {}
        for i in sorted(idx, key=lambda i: boxes[i][0]):
            x0, x1 = boxes[i][0], boxes[i][2]
            for ci, (c0, c1) in enumerate(cols):
                if min(x1, c1) - max(x0, c0) > 0.5 * min(x1 - x0, c1 - c0):
                    cols[ci] = [min(c0, x0), max(c1, x1)]
                    assign[i] = ci
                    break
            else:
                cols.append([x0, x1])
                assign[i] = len(cols) - 1
        order = sorted(range(len(cols)), key=lambda ci: cols[ci][0])
        rank = {ci: r for r, ci in enumerate(order)}
        for i in idx:
            keys[i] = (half, rank[assign[i]])
    return keys


def opens_with_exclusion(c: dict) -> bool:
    for where in (c["section"], c["text"][:90]):
        m = EXCL_CODE.search(where)
        if m and not re.search(r"shall not apply|not applicable|does not apply", c["text"][m.end():m.end() + 80], re.I):
            return True
    return False


def manifest_args(r: dict, policy_dir) -> tuple:
    """(path, skip_pages, strip_regex, plans) from one manifest row, shared by every caller."""
    skip = {int(x) for x in re.split(r"[;,]", r.get("skip_pages") or "") if x.strip().isdigit()}
    plans = [p.strip() for p in (r.get("plans") or "").split(";") if p.strip()]
    return policy_dir / r["file"], skip, (r.get("strip_regex") or "").strip() or None, plans


def chunk_plans(text: str, plans: list[str]) -> str:
    """Plans named in a chunk, as a ;-joined string (Chroma metadata cannot hold lists)."""
    # Case matters: "PREMIUM" is an Oriental plan, "premium" is what the customer pays. A title
    # case name counts only when followed by Plan or Citizen ("Gold Plan", "Senior Citizen").
    def named(p):
        return re.search(rf"\b{re.escape(p)}\b", text) or \
            re.search(rf"\b{re.escape(p.title())}\s+(?:Plan|Citizen)\b", text)
    return ";".join(p for p in plans if named(p))


def parse_pdf(path, skip_pages=frozenset(), strip_regex: str | None = None, plans=None) -> dict:
    import fitz  # imported lazily so build_chunks can be tested without it

    doc = fitz.open(path)
    pages_lines, page_tables, sparse = [], [], []
    plans = plans or []
    carried = None  # plan columns of a benefit table that continues over the following pages
    for i, page in enumerate(doc):
        tables = find_tables(page) if (i + 1) not in skip_pages else []
        rects = [tuple(t.bbox) for t in tables]
        plan_cols = {}
        if plans:
            if not tables:
                carried = None  # a page without a table ends the benefit table
            for ti, t in enumerate(tables):
                hdr = plan_header(page, t, plans)
                if hdr:
                    carried = hdr
                elif carried and t.col_count < len(plans) + 2:
                    carried = None  # a narrower table is a different table (e.g. a limits list)
                if carried:
                    plan_cols[ti] = carried
        # Text outside tables only, so two-column tables do not interleave into prose.
        tchunks = table_chunks(page, tables, strip_regex, plan_cols)
        items = []
        blocks = [b for b in page.get_text("dict", sort=True)["blocks"] if b.get("type") == 0]
        colkey = column_keys(page, [b["bbox"] for b in blocks] + rects)
        for bi, blk in enumerate(blocks):
            ck = colkey[bi]
            prev_y1 = None
            for ln in blk["lines"]:
                bb = ln["bbox"]
                if _inside(bb, rects):
                    continue
                txt = "".join(sp["text"] for sp in ln["spans"])
                # a visible vertical gap means a paragraph break
                gap = prev_y1 is not None and bb[1] - prev_y1 > 6
                items.append((ck, bb[1], bb[0], ("\n" if gap else "") + txt + "\n"))
                prev_y1 = bb[3]
        # join lines first, then strip, so multi-line strip patterns still match
        # one marker per table chunk, placed where its table starts on the page
        for k, (tidx, _, _) in enumerate(tchunks):
            r = rects[tidx]
            items.append((colkey[len(blocks) + tidx], r[1], r[0], f"{TABLE_MARK}{k}\n"))
        items.sort(key=lambda x: (x[0], round(x[1], 1), x[2]))
        text = ""
        for _, _, _, txt in items:
            text += txt if not txt.startswith(TABLE_MARK) else "\n" + txt + "\n"
        text = clean_raw(text, strip_regex)
        pages_lines.append([ln.strip() for ln in text.splitlines()])
        page_tables.append([(label, text) for _, label, text in tchunks])
        full = page.get_text("text")
        if (i + 1) not in skip_pages and len(full.strip()) < MIN_CHARS_PER_PAGE:
            sparse.append(i + 1)
    chunks = build_chunks(pages_lines, page_tables, skip_pages)
    for c in chunks:
        c["plans"] = chunk_plans(c["text"], plans)
        # Insurers do not share heading styles, but every IRDAI standard exclusion carries its code
        # ("Code - Excl 18", Oriental prints "ExcI18"). Label a chunk as an exclusion when the code
        # opens it (clause heading or first words), so the prompt's exclusion rule applies as it does
        # to National Mediclaim's "4 Exclusions" part. A code further down can sit inside a benefit
        # ("Refractive Error- Code- ExcI15 shall not apply for this benefit"), and some section labels
        # run on for many pages (SBI), so neither of those counts.
        if "xclusion" not in (c.get("part") or "") and opens_with_exclusion(c):
            c["part"] = "Exclusions (IRDAI exclusion code)"
    return {"n_pages": len(doc), "sparse_pages": sparse, "chunks": chunks}
