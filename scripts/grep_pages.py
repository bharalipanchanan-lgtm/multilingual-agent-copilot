import json, pathlib, re, sys
root = pathlib.Path(r"D:\New folder\multilingual-agent-copilot")
pat = re.compile(sys.argv[1], re.I)
for f in sorted((root/"data"/"pages").glob("[0-9][0-9]-*.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    hits = []
    for p in d["pages"]:
        t = re.sub(r"\s+", " ", p["text"])
        for m in pat.finditer(t):
            hits.append((p["page"], t[max(0,m.start()-int(sys.argv[2])):m.end()+int(sys.argv[3])]))
    print(f"== {f.stem[:40]} ({len(hits)})")
    for pg, s in hits[:int(sys.argv[4])]:
        print(f"   p{pg}: {s}")
