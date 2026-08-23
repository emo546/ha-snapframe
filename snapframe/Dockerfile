ARG BUILD_ARCH
FROM ghcr.io/home-assistant/${BUILD_ARCH}-base:3.20

RUN apk add --no-cache \
    python3 \
    py3-pip \
    libheif \
    jpeg-dev \
    zlib-dev \
    cifs-utils

RUN pip3 install --break-system-packages --no-cache-dir \
    pillow \
    pillow-heif \
    flask \
    waitress \
    pdfplumber \
    anthropic

COPY rootfs /

RUN chmod a+x /usr/bin/run.sh /usr/bin/watcher.py /usr/bin/webserver.py

CMD [ "/usr/bin/run.sh" ]
