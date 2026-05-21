#!/usr/bin/env bash
# Server setup for a fresh GCP e2-micro VM (Ubuntu 22.04 x86_64).
# Run on the VM after SSH-ing in.
#
# This script installs Docker + Compose plugin. GCP firewall rules
# (80/443) live outside the VM — manage them via `gcloud compute
# firewall-rules` (see scripts/gcp-bootstrap.md).
set -euo pipefail

echo "=== Updating system ==="
sudo apt-get update && sudo apt-get upgrade -y

echo "=== Installing Docker ==="
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Allow current user to run docker without sudo
sudo usermod -aG docker "$USER"

echo "=== Done ==="
echo "Log out and back in for docker group membership to take effect."
echo "Then clone the repo and run: ./scripts/deploy.sh"
