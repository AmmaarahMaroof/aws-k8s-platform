# AWS Kubernetes Platform

An end-to-end DevOps platform project: a FastAPI + PostgreSQL app, containerised with Docker, deployed to Kubernetes through GitHub Actions, on AWS infrastructure built with Terraform, with Prometheus and Grafana monitoring.

🚧 Work in progress

## Architecture

```mermaid
flowchart LR
    dev["Developer<br/>GitHub Codespaces"] -->|"push / PR"| repo["GitHub repo<br/>protected main"]

    subgraph ci["GitHub Actions CI"]
        test["Lint + tests<br/>ruff, pytest"]
        scan["Docker build<br/>+ Trivy scan"]
        tfcheck["Terraform<br/>fmt + validate"]
        tfplan["Terraform plan"]
    end
    repo --> test --> scan
    repo --> tfcheck --> tfplan

    subgraph aws["AWS eu-west-2"]
        oidc["IAM role via OIDC<br/>read-only, no keys"]
        state[("S3 state bucket<br/>versioned, locked")]
        ecr["ECR<br/>immutable tags, scan on push"]
        subgraph vpc["VPC 10.0.0.0/16"]
            ec2["EC2 t3.small<br/>SSM only, IMDSv2, encrypted"]
        end
    end
    tfplan -->|"OIDC token"| oidc
    oidc --> state
    ec2 -.->|"pull images"| ecr

    subgraph k8s["Kubernetes - namespace uptime"]
        svcapi["Service: api"] --> api["Deployment: api<br/>2 replicas, probes"]
        cron["CronJob: checker<br/>every 5 min"]
        svcdb["Service: db"] --> pg[("StatefulSet: postgres<br/>+ PVC")]
        secret["Secrets<br/>created via CLI"]
        api --> svcdb
        cron --> svcdb
        secret -.-> api
        secret -.-> cron
    end
    dev -->|"minikube"| svcapi

    helm["Helm chart"]:::planned
    mig["DB migrations Job"]:::planned
    deploy["CI deploy to cluster<br/>on EC2 from ECR"]:::planned
    obs["Prometheus + Grafana"]:::planned
    prod["prod environment"]:::planned
    helm -.-> k8s
    mig -.-> pg
    deploy -.-> ec2
    obs -.->|"/metrics"| api
    prod -.-> aws

    classDef planned stroke-dasharray: 5 5,fill:#f5f5f5,color:#666
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
