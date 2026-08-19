FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# CPU-only torch explicitly, *before* the rest of requirements.txt — without
# this, pip resolves sentence-transformers' torch dependency to the default
# PyPI wheel, which pulls in ~1GB+ of CUDA/NVIDIA packages that are useless
# (and don't even apply) on a CPU-only deploy target.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

# Bake the embedding model's weights into the image at build time, instead
# of letting the app fetch them from Hugging Face Hub on first use at
# runtime. This isn't just convenience — pulling ~90MB from an external CDN
# on every fresh pod start is a real cold-start latency hit, and turns any
# hiccup on that network path (a restrictive egress policy, a Hub outage)
# into a crash-looping pod instead of a slow-but-working one. Baking it in
# trades image size for the ML-serving container never depending on Hub
# availability at all once built.
RUN python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
ENV HF_HUB_OFFLINE=1
# torch's default thread-pool sizing often ignores the container's cgroup CPU
# limit and matches the *node's* core count instead — fine on a dedicated
# host, but a real problem in a CPU-limited pod, where it causes the thread
# pool to thrash and can make model loading dramatically slower than it needs
# to be. Pin it to what the pod's own resource limits actually grant.
ENV OMP_NUM_THREADS=1
ENV TOKENIZERS_PARALLELISM=false

COPY app ./app
COPY ingestion ./ingestion
COPY worker ./worker
COPY alembic ./alembic
COPY alembic.ini .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
