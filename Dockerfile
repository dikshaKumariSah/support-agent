FROM python:3.14-slim

# Print logs immediately, so they show up in the host's log viewer.
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install packages first: Docker reuses this step while requirements.txt doesn't change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 0.0.0.0 accepts connections from outside the container.
# Render sets $PORT; locally it falls back to 8000.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
