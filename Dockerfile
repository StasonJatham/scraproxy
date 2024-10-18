FROM python:3.12-slim-bullseye

# Set environment variables
ENV PLAYWRIGHT_BROWSERS_PATH=0
ENV API_KEY=none

# Set the working directory
WORKDIR /app

# Install required system dependencies for Playwright and Chromium
RUN apt-get update && apt-get install -y \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    libcairo2 \
    libxshmfence1 \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements.txt and install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright with Chromium and its dependencies
RUN playwright install --with-deps chromium

# Copy the current directory contents into the container
COPY . .

# Expose port 8000 for the FastAPI app
EXPOSE 8000

# Command to run Uvicorn with your FastAPI app
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]