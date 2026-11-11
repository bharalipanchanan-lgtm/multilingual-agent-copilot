#!/usr/bin/env python3
"""Page-aware text extraction for policy wordings.

    python3 ingest/extract.py [pdf_dir] [out_dir]
    python3 ingest/extract.py --repair     # only re-read garbled pages of existing JSONs

Writes one JSON per PDF to data/pages/, shaped:

    {"source": "...pdf", "pages": [{"page": 1, "text": "..."}, ...]}

Page numbers are the PDF's own 1-based page index, which is what the UI
cites. If a wording's printed page numbers differ from the PDF index,
that offset must be recorded per product — do not silently assume they
match.

Requires poppler's pdftotext (brew install poppler).
"""

import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent

DEFAULT_PDF_DIR = ROOT / "data" / "policies"
DEFAULT_OUT = ROOT / "data" / "pages"


def page_count(pdf: pathlib.Path) -> int:
    try:
        out = subprocess.run(
            ["pdfinfo", str(pdf)], capture_output=True, text=True, check=True
        ).stdout
        m = re.search(r"^Pages:\s+(\d+)", out, re.M)
        if m:
            return int(m.group(1))
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    import fitz
    with fitz.open(pdf) as doc:
        return len(doc)


def _run(pdf: pathlib.Path, n: int, *flags: str) -> str:
    try:
        out = subprocess.run(
            ["pdftotext", "-enc", "UTF-8", *flags, "-f", str(n), "-l", str(n), str(pdf), "-"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        ).stdout
        return re.sub(r"\n{3,}", "\n\n", out).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        import fitz
        with fitz.open(pdf) as doc:
            page = doc[n - 1]
            mode = "blocks" if "-layout" in flags else "text"
            if mode == "blocks":
                blocks = sorted(page.get_text("blocks"), key=lambda b: (round(b[1], 1), round(b[0], 1)))
                txt = "\n".join(b[4].strip() for b in blocks if b[4].strip())
            else:
                txt = page.get_text("text")
            return re.sub(r"\n{3,}", "\n\n", txt).strip()


def page_text(pdf: pathlib.Path, n: int) -> str:
    """Reading order — the content-stream order, which follows columns
    correctly. Use this for quoting clauses.

    `-layout` is NOT usable for quotes: on a two-column page it reads
    across the gutter, so a sentence that is continuous on the page comes
    out interleaved with the neighbouring column. Tables need -layout,
    which is why both are stored."""
    return _run(pdf, n)


def page_layout(pdf: pathlib.Path, n: int) -> str:
    """Spatial layout — keeps benefit tables and sum-insured grids aligned.
    Use this for reading tables, never for quoting prose."""
    return _run(pdf, n, "-layout")


# Some wordings carry an invisible OCR layer (font "HiddenHorzOCR") over the real text.
# pdftotext merges both, so a page reads "cla I, l1i ms where I I j I I tI". These are the
# marks that layer leaves: lone letters, bars run together, a capital I inside a lower-case
# word, letters and digits mixed.
OCR_JUNK = re.compile(
    r"[^aA&/*•\-–—\d\W]"
    r"|[Il|]{2,}"
    r"|\S*[a-z]I\S*"
    r"|\S*[a-zA-Z]\d\S*"
    r"|\S*\d(?!st|nd|rd|th)[a-zA-Z]\S*",
    re.A,
)
_NOT_JUNK = re.compile(r"[ivxIVX]+|[A-Z]\d{1,3}|UIN\S*|[A-Z]{2,}\d\S*")


def garbled(text: str, limit: float = 0.08) -> bool:
    """True when more than `limit` of the words are OCR-overlay noise.
    Clean wording stays under 0.06; broken pages run 0.10 to 0.60."""
    toks = [t for t in text.split() if not re.fullmatch(r"[A-Za-z0-9]{1,3}[.)]", t)]  # list markers "F." "ii)"
    toks = [t.strip(".,;:()'\"") for t in toks]
    toks = [t for t in toks if t]
    if len(toks) < 5:
        return False
    junk = sum(1 for t in toks if OCR_JUNK.fullmatch(t) and not _NOT_JUNK.fullmatch(t))
    return junk / len(toks) > limit


def clean_page_text(pdf: pathlib.Path, n: int) -> str:
    """Page text from PyMuPDF without the invisible OCR layer."""
    import pymupdf
    with pymupdf.open(pdf) as d:
        out = []
        for b in d[n - 1].get_text("dict")["blocks"]:
            for line in b.get("lines", []):
                s = "".join(sp["text"] for sp in line["spans"] if "OCR" not in sp.get("font", ""))
                if s.strip():
                    out.append(s)
        return "\n".join(out)


def repair_page(pdf: pathlib.Path, page: dict) -> bool:
    """Swap a garbled page's text for the clean re-read, if the re-read is clean."""
    if not garbled(re.sub(r"\s+", " ", page["text"])):
        return False
    fixed = clean_page_text(pdf, page["page"])
    if not fixed.strip() or garbled(re.sub(r"\s+", " ", fixed)):
        return False
    page["text"] = fixed
    page["reread_without_ocr_layer"] = True
    return True


def extract(pdf: pathlib.Path, out_dir: pathlib.Path) -> dict:
    total = page_count(pdf)
    pages = []
    empty = 0
    for n in range(1, total + 1):
        txt = page_text(pdf, n)
        page = {"page": n, "text": txt}
        if repair_page(pdf, page):
            txt = page["text"]
        if len(txt) < 40:
            empty += 1
        pages.append({**page, "text": txt, "layout": page_layout(pdf, n)})

    doc = {
        "source": pdf.name,
        "page_count": total,
        "pages_without_text": empty,
        "pages": pages,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{pdf.stem}.json"
    dest.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return {
        "pdf": pdf.name,
        "pages": total,
        "empty": empty,
        "chars": sum(len(p["text"]) for p in pages),
        "out": str(dest.relative_to(ROOT)),
    }


def repair(pdf_dir: pathlib.Path, out_dir: pathlib.Path) -> int:
    """Fix only the garbled pages of already-extracted JSONs; every other page stays as it was."""
    for f in sorted(out_dir.glob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        pdf = pdf_dir / doc["source"]
        if not pdf.exists():
            continue
        fixed = [p["page"] for p in doc["pages"] if repair_page(pdf, p)]
        if fixed:
            f.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{doc['source']}: re-read pages {fixed} without the OCR layer")
    return 0


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--repair"]
    pdf_dir = pathlib.Path(args[0]) if len(args) > 0 else DEFAULT_PDF_DIR
    out_dir = pathlib.Path(args[1]) if len(args) > 1 else DEFAULT_OUT
    if "--repair" in sys.argv:
        return repair(pdf_dir, out_dir)

    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if not pdfs:
        print(f"no PDFs in {pdf_dir}", file=sys.stderr)
        return 1

    print(f"{'pdf':<40} {'pages':>6} {'blank':>6} {'chars':>9}")
    for pdf in pdfs:
        r = extract(pdf, out_dir)
        flag = "  <-- CHECK: scanned?" if r["empty"] > r["pages"] * 0.2 else ""
        print(f"{r['pdf']:<40} {r['pages']:>6} {r['empty']:>6} {r['chars']:>9}{flag}")
    print(f"\nwritten to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
