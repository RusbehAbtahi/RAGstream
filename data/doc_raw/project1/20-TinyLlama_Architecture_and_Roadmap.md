```markdown
---
title: "TinyLlama_Architecture_and_Roadmap"
author: "Rusbeh Abtahi"
version: "1.0"
updated: "2025-06-11"
---

# TinyLlama · Requirements, Architecture, and Long-Term Roadmap  

This document unifies the **requirement list (17)**, the **high-level cloud blueprint (16)**, and the **forward-looking vision for GPTRusbeh / GPTRusbeh-X (14)**.  
Everything here is current and relevant; obsolete or superseded details from the older files have been omitted.

---

## 1 · MVP Requirements (Lambda-only Desktop Flow)

### 1.1 Infrastructure & IAM  
1. Provision S3 bucket `tinyllama-data-<account>` (versioning enabled) for prompt I/O and artifacts.  
2. Store `OPENAI_API_KEY` in AWS Secrets Manager under `tinyllama/openai`.  
3. Create IAM role **tinyllama-lambda-role** with:  
   - AWSLambdaBasicExecutionRole (managed)  
   - Inline policy: `s3:PutObject`, `s3:GetObject`, `secretsmanager:GetSecretValue` on the bucket and secret ARNs.  
4. Trust policy allows `lambda.amazonaws.com`.

### 1.2 Compute & API  
5. Package handler in `01_src/tinyllama/orchestration/lambda_router/handler.py` → `router.zip`.  
6. Deploy Lambda **tinyllama-router** (Python 3.12, 512 MB, 30 s timeout) with env vars: `DATA_BUCKET`, `OPENAI_SECRET`.  
7. Create HTTP API Gateway `/` POST route → Lambda proxy integration.  
8. Add `lambda:AddPermission` so API Gateway can invoke the function.

### 1.3 CI/CD  
9. CodeBuild role with:  
   - AWSCodeBuildDeveloperAccess  
   - Inline `codestar-connections:UseConnection` (GitHub)  
   - Inline `lambda:UpdateFunctionCode` on **tinyllama-router**.  
10. Buildspec: zip → `aws lambda update-function-code`.

### 1.4 Monitoring & Cost  
11. CloudWatch Logs enabled; optional budget alarm ≤ $5 / month.

### 1.5 Security & Compliance  
12. No public S3 ACLs; bucket private.  
13. Secrets fetched at runtime—never committed to Git.

*Acceptance:* `curl` POST returns Lambda echo; CodeBuild redeploy succeeds; cost ≤ $0.05 per build.

---

## 2 · Intermediate Requirements (Desktop GUI + GPU Inference)

> **Goal:** Local desktop client triggers on-demand GPU inference on a hibernated EC2, with Redis queue, cost safety, and IAM least-privilege.

### 2.1 API & Queue  
1. CloudFront (optional) ⇒ API Gateway (HTTP API, JWT via Cognito).  
2. Lambda **router-v2**: validates JWT, enqueues jobs in Redis, returns request-ID.

### 2.2 Redis  
3. ElastiCache Redis 6.2 (cluster-mode off) in private subnets; TTL 5 min; SG restricts to Lambda + EC2.

### 2.3 Inference EC2 (Hibernated GPU)  
4. Instance type `g4dn.xlarge` (fallback `g5.xlarge`); custom AMI baked via Image Builder.  
5. 100 GB gp3 EBS holds Docker layers + model weights; hibernate after idle.  
6. IAM profile **tinyllama-inference**: `s3:GetObject`, `ssm:*`, `cloudwatch:PutMetricData` (least privilege only).  
7. Lambda Router starts instance if stopped; cold wake target ≤ 60 s.  
8. vLLM served on localhost:8000; logs to CloudWatch.

### 2.4 CI/CD & Image Pipeline  
9. CodePipeline: Git ➜ CodeBuild (tests) ➜ Image Builder ➜ AMI snapshot ➜ manual approve ➜ deploy.

### 2.5 Ops & Cost  
10. All EC2 access via SSM Session Manager—SSH closed.  
11. CloudWatch dashboards: GPU util, queue depth, latency, cost alarms (€15 warn, €20 hard-stop).  
12. Hibernate timeout 15 min; auto-stop if idle 30 min.

---

## 3 · Final Architecture Requirements (Multi-User, Mobile-Ready)

> High-level only—details will be refined once Intermediate phase proves stable.

- API Gateway with custom domain + Cognito; mobile and web clients.  
- Multi-GPU pool with spot-fallback and autoscaling.  
- Canary deployments, blue/green testing, full IaC via Terraform.  
- Cost-governance dashboard (Grafana) and automated budget enforcement.  
- Continuous RL fine-tuning loop for personalized TinyLlama adapters (nightly QLoRA/DPO).  
- Guard-rails: PII scanner, hallucination validator, secure prompt logging.

---

## 4 · High-Level Cloud Blueprint (from original 16)

*Kept here because it clarifies the architectural “shape” that underpins Intermediate & Final phases.*

```

Mobile App → API Gateway → Lambda Router
↘
Redis Queue
↘
EC2 GPU Inference Node

```

- **Hibernate EC2**: on-demand only; resumes < 60 s; pays only EBS when idle.  
- **Custom AMI + EBS cache**: slashes boot time; stores model weights and Docker layers.  
- **SSM-only ops**: zero open ports; easier automation.  
- **Cost Guardrails**: CloudWatch alarms + Lambda auto-shutdown; IAM restricts resource scope.  

*(The mobile-app front-end is optional for Desktop-only deployments.)*

---

## 5 · Future Evolution — GPTRusbeh Core & GPTRusbeh-X (summary of 14)

1. **GPTRusbeh Core**  
   - Wrap TinyLlama inference behind a public or partner-facing API Gateway.  
   - Add OpenAI / third-party LLM fallback with cost-aware routing.  
   - Build live cost dashboard, prompt history, and semantic search memory.  
   - Goal: production-grade personal AI assistant with multi-model flexibility.

2. **GPTRusbeh-X** (long-term R&D)  
   - Autonomous agent layer (planner / critic) orchestrates tool use.  
   - Continuous RL fine-tuning pipeline (human ranking ➜ nightly DPO/QLoRA).  
   - Full infra-as-code (Pulumi/Terraform) and observability stack (Grafana, trace).  
   - Self-audit memory graph (Neo4j) for drift detection and compliance.  

> These visions guide design choices today (cost discipline, IAM strictness, modular routing) but **are not part of the current build scope**. Detailed specs remain in GitHub archive for future phases.

---

## 6 · Change-Log

- **2025-06-11** • Initial merge of 17, 16, and strategic excerpts of 14; obsolete details removed.

---

*End of TinyLlama_Architecture_and_Roadmap.md*
```
