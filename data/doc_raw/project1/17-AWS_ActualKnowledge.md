---
title: "AWS Actual Knowledge"
author: "Rusbeh Abtahi"
version: "2025-06-12"
---

# AWS Actual Knowledge

## What I’ve Done

- **End-to-End AWS MVP Orchestration**  
  Managed the full lifecycle of a real AWS project (“Bootstrap_MVP”), executing, debugging, and supervising all steps for a cloud-native LLM pipeline.  
  Designed, launched, and tested each component in context: Lambda, S3, IAM, ECR, EC2, CodeBuild, Secrets Manager, CloudWatch, and API Gateway.

- **Lambda, Docker, and ECR Integration**  
  Deployed Dockerized Python scripts via Elastic Container Registry (ECR) into AWS Lambda.  
  Verified container packaging, image push, permission setup, and Lambda invocation using CLI and console.

- **S3 Bucket Management and Secrets Handling**  
  Created, versioned, and managed S3 buckets for data storage.  
  Used AWS Secrets Manager for securely storing and referencing OpenAI API keys and service secrets; referenced these in Lambda and scripts.

- **IAM Policy Engineering (Hands-On, Meta, Debugging)**  
  Designed, tested, and debugged IAM roles, trust policies, and permission boundaries for Lambda, EC2, S3, CodeBuild, and Secrets Manager.  
  Iteratively wrote and refined custom inline policies, resolving permission errors through interactive troubleshooting.  
  Applied the official AWS IAM study roadmap (first three chapters), using both console and JSON editing, and implemented policies generated through a custom Python GUI.

- **Automated EC2 Lifecycle & Cost Controls**  
  Designed and ran automated Python scripts (with boto3) for EC2 lifecycle: launching, configuring, SSH key management, security group setup, public IP retrieval, and resource teardown (EBS, key pairs, security groups).  
  Built-in safety to terminate resources and clean up to avoid unwanted costs.  
  Managed basic GPU quotas by requesting increased quotas from AWS; however, detailed GPU instance selection criteria and advanced GPU workload optimization remain future learning targets.

- **CI/CD with CodeBuild (GitHub Integration)**  
  Set up and executed AWS CodeBuild projects for automated packaging and deployment.  
  Connected CodeBuild with GitHub (via CodeStar), wrote and tested `buildspec.yml`, and handled build artefacts for Lambda deployment.  
  Manually triggered pipelines, observed logs via CloudWatch, and validated build outputs.

- **API Gateway & Lambda Routing**  
  Provisioned HTTP API Gateway endpoints, wired Lambda integrations, and performed end-to-end tests (via `curl` and AWS CLI).  
  Managed route creation, deployment stages, and access permissions.

- **Cost Management and Budget Alarms**  
  Set up AWS Budgets with cost alerts and optionally configured CloudWatch metric alarms for error/failure detection.  
  Actively monitored usage to remain within Free Tier and budgeted limits.

- **Meta-Learning & Self-Documentation**  
  Authored detailed architectural and causality mapping files (“IAM Architectural Roadmap”, “Command Causality Table”, “ec2_launcher_audit”), establishing clarity for each step, command, and their IAM implications.  
  Regularly leveraged explicit documentation such as "IAM Architectural Roadmap", "Command Causality Table", and "EC2 Launcher Audit" to guide and validate operational steps, significantly enhancing structured learning and operational transparency.  
  Integrated high-level meta-learning from official docs and hands-on errors to build a personal knowledge framework.

- **Prompt Engineering Tools in AWS Context**  
  Built and ran prompt-generation tools (Python GUI for IAM policy JSON), directly connecting LLM knowledge to AWS permissions design.

- **Guidance, LMQL, and PromptML Meta-Analysis**  
  Studied, compared, and understood the role of Guidance, LMQL, and PromptML in prompt orchestration—recognizing how Python-based DSLs can drive real infrastructure automation in AWS.

- **Automation via CLI/scripts**  
  Executed, debugged, and adapted Python and shell scripts for automation of AWS resource creation, orchestration, and teardown.  
  While many initial scripts and Python codes were co-generated with AI support (ChatGPT), all were supervised, tested, debugged, and fully understood by myself—aligning with modern AI-assisted development practices.

---

## What I’ve Learned

- **IAM Architecture and Security Principles**  
  Gained a working, practical understanding of IAM users, roles, trust policies, permission policies, boundaries, and temporary credentials.  
  Can explain how Lambda, EC2, and CodeBuild roles differ and interconnect, and how least-privilege is enforced in real projects.

- **Cloud-Native Pipeline Orchestration**  
  Understand the full data and code flow: source code → build pipeline → Docker image → ECR → Lambda/EC2 → output to S3/API Gateway.  
  Experienced the real-world challenges of permission boundaries, function timeouts, cost control, and debugging distributed failures.

- **Service Interdependency & Debugging**  
  Developed the ability to trace and resolve service dependencies and permission errors—e.g., understanding why a Lambda cannot access a secret, or CodeBuild cannot update Lambda code.  
  Learned to diagnose errors using both CLI and Console logs, with a “debug-and-correct” workflow.

- **Automation and Clean-Up Discipline**  
  Automated cloud resource management (EC2, S3, IAM, Lambda) with teardown scripts and checks for idempotency.  
  Understood the importance of cleaning up unused resources to prevent unnecessary costs.

- **CI/CD Fundamentals (AWS Style)**  
  Learned the real mechanics of AWS-native build and deploy pipelines, GitHub connections, and artifact management for both Lambda and EC2 deployments.

- **Cost Control and Cloud Billing Awareness**  
  Internalized free tier boundaries, quotas, and the necessity of budget alerts in all non-hobby cloud work.

- **Meta-Learning as Operational Skill**  
  Learned to integrate ongoing self-study (official AWS docs, architectural roadmaps, session audits) directly into operational workflows—bridging “book knowledge” and practical deployment.  
  Regularly used Command Causality Table, IAM Architectural Roadmap, and EC2 Launcher Audit to structure, plan, and validate all AWS activities.

---

## Current Skill Level

| Area                               | Level                    | Notes                                                                              |
|-------------------------------------|--------------------------|------------------------------------------------------------------------------------|
| IAM roles, trust, and permission    | Intermediate             | Designed, deployed, debugged; 1:1 mapping between theory and practice               |
| Lambda, ECR, S3, Secrets Manager    | Intermediate             | End-to-end orchestration, Docker image flow, secret use, and output validation      |
| EC2 automation & cost management    | Intermediate             | Automated via Python/boto3, with full resource cleanup and safety checks            |
| CodeBuild, CI/CD                   | Entry–Intermediate       | Set up projects, managed build artifacts, manual triggers, basic GitHub integration |
| API Gateway                        | Entry–Intermediate       | Created endpoints, routed Lambda, and tested full flows                             |
| Budgeting & cost alerts             | Entry–Intermediate       | Created and managed budget alarms, tracked usage                                    |
| Guidance/PromptML/LMQL meta-use     | Conceptual/Beginner      | Meta-learning and architectural awareness, not deep deployment                      |
| Terraform/CDK                       | Conceptual only          | Meta-learning only; no live deployment                                              |
| Deep VPC/KMS/networking             | Not practiced yet        | Currently default configs only; advanced customization planned                      |
| Automation via CLI/scripts          | Intermediate             | Python/sh code executed, debugged, and adapted; AI-assisted scripting role clarified|

---

## Next Steps

1. **Deeper CI/CD Automation**  
   Fully automate CodeBuild–GitHub pipelines (triggered on push, not just manual); extend to automated test/deploy flows.

2. **Finish IAM Deep Dive**  
   Continue the official IAM study plan (beyond first 30 pages), including Access Analyzer, ABAC, permission boundaries, and advanced trust policy scenarios.

3. **Explore Advanced Infrastructure as Code**  
   Deploy at least one real-world stack with AWS CDK or Terraform, to cement IaC workflows and reusable architecture.

4. **Productionize Security Practices**  
   Implement MFA, least-privilege, and resource tagging standards across all projects; practice with Access Analyzer and security auditing tools.

5. **Move to Multi-Region & Advanced Networking**  
   Experiment with VPC customization, subnetting, and (optionally) cross-region replication or multi-region architectures.

6. **Integrate LLM-Based Automation**  
   Build a more robust Python toolchain for automatic IAM policy generation, cloud resource setup, and “infrastructure by prompt.”

---

*This document reflects only proven, hands-on AWS skills as of June 2025. All claims are backed by session logs, scripts, architectural files, and live deployments. No knowledge is claimed unless directly practiced or implemented.*
