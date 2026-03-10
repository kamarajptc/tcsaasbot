# DigitalOcean Droplet Deployment

This repository now includes a Droplet-oriented deployment path based on Docker Compose.

Files used:
- `docker-compose.droplet.yml`
- `.env.droplet.example`
- `scripts/remote_deploy.sh`
- `infra/do/nginx/tcsaasbot.conf.template`

## Architecture

- `web`: Next.js dashboard on `127.0.0.1:3000`
- `api`: FastAPI backend on `127.0.0.1:9100`
- Managed PostgreSQL on DigitalOcean
- `redis`: Redis 7
- `nginx` on the host:
  - `/` -> dashboard
  - `/api/` -> backend

## 1. Prepare the Droplet

Use Ubuntu 24.04 and a DNS A record pointed to the Droplet IP.

Install Docker and the Compose plugin:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
newgrp docker
```

## 2. Copy the Repo and Create the Environment File

```bash
sudo mkdir -p /opt/tcsaasbot
sudo chown -R $USER:$USER /opt/tcsaasbot
git clone <your-repo-url> /opt/tcsaasbot
cd /opt/tcsaasbot
cp .env.droplet.example .env.droplet
```

Set at minimum:

```bash
APP_DOMAIN=chat.example.com
OPENAI_API_KEY=...
DATABASE_URL=postgresql+psycopg://doadmin:<password>@db-postgresql-chat-do-user-7825403-0.g.db.ondigitalocean.com:25060/defaultdb?sslmode=require
SECRET_KEY=<long-random-value>
AUTH_PASSWORD=<strong-password>
FRONTEND_URL=https://chat.example.com
CORS_ORIGINS=https://chat.example.com
```

`SECRET_KEY` and `AUTH_PASSWORD` must be changed in production or the backend will refuse to start.

## 3. Deploy

```bash
chmod +x scripts/remote_deploy.sh
./scripts/remote_deploy.sh
```

That script:
- builds and starts all containers
- installs/configures Nginx if needed
- routes `/` to the dashboard and `/api/` to the backend

## 4. Enable HTTPS

After DNS is resolving to the Droplet:

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d chat.example.com
```

## 5. Verify

```bash
curl http://127.0.0.1:9100/healthz
curl -I http://127.0.0.1:3000
curl -I http://chat.example.com
curl http://chat.example.com/healthz
docker compose -f docker-compose.droplet.yml --env-file .env.droplet ps
```

## GitHub Actions Deployment

If you want the existing workflow to deploy automatically, store these repository secrets:

- `DROPLET_HOST`
- `DROPLET_USER`
- `DROPLET_SSH_PASSWORD`
- `SSH_PORT`
- `APP_DOMAIN`
- `OPENAI_API_KEY`
- `GOOGLE_API_KEY`
- `DATABASE_URL`
- `REDIS_URL`
- `SECRET_KEY`
- `AUTH_PASSWORD`
- `FRONTEND_URL`
- `CORS_ORIGINS`

Then update `.github/workflows/deploy.yml` to write `/opt/tcsaasbot/.env.droplet` instead of `backend/.env`.
