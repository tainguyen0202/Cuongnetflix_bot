FROM python:3.12-slim

WORKDIR /app

# Cài dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy code
COPY config.py supabase_client.py handlers.py api_server.py main.py checker.py proxies.py shrinkme.py lang.py cookie_checker.py ./
COPY PROXY_URLS.txt ./

# Mở port từ $PORT (Tranger Cloud inject PORT)
EXPOSE 8081

# Start command - dùng $PORT hoặc default 8081
CMD ["sh", "-c", "python3 -u main.py"]
