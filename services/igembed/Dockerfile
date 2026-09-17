FROM python:3.12-slim

RUN pip install --no-cache-dir aiohttp yt-dlp Pillow \
    && useradd --create-home --uid 10001 igembed

WORKDIR /app
COPY --chown=igembed:igembed app.py /app/app.py
USER igembed

CMD ["python", "app.py"]
