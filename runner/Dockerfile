FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/runner
COPY runner/entrypoint.py /opt/runner/entrypoint.py

RUN useradd --uid 65534 --no-create-home --shell /usr/sbin/nologin runner

USER 65534:65534
ENTRYPOINT ["/usr/local/bin/python", "-I", "-S", "/opt/runner/entrypoint.py"]
