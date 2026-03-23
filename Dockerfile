FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    JAVA_HOME=/opt/jdk

ARG TARGETARCH
ENV PATH="${JAVA_HOME}/bin:${PATH}"

WORKDIR /app

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

RUN java -version && javac -version

COPY requirements-web.txt /app/requirements-web.txt
RUN pip install --no-cache-dir -r /app/requirements-web.txt

COPY . /app

RUN mkdir -p /app/output /app/cache

EXPOSE 8000

CMD ["sh", "-c", "uvicorn apps.web.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

