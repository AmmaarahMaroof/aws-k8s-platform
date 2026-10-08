#!/bin/bash
# Runs once, as root, on the instance's first boot.
# Output is logged to /var/log/cloud-init-output.log
set -euxo pipefail

# 1. k3s: lightweight Kubernetes (single node)
curl -sfL https://get.k3s.io | INSTALL_K3S_CHANNEL=stable sh -

# 2. Helm: to install our chart
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# 3. AWS CLI: to log in to ECR during deploys
snap install aws-cli --classic