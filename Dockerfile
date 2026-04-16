# Multi-stage build to reduce final image size
FROM python:3.12-slim as builder

# Install dependencies for building and downloading
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Build JDK stage
ARG TARGETARCH
ENV JAVA_HOME=/opt/jdk

RUN set -eux; \
    case "${TARGETARCH}" in \
      "amd64") JDK_URL="https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.14%2B7/OpenJDK17U-jdk_x64_linux_hotspot_17.0.14_7.tar.gz" ;; \
      "arm64") JDK_URL="https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.14%2B7/OpenJDK17U-jdk_aarch64_linux_hotspot_17.0.14_7.tar.gz" ;; \
      *) echo "Unsupported TARGETARCH: ${TARGETARCH}"; exit 1 ;; \
    esac; \
    export JDK_URL; \
    python - <<'PY'
import os
import pathlib
import shutil
import tarfile
import urllib.request

jdk_url = os.environ["JDK_URL"]
archive = pathlib.Path("/tmp/jdk.tar.gz")
download_dir = pathlib.Path("/tmp/jdk_extract")
download_dir.mkdir(parents=True, exist_ok=True)
urllib.request.urlretrieve(jdk_url, archive)
with tarfile.open(archive) as tf:
    tf.extractall(download_dir)
extracted = next(download_dir.iterdir())
target = pathlib.Path("/opt/jdk")
if target.exists():
    shutil.rmtree(target)
shutil.move(str(extracted), str(target))
PY

# Verify Java installation
RUN /opt/jdk/bin/java -version && /opt/jdk/bin/javac -version

# Final stage
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    JAVA_HOME=/opt/jdk \
    PATH="${JAVA_HOME}/bin:${PATH}"

# Create app user for security
RUN useradd -m -u 1000 appuser

# Set working directory
WORKDIR /app

# Copy JDK from builder
COPY --from=builder /opt/jdk /opt/jdk

# Copy and install Python dependencies
COPY requirements-web.txt /app/requirements-web.txt
RUN pip install --no-cache-dir --upgrade pip setuptools && \
    pip install --no-cache-dir -r /app/requirements-web.txt

# Copy application code
COPY --chown=appuser:appuser . /app

# Create necessary directories
RUN mkdir -p /app/output /app/cache /app/trade_data && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/docs', timeout=5)" || exit 1

EXPOSE 8000

CMD ["uvicorn", "apps.web.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

