# Cloud image of the copilot: the same parser, bge-m3 search, checks and chat page as the laptop,
# with answers from a hosted model instead of MLX.
#
#   docker build -t claviq-copilot .
#   docker run -p 7860:7860 -e GROQ_API_KEY=... claviq-copilot      (or GEMINI_API_KEY / SARVAM_API_KEY)
#
# Without any key it still runs: the extractive backend quotes the matching clauses verbatim.
# Needs about 3 GB of memory (bge-m3 on CPU). Keys are passed at run time, never baked in.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HUB_DISABLE_XET=1 HF_HOME=/app/.hf \
    COPILOT_DEVICE=cpu COPILOT_HOST=0.0.0.0 PORT=7860 COPILOT_BACKEND=api COPILOT_PUBLIC=1 \
    TOKENIZERS_PARALLELISM=false

WORKDIR /app
COPY requirements-cloud.txt .
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install -r requirements-cloud.txt

COPY . .
# Fetch bge-m3 and build the search index inside the image, so a cold start does not re-parse
# the PDFs. The index is built here rather than copied from the laptop (platform independent).
RUN python -W ignore -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')" \
 && python -W ignore ingest.py \
 && chmod -R a+rwX /app

EXPOSE 7860
CMD ["python", "-W", "ignore", "server.py"]
