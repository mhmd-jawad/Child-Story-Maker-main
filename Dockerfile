FROM python:3.13-slim

# No system packages required for this build; pip wheels cover deps.
# If you later add native deps, install them here.

# Set workdir
WORKDIR /app

# Copy only dependency files first (layer caching)
COPY requirements.txt .

# Install Python deps
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8000

# Healthcheck (no curl dependency)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request, sys; \
  urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3); sys.exit(0)"

# Run the API (serves the web UI at /)
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
