# Optional self-contained sandbox image (portable: no host /usr mount).
# Build once where a registry is reachable:   scripts/build_sandbox_image.sh
# VeriCode uses it automatically when `vericode-sandbox:full` (or VERICODE_SANDBOX_IMAGE) exists locally;
# otherwise it falls back to the host-toolchain mode (empty local image + host /usr read-only).
# Keep the Python minor version equal to the one used to create project virtualenvs (site-packages are mounted).
FROM python:3.13-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends nodejs npm ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --uid 65534 --no-create-home --shell /usr/sbin/nologin sandbox 2>/dev/null || true
WORKDIR /work
USER 65534:65534
