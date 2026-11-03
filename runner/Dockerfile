FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/runner
RUN python -m pip install --no-cache-dir "docker>=7.1,<8.0" "fastapi>=0.115,<1.0" "uvicorn[standard]>=0.30,<1.0"
COPY runner/entrypoint.py /opt/runner/entrypoint.py
COPY runner /opt/runner/runner

EXPOSE 8001
CMD ["uvicorn", "runner.main:app", "--host", "0.0.0.0", "--port", "8001"]
