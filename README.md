# AWS Kubernetes Platform

An end-to-end DevOps platform project: a FastAPI + PostgreSQL app, containerised with Docker, tested and scanned in GitHub Actions, packaged as a Helm chart, and deployed to Kubernetes on AWS infrastructure built with Terraform.

🚧 Work in progress: see the roadmap below.

## Architecture

```mermaid
flowchart LR
    dev["Developer<br/>GitHub Codespaces"] -->|"push / PR"| repo["GitHub repo<br/>protected main"]

    subgraph ci["CI on every pull request"]
        test["Lint + tests<br/>ruff, pytest"]
        scan["Docker build<br/>+ Trivy scan"]
        tfcheck["Terraform<br/>fmt + validate"]
        tfplan["Terraform plan"]
        helmlint["Helm lint<br/>+ template"]
    end
    repo --> test --> scan
    repo --> tfcheck --> tfplan
    repo --> helmlint

    subgraph cd["Deploy on merge to main"]
        push["Build + scan,<br/>push SHA-tagged image"]
        deploy["helm upgrade<br/>via SSM"]
    end
    repo -->|"merge"| push
    push -.-> deploy

    subgraph aws["AWS eu-west-2"]
        oidc["IAM plan role via OIDC<br/>read-only, no keys"]
        deployrole["IAM deploy role via OIDC<br/>main branch only"]
        state[("S3 state bucket<br/>versioned, locked")]
        ecr["ECR<br/>immutable tags, scan on push"]
        subgraph vpc["VPC 10.0.0.0/16"]
            ec2["EC2 t3.small + k3s<br/>SSM only, IMDSv2, encrypted"]
        end
    end
    tfplan -->|"OIDC token"| oidc
    oidc --> state
    push -->|"OIDC token"| deployrole
    push --> ecr
    ec2 -.->|"pull images"| ecr
    deploy -.-> ec2

    subgraph k8s["Kubernetes (minikube, local) - namespace uptime"]
        svcapi["Service: api"] --> api["Deployment: api<br/>2 replicas, probes,<br/>wait-for-db init"]
        cron["CronJob: checker<br/>every 5 min"]
        svcdb["Service: db"] --> pg[("StatefulSet: postgres<br/>+ PVC")]
        secret["Secrets<br/>created via CLI"]
        api --> svcdb
        cron --> svcdb
        secret -.-> api
        secret -.-> cron
    end
    dev -->|"minikube"| svcapi

    helm["Helm chart"]
    helm -->|"helm install / upgrade"| k8s

    mig["DB migrations Job"]:::planned
    obs["Prometheus + Grafana"]:::planned
    prod["prod environment"]:::planned
    mig -.-> pg
    obs -.->|"/metrics"| api
    prod -.-> aws

    classDef planned stroke-dasharray: 5 5,fill:#f5f5f5,color:#666
    classDef built fill:#e6f4ea,stroke:#34a853,color:#1e4620
    class dev,repo,test,scan,tfcheck,tfplan,helmlint,push,deploy,oidc,deployrole,state,ecr,ec2,svcapi,api,cron,svcdb,pg,secret,helm built
```

🟩 Green = built · ⬜ Grey dashed = planned

## Roadmap
- [x] Dev environment defined as code (devcontainer)
- [x] Phase 1: Linux and networking basics
- [x] Phase 2: FastAPI app + Docker
- [x] Phase 3: CI with GitHub Actions
- [x] Phase 4: Terraform on AWS
- [x] Phase 5: Kubernetes locally (manifests, break/fix, Helm chart)
- [ ] Phase 6: Kubernetes on AWS + automated deploys
  - [x] k3s bootstrapped on EC2 by Terraform `user_data`
  - [x] Merges to main push scanned, SHA-tagged images to ECR
  - [ ] Auto-deploy to k3s with Helm via SSM
- [ ] Phase 7: Monitoring and alerting
- [ ] Phase 8: Security, backups, disaster recovery
- [ ] Phase 9: Polish (runbook, lessons learned)

## Docs
- [How the app works](docs/APP.md)
- [Security decisions and vulnerability triage](docs/SECURITY.md)
- [Troubleshooting log: real issues and how they were fixed](docs/TROUBLESHOOTING.md)