# Author: Bradley R. Kinnard
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY src/ src/
RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["uvicorn", "ironroot.main:app", "--host", "0.0.0.0", "--port", "8000"]
