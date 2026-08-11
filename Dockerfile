# -----------------------------------------
# FOX-KRİPTO DIGITALOCEAN DOCKERFILE
# -----------------------------------------
FROM python:3.12-slim

# Çalışma dizinini ayarla
WORKDIR /app

# Gerekli sistem paketlerini yükle
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Bağımlılıkları kopyala ve yükle
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Proje dosyalarını kopyala
COPY . .

# Port tanımı (FastAPI & Webhook için)
EXPOSE 8000

# Varsayılan başlangıç komutu
CMD ["uvicorn", "app:app_api", "--host", "0.0.0.0", "--port", "8000"]
