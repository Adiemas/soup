# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS build
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir .

FROM python:3.12-slim
WORKDIR /app
COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /usr/local/bin /usr/local/bin
COPY app ./app
COPY migrations ./migrations
ENV PORT=8000
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
