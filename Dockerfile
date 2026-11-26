# Rest-Place birthday flyer — production image
#   docker build -t flyer .
#   docker run -p 8000:8000 -e PORT=8000 flyer
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    REMBG_HOME=/models \
    U2NET_HOME=/models \
    PORT=8000 \
    OMP_NUM_THREADS=2

# libgomp1 for onnxruntime, libglib2.0-0 for opencv-headless
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# Bake the cut-out model into the image so the first request isn't a 170 MB download.
RUN mkdir -p /models \
    && python -c "from rembg import new_session; new_session('isnet-general-use')"

COPY . .

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
    CMD curl -fsS http://127.0.0.1:${PORT}/healthz || exit 1

# one worker (the models are heavy) + threads; each cut-out also runs as its own process
CMD ["sh", "-c", "exec gunicorn -b 0.0.0.0:${PORT} -w 1 --threads 4 -t 300 --keep-alive 15 --access-logfile - --error-logfile - app:app"]
