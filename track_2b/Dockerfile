FROM python:3.12-slim

WORKDIR /app
COPY src/ ./src/
COPY data/ ./data/

ENV PORT=8000
EXPOSE 8000

# Python standard library only: nothing to install, nothing to download.
CMD ["python3", "src/app.py"]
