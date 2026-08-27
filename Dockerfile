# -----------------------------------------
# FOX-KRİPTO DIGITALOCEAN DOCKERFILE
# -----------------------------------------
FROM python:3.12-slim
LABEL maintainer="FoxKripto"
LABEL build.version="20260827-v5-clean"

# Çalışma dizinini ayarla
WORKDIR /app

# Gerekli sistem paketlerini yükle
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Bağımlılıkları kopyala ve yükle
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Proje dosyalarını kopyala
COPY . .

# Port tanımı
EXPOSE 8000

# Varsayılan başlangıç komutu
CMD ["sh", "-c", "uvicorn app:app_api --host 0.0.0.0 --port ${PORT:-8000}"]
