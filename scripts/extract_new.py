import pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "ingest"))
from extract import extract
from concurrent.futures import ProcessPoolExecutor
root = pathlib.Path(__file__).resolve().parent.parent
out = root / "data" / "pages"
pdfs = sorted(p for p in (root/"data"/"policies").glob("*.pdf")
              if p.name[:2].isdigit() and p.name[2] == "-" and not (out / f"{p.stem}.json").exists())
def run(p):
    return extract(p, out)
if __name__ == "__main__":
    t=time.time()
    with ProcessPoolExecutor(8) as ex:
        for r in ex.map(run, pdfs):
            flag = "  <-- scanned?" if r["empty"] > r["pages"] * 0.2 else ""
            print(f"{r['pdf']:<72} {r['pages']:>4} pages {r['empty']:>3} blank {r['chars']:>8} chars{flag}")
    print(f"{len(pdfs)} done in {time.time()-t:.0f}s")

