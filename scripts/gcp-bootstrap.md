# Bootstrapping a fresh GCP VM for Telegram Message Migrator

These commands provision a GCP e2-micro instance that fits in the Free Tier
(in `us-west1`, `us-central1`, or `us-east1`). Run them locally from a
machine with `gcloud` authenticated.

> The hosted instance at <https://tgmigrate.com> currently runs on
> `homelab` / `us-west1-b`. Replace names below for a fresh deploy.

## 1. Create the VM

```bash
gcloud compute instances create homelab \
    --zone=us-west1-b \
    --machine-type=e2-micro \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --boot-disk-size=30GB \
    --boot-disk-type=pd-standard \
    --tags=http-server,https-server
```

## 2. Open ports 80 and 443

The `default-allow-ssh` rule (port 22) is created automatically. Add:

```bash
gcloud compute firewall-rules create allow-http \
    --network=default \
    --allow=tcp:80,tcp:443 \
    --source-ranges=0.0.0.0/0 \
    --target-tags=http-server,https-server
```

## 3. SSH and provision

```bash
gcloud compute ssh homelab --zone=us-west1-b
```

Then on the VM:

```bash
git clone https://github.com/bolin8017/telegram-message-migrator.git
cd telegram-message-migrator
bash scripts/server-setup.sh
# Log out, log back in for the docker group.

cp .env.example .env
# Edit .env — set TELEGRAM_API_ID/HASH (single-user) or SERVER_SECRET
# (multi-user), DOMAIN=tgmigrate.com, CORS_ORIGINS=https://tgmigrate.com.
./scripts/deploy.sh
```

## 4. Cloudflare DNS

In the Cloudflare dashboard for the zone:

1. Create an `A` record: `tgmigrate.com → <VM external IP>`.
2. Set proxy status to **Proxied** (orange cloud).
3. SSL/TLS encryption mode: **Full** (Caddy issues Let's Encrypt origin certs).

The VM's external IP can be found with:

```bash
gcloud compute instances describe homelab --zone=us-west1-b \
    --format='value(networkInterfaces[0].accessConfigs[0].natIP)'
```

## 5. Verify

```bash
curl -sf https://tgmigrate.com/health
# {"status":"ok"}
```
