# Cullenect Label Planner — React UI + FastAPI + a real OpenSCAD renderer.
#
# The renderer must be a 2025+ OpenSCAD: colored 3MF export (`export-3mf/color-mode`)
# does not exist in the 2021.01 that Debian stable ships, and the Manifold backend is
# what makes a label render in ~0.5s instead of ~2 minutes. There is no apt package for
# that, so we take the official AppImage and *extract* it — extraction needs no FUSE,
# which a container can't provide anyway.
FROM node:20-slim AS web
WORKDIR /build
COPY app/package.json app/package-lock.json ./
RUN npm ci
COPY app/ ./
RUN npm run build

# trixie, not bookworm: fonts-montserrat only exists from Debian 13 onward.
FROM python:3.12-slim-trixie

# Pinned deliberately: a moving nightly would make renders irreproducible.
ARG OPENSCAD_APPIMAGE=https://files.openscad.org/snapshots/OpenSCAD-2026.01.02.ai30348-x86_64.AppImage

# The Ubuntu font family is non-free in Debian (UFL licence), so that component
# has to be enabled or `fonts-ubuntu` resolves to nothing and OpenSCAD would
# silently substitute a different face for every Ubuntu-font label.
RUN sed -i 's/^Components: main$/Components: main non-free/' /etc/apt/sources.list.d/debian.sources \
 && apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl fontconfig \
      fonts-open-sans fonts-ubuntu fonts-montserrat \
      libgl1 libegl1 libopengl0 libglx0 libfontconfig1 libfreetype6 \
      libharfbuzz0b libgraphite2-3 libgmp10 libexpat1 libpng16-16 \
      libx11-6 libx11-xcb1 libxau6 libxcb1 libxdmcp6 \
      libbrotli1 libbsd0 libmd0 libuuid1 libgpg-error0 libcom-err2 zlib1g \
 && curl -fsSL "$OPENSCAD_APPIMAGE" -o /tmp/openscad.AppImage \
 && chmod +x /tmp/openscad.AppImage \
 && cd /tmp && /tmp/openscad.AppImage --appimage-extract > /dev/null \
 && mv /tmp/squashfs-root /opt/openscad \
 && rm -f /tmp/openscad.AppImage \
 && /opt/openscad/AppRun --version \
 && apt-get purge -y curl && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/* /tmp/*

ENV PYTHONUNBUFFERED=1 \
    OPENSCAD_BIN=/opt/openscad/AppRun \
    DATA_DIR=/data \
    RENDER_CACHE=/data/render-cache

WORKDIR /srv
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/scad ./scad
COPY --from=web /build/dist ./static

# The label library lives here — mount a named volume (see docker-compose.yml).
VOLUME ["/data"]
EXPOSE 80

HEALTHCHECK --interval=60s --timeout=10s --start-period=20s \
  CMD python3 -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:80/api/health',timeout=5)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]
