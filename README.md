# AWS Kubernetes Platform

An end-to-end DevOps platform project: a FastAPI + PostgreSQL app, containerised with Docker, deployed to Kubernetes through GitHub Actions, on AWS infrastructure built with Terraform, with Prometheus and Grafana monitoring.

🚧 Work in progress

## Architecture

```mermaid
flowchart TB
  Dev[Codespaces devcontainer] -->|branch + pull request| GH[GitHub repo<br/>protected main]
  GH --> CI[GitHub Actions<br/>lint · 20 tests · build · Trivy scan]

  subgraph AWS[AWS eu-west-2]
    TF[Terraform modules] --> S3[(S3 remote state<br/>versioned · encrypted · locked)]
    TF --> VPC
    TF -.-> ECR[(ECR private registry)]

    subgraph VPC[VPC 10.0.0.0/16 · public subnet · security group]
      subgraph K3S[EC2 + k3s Kubernetes]
        APP[Uptime Monitor API<br/>FastAPI pods]
        CRON[Checker CronJob]
        DB[(PostgreSQL)]
        MON[Prometheus + Grafana]
      end
    end
  end

  CI -.->|push image| ECR
  CI -.->|terraform plan via OIDC| TF
  CI -.->|helm upgrade| K3S
  ECR -.->|pull image| K3S
  APP -.-> DB
  CRON -.-> DB
  MON -.->|scrape /metrics| APP

  classDef built fill:#d4edda,stroke:#2e7d32,color:#000
  classDef planned fill:#f5f5f5,stroke:#888,stroke-dasharray:5 5,color:#000
  class Dev,GH,CI,TF,S3 built
  class ECR,APP,CRON,DB,MON planned
  style VPC fill:#e8f5e9,stroke:#2e7d32,color:#000
  style K3S fill:#fafafa,stroke:#888,stroke-dasharray:5 5,color:#000
```

🟩 Green / solid = built · ⬜ Grey / dashed = planned

## Roadmap
- [x] Dev environment defined as code (devcontainer)
- [x] Phase 1: Linux and networking basics
- [x] Phase 2: FastAPI app + Docker
- [x] Phase 3: CI with GitHub Actions
- [ ] Phase 4: Terraform on AWS
- [ ] Phase 5: Kubernetes locally
- [ ] Phase 6: Kubernetes on AWS + automated deploys
- [ ] Phase 7: Monitoring and alerting
- [ ] Phase 8: Security, backups, disaster recovery
