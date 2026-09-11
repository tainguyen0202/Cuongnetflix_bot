FROM python:3.12-slim

WORKDIR /app

# Cài dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy code bot (không copy .env — env vars set trên hosting)
COPY config.py supabase_client.py handlers.py api_server.py main.py checker.py proxies.py shrinkme.py lang.py ./
COPY PROXY_URLS.txt ./

# Mở port API server (web gọi check-cookie)
EXPOSE 8081

CMD ["python3", "-u", "main.py"]
