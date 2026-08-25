FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV APP_PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ .

RUN adduser --disabled-password --gecos "" appuser
USER appuser

EXPOSE 8080

CMD ["opentelemetry-instrument", "python", "main.py"]

# Debug variant: identical to runtime, plus tools for live troubleshooting
# (heap/CPU profiling, ptrace-based debugging). Swap a Deployment's image to
# this tag temporarily rather than shipping these tools in the normal image.
FROM runtime AS debug

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    procps \
    gdb \
    strace \
    lsof \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir memray py-spy

USER appuser
