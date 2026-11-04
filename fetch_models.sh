#!/bin/zsh
# Download models with curl (resumable). The Python downloader stalls on some networks.
# Usage: ./fetch_models.sh BAAI/bge-m3 [more repos...]
cd "$(dirname "$0")"
for repo in "$@"; do
  dest="models/${repo:t}"
  mkdir -p "$dest"
  files=$(curl -s "https://huggingface.co/api/models/$repo" | python3 -c "
import json,sys
skip=('onnx/','imgs/','.jpg','.png','.onnx','.md','.gitattributes')
for s in json.load(sys.stdin)['siblings']:
    f=s['rfilename']
    if not any(k in f for k in skip): print(f)")
  for f in ${(f)files}; do
    mkdir -p "$dest/${f:h}"
    for try in 1 2 3 4 5 6 7 8 9 10; do
      curl -sL -C - --retry 3 --speed-limit 50000 --speed-time 30 -o "$dest/$f" "https://huggingface.co/$repo/resolve/main/$f" && break
      echo "retry $f ($try)"; sleep 2
    done
  done
  touch "$dest/.fetched"; echo "FETCHED $repo"
done
