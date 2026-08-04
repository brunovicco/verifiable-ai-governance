#!/bin/bash
set -euo pipefail
exec > >(tee /var/log/vai-cloud-init.log) 2>&1

APP_DIR=/opt/vai-governance
GIT_REPO_URL="${git_repo_url}"
GIT_REF="${git_ref}"
POSTGRES_PASSWORD="${postgres_password}"
MINIO_PASSWORD="${minio_password}"
AUDIT_SALT="${audit_salt}"
APP_DOMAIN="${app_domain}"
API_DOMAIN="${api_domain}"

# --- 1. Sistema base ---
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y

# --- 2. Swap (build do Next.js + freshclam do ClamAV pedem folga de memoria) ---
if [ ! -f /swapfile ]; then
  fallocate -l 4G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# --- 3. Firewall interno do host (alem da Security List da VCN) ---
iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT || true
iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT || true
netfilter-persistent save || (iptables-save > /etc/iptables/rules.v4 || true)

# --- 4. Docker Engine + Compose plugin ---
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
ARCH="$(dpkg --print-architecture)"
CODENAME="$(. /etc/os-release && echo "$VERSION_CODENAME")"
echo "deb [arch=$ARCH signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $CODENAME stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
usermod -aG docker ubuntu

# --- 5. Clonar o projeto (ref fixo, nao o HEAD do branch a cada boot) ---
git clone --no-checkout "$GIT_REPO_URL" "$APP_DIR"
cd "$APP_DIR"
git fetch --depth 1 origin "$GIT_REF"
git checkout --detach FETCH_HEAD
GIT_SHA="$(git rev-parse --short HEAD)"
cp .env.example .env

# Ajusta as variaveis criticas do .env (mantendo o restante do exemplo)
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$POSTGRES_PASSWORD|" .env || echo "POSTGRES_PASSWORD=$POSTGRES_PASSWORD" >> .env
sed -i "s|^MINIO_ROOT_PASSWORD=.*|MINIO_ROOT_PASSWORD=$MINIO_PASSWORD|" .env || echo "MINIO_ROOT_PASSWORD=$MINIO_PASSWORD" >> .env
sed -i "s|^AUDIT_HASH_SALT=.*|AUDIT_HASH_SALT=$AUDIT_SALT|" .env || echo "AUDIT_HASH_SALT=$AUDIT_SALT" >> .env
{
  echo "NEXT_PUBLIC_API_URL=https://$API_DOMAIN"
  echo "CORS_ORIGINS=https://$APP_DOMAIN"
  echo "APP_ENV=local"
  echo "OIDC_ENABLED=false"
  echo "NEXT_PUBLIC_AUTH_MODE=local"
  echo "NEXT_PUBLIC_DEMO_READ_ONLY=true"
  echo "NEXT_PUBLIC_DEPLOYMENT_LABEL=Demo pública — GCP"
  echo "NEXT_PUBLIC_GIT_SHA=$GIT_SHA"
} >> .env

# --- 6. Override de producao: restart policy + bind em loopback ---
# ports usa a tag "!override" (nao lista simples): o Compose concatena listas de
# 'ports:' entre arquivos -f, entao sem essa tag o bind duplicado (0.0.0.0 do
# compose base + 127.0.0.1 daqui) falha com "address already in use".
cat > docker-compose.override.yml <<'OVERRIDE_EOF'
services:
  postgres:
    restart: unless-stopped
    ports: !override
      - "127.0.0.1:5432:5432"
  object-storage:
    restart: unless-stopped
  malware-scanner:
    restart: unless-stopped
  api:
    restart: unless-stopped
    ports: !override
      - "127.0.0.1:8000:8000"
  web:
    restart: unless-stopped
    ports: !override
      - "127.0.0.1:3000:3000"
OVERRIDE_EOF

chown -R ubuntu:ubuntu "$APP_DIR"

# --- 7. Build e subida (feito como root; docker root e equivalente aqui) ---
docker compose build
docker compose up -d

# --- 8. Semear dados de exemplo (melhor esforco - roda so no primeiro boot,
# ja que o cloud-init nao roda de novo; nao bloqueia o resto do provisionamento
# se falhar). Ve scripts/seed_demo_data.py: aborta sozinho se dados [DEMO] ja
# existirem, entao seguro mesmo que este passo seja executado mais de uma vez.
docker compose exec -T -u root api mkdir -p /workspace/scripts || true
docker compose cp scripts/seed_demo_data.py api:/workspace/scripts/seed_demo_data.py || true
docker compose exec -T api python scripts/seed_demo_data.py \
  || echo "aviso: semeadura de dados de exemplo falhou ou ja existia; continuando o provisionamento"

# --- 9. Caddy (reverse proxy + TLS automatico) ---
apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
apt-get update -y
apt-get install -y caddy

# Demo publica sem credencial: qualquer pessoa acessa e "loga" com uma
# identidade local autodeclarada (modo dev, sem verificacao real - ver
# NEXT_PUBLIC_AUTH_MODE=local acima). Sem uma barreira de escrita aqui,
# isso permitiria qualquer visitante mutar dados. O matcher @write bloqueia
# metodos que nao sejam leitura (GET/HEAD/OPTIONS) no dominio da API antes
# de chegarem ao backend, mantendo a demo navegavel mas somente leitura.
cat > /etc/caddy/Caddyfile <<CADDY_EOF
$APP_DOMAIN {
    header {
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "camera=(), microphone=(), geolocation=()"
        X-Frame-Options "DENY"
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
    }
    reverse_proxy 127.0.0.1:3000
}

$API_DOMAIN {
    header {
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "camera=(), microphone=(), geolocation=()"
        X-Frame-Options "DENY"
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
    }
    @write {
        not method GET HEAD OPTIONS
    }
    respond @write "Demo publica somente leitura - escrita desabilitada." 403
    reverse_proxy 127.0.0.1:8000
}
CADDY_EOF

systemctl restart caddy
systemctl enable caddy
systemctl enable docker

echo "Provisionamento concluido." > /opt/vai-governance/.cloud-init-done
