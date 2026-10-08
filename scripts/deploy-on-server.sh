#!/bin/bash
# Runs ON the EC2 server, as root, via SSM Run Command.
# Usage: deploy-on-server.sh <git-commit-sha>
set -euo pipefail

SHA="$1"
REGISTRY="099021515478.dkr.ecr.eu-west-2.amazonaws.com"
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
export HOME=/root
export PATH="$PATH:/usr/local/bin:/snap/bin"
CHART_DIR="$(cd "$(dirname "$0")/.." && pwd)/helm/uptime-monitor"

echo "== Refreshing ECR pull secret (ECR login tokens expire after 12 hours)"
kubectl -n uptime create secret docker-registry ecr-pull \
  --docker-server="$REGISTRY" --docker-username=AWS \
  --docker-password="$(aws ecr get-login-password --region eu-west-2)" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "== Deploying $SHA"
helm upgrade --install uptime "$CHART_DIR" -n uptime \
  -f "$CHART_DIR/values-aws.yaml" \
  --set image.tag="$SHA" \
  --atomic --timeout 5m

kubectl -n uptime get pods