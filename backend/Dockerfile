FROM python:3.12-slim

WORKDIR /app

# System dependencies
# ffmpeg: NEW (Voice AI Part 3) — decodes TTS provider output (mp3/wav) to
# raw PCM so it can be resampled to 8kHz mu-law for Twilio Media Streams.
# Only used by services/call_audio_utils.py; nothing else in the backend
# depends on it.
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Create uploads directory
RUN mkdir -p /tmp/thunderbots_uploads

EXPOSE 8000

# Use uvloop + httptools for maximum async performance
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
