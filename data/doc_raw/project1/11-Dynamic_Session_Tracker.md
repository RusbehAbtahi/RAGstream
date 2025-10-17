---
title: "11-Dynamic_Session_Tracker"
author: "Rusbeh Abtahi"
version: "2.5"
updated: "2025-07-24"
tags: [prompt-engineering, aws, session-log, dynamic-tracking, capstone]
---

## Latest Progress & Ticket Integration (July 2025)

### **Recently Closed Tickets**

#### LAM-001: Lambda Router Deployment & Integration (**Closed 23.07.2025**)
- Deployed TinyLlama Lambda Router via Terraform.
- Integrated JWT authentication and JSON schema validation (using shared `verify_jwt()` and Pydantic).
- Automated CI/CD (GitHub Actions) with id-token trust and region export.
- Major blockers resolved:
  - `/ping` route conflict: switched to `/health` for health checks.
  - Fixed Lambda code redeploys by using `source_code_hash`.
  - IAM permission debugging for just-in-time access.
- Final lessons:
  - Never use AWS-reserved `/ping` in API Gateway.
  - Always sync environment variables between CI and local.
  - Use least-privilege IAM roles.
  - Use `source_code_hash` for all Lambda deployments.

#### API-002: JWT Authorizer & /infer Route (**Closed 26.06.2025**)
- Full JWT-based authorization for `/infer` endpoint.
- All code dependencies locked; CI and local now deterministic.
- `.env.dev` enables seamless local development.

#### Infra-001: Networking Baseline (**Closed 01.07.2025**)
- S3 bucket and DynamoDB for Terraform state.
- Custom VPC, public/private subnets, IGW, and NAT-GW.
- Routing fully automated.

#### SSM Registry v2 (**Closed 08.07.2025**)
- All environment-specific resource IDs are written/read from SSM Parameter Store.
- Helper (`tinyllama/utils/ssm.py`) provides runtime lookup.
- IAM policies restrict SSM access by path.

---

### **Checklist & Lessons Learned**

- [x] Lambda Router integration completed, fully validated.
- [x] JWT & schema validation working for all test paths.
- [x] CI/CD, environment variable sync, and IAM permissions fully debugged.
- [x] Major blockers (e.g., `/ping` route) resolved via clear AWS best practices.
- [x] All future stack IDs/ARNs now managed in SSM for full automation and safety.

---

## **Capstone Roadmap (Weeks 3–8: In Progress / Next)**

- EC2 Automation & Network Prep
- Multi-Agent AWS Architecture
- Dynamic Prompt Routing
- GUI & User Experience
- Security, Monitoring, Governance
- Testing & CI/CD
- Final Integration

---

**Note:**  
Lambda MVP, API JWT Auth, and core infrastructure are closed and validated.  
All new technical work (EC2, Multi-Agent, GUI, SQS) will be tracked in new phase logs.

---
date: 2025-07-24
update: "All Lambda/API/Infra/SSM tickets merged and validated; SQS phase next."
