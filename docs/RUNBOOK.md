name: Deploy

on:
  push:
    branches: [main]
    paths-ignore:          # changes that can't affect the running app don't deploy
      - "docs/**"
      - "infra/**"
      - "monitoring/**"
      - "README.md"
  workflow_dispatch:       # "Run workflow" button: redeploy what's on main

permissions:
  id-token: write   # lets the job get an OIDC token for AWS
  contents: read

concurrency:
  group: deploy
  cancel-in-progress: false   # never run two deploys at once; queue them

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Sign in to AWS via OIDC
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::099021515478:role/github-actions-deploy
          aws-region: eu-west-2

      - name: Log in to ECR
        id: ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Work out image name
        id: meta
        run: echo "image=${{ steps.ecr.outputs.registry }}/uptime-monitor:${{ github.sha }}" >> "$GITHUB_OUTPUT"

      # Tags are immutable, so if this commit's image already exists, reuse it.
      # This makes "Run workflow" a true redeploy (DR finding #22).
      - name: Check if this commit's image already exists
        id: exists
        run: |
          if aws ecr batch-get-image --repository-name uptime-monitor \
               --image-ids imageTag=${{ github.sha }} \
               --query 'images[0].imageId.imageTag' --output text | grep -q "${{ github.sha }}"; then
            echo "skip=true" >> "$GITHUB_OUTPUT"
            echo "Image already in ECR, skipping build"
          else
            echo "skip=false" >> "$GITHUB_OUTPUT"
          fi

      - name: Build
        if: steps.exists.outputs.skip != 'true'
        run: docker build --provenance=false -t "${{ steps.meta.outputs.image }}" .

      - name: Scan before pushing
        if: steps.exists.outputs.skip != 'true'
        run: >
          docker run --rm -v /var/run/docker.sock:/var/run/docker.sock
          aquasec/trivy:latest image --exit-code 1 --severity CRITICAL --ignore-unfixed
          "${{ steps.meta.outputs.image }}"

      - name: Push
        if: steps.exists.outputs.skip != 'true'
        run: docker push "${{ steps.meta.outputs.image }}"

  deploy:
    needs: build-and-push
    runs-on: ubuntu-latest
    steps:
      - name: Sign in to AWS via OIDC
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::099021515478:role/github-actions-deploy
          aws-region: eu-west-2

      - name: Find the running server
        id: server
        run: |
          ID=$(aws ec2 describe-instances \
            --filters "Name=tag:Name,Values=uptime-dev-server" "Name=instance-state-name,Values=running" \
            --query "Reservations[].Instances[].InstanceId" --output text)
          if [ -z "$ID" ]; then
            echo "::error::No running server. Start it, then use 'Re-run jobs' or 'Run workflow'."
            exit 1
          fi
          echo "id=$ID" >> "$GITHUB_OUTPUT"

      - name: Deploy via SSM
        env:
          ID: ${{ steps.server.outputs.id }}
          SHA: ${{ github.sha }}
          REPO: ${{ github.repository }}
        run: |
          jq -n --arg sha "$SHA" --arg repo "$REPO" '{commands: [
            "set -e",
            "rm -rf /tmp/deploy && mkdir -p /tmp/deploy",
            "curl -sfL https://github.com/\($repo)/archive/\($sha).tar.gz | tar xz -C /tmp/deploy --strip-components=1",
            "bash /tmp/deploy/scripts/deploy-on-server.sh \($sha)"
          ]}' > params.json

          CMD_ID=$(aws ssm send-command --instance-ids "$ID" \
            --document-name AWS-RunShellScript --comment "deploy $SHA" \
            --parameters file://params.json --query Command.CommandId --output text)

          # Wait up to 6 minutes for the command to finish
          for i in $(seq 1 72); do
            STATUS=$(aws ssm get-command-invocation --command-id "$CMD_ID" --instance-id "$ID" \
              --query Status --output text 2>/dev/null || echo Pending)
            case "$STATUS" in Pending|InProgress|Delayed) sleep 5 ;; *) break ;; esac
          done

          echo "== Output from the server"
          aws ssm get-command-invocation --command-id "$CMD_ID" --instance-id "$ID" \
            --query "[StandardOutputContent, StandardErrorContent]" --output text
          echo "== Status: $STATUS"
          [ "$STATUS" = "Success" ]