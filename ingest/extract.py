#!/usr/bin/env python3
"""Page-aware text extraction for policy wordings.

    python3 ingest/extract.py [pdf_dir] [out_dir]

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
            ["pdftotext", *flags, "-f", str(n), "-l", str(n), str(pdf), "-"],
            capture_output=True,
            text=True,
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


def extract(pdf: pathlib.Path, out_dir: pathlib.Path) -> dict:
    total = page_count(pdf)
    pages = []
    empty = 0
    for n in range(1, total + 1):
        txt = page_text(pdf, n)
        if len(txt) < 40:
            empty += 1
        pages.append({"page": n, "text": txt, "layout": page_layout(pdf, n)})

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


def main() -> int:
    pdf_dir = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PDF_DIR
    out_dir = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT

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
