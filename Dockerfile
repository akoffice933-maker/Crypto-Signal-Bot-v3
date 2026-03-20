FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc curl wget && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p data logs results
RUN useradd -m -u 1000 bot && chown -R bot:bot /app
USER bot
EXPOSE 8000
CMD ["python", "main.py", "--log-level=INFO"]
