FROM python:3.12-slim

RUN pip install --no-cache-dir aiohttp yt-dlp Pillow \
    && useradd --create-home --uid 10001 xembed

WORKDIR /app
COPY --chown=xembed:xembed app.py /app/app.py
COPY --chown=xembed:xembed static /app/static
USER xembed

CMD ["python", "app.py"]
