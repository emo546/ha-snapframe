ARG BUILD_ARCH
FROM ghcr.io/home-assistant/${BUILD_ARCH}-base:3.20

# Bez -dev balíkov: všetky závislosti majú musllinux wheely, takže sa nič
# nekompiluje. --only-binary to poistí – build spadne nahlas namiesto toho,
# aby ticho prešiel na pomalý build zo zdrojov.
RUN apk add --no-cache \
    python3 \
    py3-pip \
    libheif \
    cifs-utils

COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --break-system-packages --no-cache-dir --only-binary=:all: \
        -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

COPY rootfs /

RUN chmod a+x /usr/bin/run.sh /usr/bin/watcher.py /usr/bin/webserver.py

# Supervisor podľa tohto reštartuje zamrznutý add-on. Port si berieme zo súboru,
# ktorý zapíše run.sh – do prostredia HEALTHCHECKu sa konfigurácia nedostane.
HEALTHCHECK --interval=60s --timeout=10s --start-period=180s --retries=3 \
    CMD python3 -c "import pathlib, urllib.request; \
p = pathlib.Path('/tmp/snapframe.port'); \
port = p.read_text().strip() if p.is_file() else '8099'; \
urllib.request.urlopen('http://127.0.0.1:%s/health' % port, timeout=5)" || exit 1

CMD [ "/usr/bin/run.sh" ]
