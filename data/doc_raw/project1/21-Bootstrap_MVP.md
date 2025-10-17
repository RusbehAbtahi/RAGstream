# TinyLlama MVP – AWS Lambda Orchestration (Full Technical Bootstrap)

## 1. Project Overview

This document captures the entire process for building, deploying, and verifying the TinyLlama MVP orchestration on AWS using Lambda, S3, IAM, Secrets Manager, and CodeBuild (CI/CD), with all policies, scripts, and real troubleshooting included.

**Repo root:**  
C:\0000\Prompt_Engineering\Projects\GTPRusbeh\Aistratus  
**Git remote:**  
git@github.com:RusbehAbtahi/Aistratus.git  
**AWS region:**  
eu-central-1

---

## 2. Environment Setup

**2.1. Required Tools**
- Git (local + GitHub)
- AWS CLI (configured for your account/region)
- Bash shell (Git Bash on Windows or native Linux/Mac)
- Python 3.x (for local testing, not required for build)
- Obsidian or other markdown editor (for documentation)

**2.2. AWS Resources to be Created**
- S3 bucket (for data exchange)
- Secrets Manager secret (for OpenAI API key)
- IAM roles (for Lambda, CodeBuild, and deployment)
- Lambda function (router)
- API Gateway (HTTP API)
- CodeBuild project (CI/CD pipeline)
- Required trust and inline policies

---

## 3. Repository Structure

```
.
├── .buildspec.yml
├── .env
├── .gitignore
├── output.json
├── README.md
├── router.zip
├── 00_infra
│   ├── codebuild_trust_policy.json
│   ├── codepipeline_trust_policy.json
│   ├── lambda_inline_policy.json
│   ├── lambda_role.json
│   ├── lambda_trust_policy.json
├── 01_src
│   └── tinyllama/orchestration/lambda_router/handler.py
├── 04_scripts
│   ├── ci
│   │   ├── create_cicd_roles.sh
│   │   ├── create_iam.sh
│   │   ├── deploy_lambda.sh
│   └── local
│       ├── create_api.sh
│       ├── create_s3.sh
│       ├── create_secret.sh
│       ├── invoke_lambda.sh
├── 05_docs/...
├── build/router.zip
```

---

## 4. One-Time Infrastructure Bootstrapping

### 4.1. S3 Bucket Creation

```bash
bash 04_scripts/local/create_s3.sh
```
- Creates an S3 bucket, stores the bucket name in `.env`.

### 4.2. Secrets Manager (OpenAI Key)

```bash
bash 04_scripts/local/create_secret.sh
```
- Stores your OpenAI API key securely in AWS Secrets Manager.

### 4.3. IAM Lambda Role and Inline Policy

- **Trust policy:** `00_infra/lambda_trust_policy.json`
- **Role policy:** `00_infra/lambda_role.json`
- **Inline policy:** `00_infra/lambda_inline_policy.json`
- **Create/attach using:**

```bash
bash 04_scripts/ci/create_iam.sh
```

### 4.4. Lambda Handler

- Code in `01_src/tinyllama/orchestration/lambda_router/handler.py`.
- The handler uploads each input prompt to S3 and can verify access to the secret.

---

## 
## 5. Manual Lambda Deployment (local, before CI/CD)

### 5.1. Zipping and Deploying Lambda

```bash
bash 04_scripts/ci/deploy_lambda.sh
```
- Zips handler and dependencies, creates/updates Lambda function.

---

## 6. API Gateway HTTP API Setup

```bash
bash 04_scripts/local/create_api.sh
```
- Deploys an HTTP API Gateway that routes POST requests to your Lambda.
- Returns the API endpoint URL.

---

## 7. CI/CD Pipeline – CodeBuild

### 7.1. Trust Policy for CodeBuild Role

`00_infra/codebuild_trust_policy.json`

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "codebuild.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

### 7.2. IAM Policies for CodeBuild Role

- **AWS Managed:**  
  - `AWSCodeBuildDeveloperAccess`
- **Custom Inline (Critical):**
  - **Allow-CodeConnections-Use:**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "codestar-connections:UseConnection"
      ],
      "Resource": "arn:aws:codeconnections:eu-central-1:108782059508:connection/5b8cc5cc-922b-4125-8dd9-abe0bbc66cab"
    }
  ]
}
```
  - **Allow-UpdateFunctionCode:**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "lambda:UpdateFunctionCode",
      "Resource": "arn:aws:lambda:eu-central-1:108782059508:function:tinyllama-router"
    }
  ]
}
```

### 7.3. Creating the CodeBuild Role

```bash
bash 04_scripts/ci/create_cicd_roles.sh
```
- Idempotent: skips existing roles and attaches only missing policies.

### 7.4. Final, Minimal `.buildspec.yml`

```yaml
version: 0.2

phases:
  build:
    commands:
      - zip -r router.zip 01_src/tinyllama/orchestration/lambda_router
  post_build:
    commands:
      - aws lambda update-function-code --function-name tinyllama-router --zip-file fileb://router.zip

artifacts:
  files:
    - router.zip
```
- No Python install or extra steps.
- Keeps CI runs fast and cost at minimum.

### 7.5. GitHub Connection (CodeStar) Setup
- In AWS Console → CodeBuild, connect GitHub using CodeStar Connections.
- The IAM role above allows CodeBuild to use this connection.

### 7.6. Manual Build/Test
- Start a new build in CodeBuild.
- Confirm Lambda is updated and API Gateway endpoint still works.

---

## 8. Acceptance Checklist

- [x] S3 bucket exists and is accessible from Lambda.
- [x] Secret is stored and Lambda can read it.
- [x] Lambda role has correct trust and inline policies.
- [x] API Gateway routes requests to Lambda and returns a response.
- [x] CodeBuild can connect to GitHub, build, and deploy Lambda (see logs).
- [x] No unnecessary policies, no Python install in buildspec, no stray resources.
- [x] All scripts, policies, and handler are versioned and in repo.
- [x] MVP costs are controlled (each CodeBuild run: ~$0.025 for 5 minutes).

---

## 9. Troubleshooting & Lessons Learned

- **Missing permissions:** If `lambda:UpdateFunctionCode` fails, attach the custom inline policy to CodeBuild role.
- **Webhook creation fails:** Make sure the CodeBuild role allows `codestar-connections:UseConnection` for your CodeStar Connection ARN.
- **YAML file errors:** Double-check that `.buildspec.yml` is in repo root and matches above.
- **Python not needed:** Omitting Python runtime speeds up builds and cuts cost; keep the buildspec as minimal as possible.
- **Manual fixes:** If you hand-edit any policy or role in AWS Console, update your repo or this doc to match.
- **IAM role and trust policies must be correct and up-to-date.**

---

## 10. Repeatable Git Workflow

```bash
# (from project root)
git add .
git commit -m "Finalize MVP for TinyLlama Lambda orchestration"
git push origin main

# To tag and freeze MVP version
git tag mvp-v1
git push origin mvp-v1
```

---

## 11. Files & Artifacts – At a Glance

- **Main Scripts:**  
  - 04_scripts/local/create_s3.sh  
  - 04_scripts/local/create_secret.sh  
  - 04_scripts/ci/create_iam.sh  
  - 04_scripts/ci/create_cicd_roles.sh  
  - 04_scripts/ci/deploy_lambda.sh  
  - 04_scripts/local/create_api.sh

- **JSON Policies:**  
  - 00_infra/lambda_trust_policy.json  
  - 00_infra/lambda_role.json  
  - 00_infra/lambda_inline_policy.json  
  - 00_infra/codebuild_trust_policy.json

- **Handler:**  
  - 01_src/tinyllama/orchestration/lambda_router/handler.py

- **BuildSpec:**  
  - .buildspec.yml (see above for latest working version)

- **IAM Inline Policies (console):**  
  - Allow-CodeConnections-Use
  - Allow-UpdateFunctionCode

---

## 12. Next Steps (Post-MVP)

- Archive old markdowns and scripts, keep only latest verified versions.
- Increment architecture: Add EC2 (hibernated GPU) step next, using Terraform for infra-as-code.
- Review/trim docs: only keep what is necessary and up-to-date.

---

**MVP Complete.**  
This document is the authoritative record of the working TinyLlama Lambda orchestration MVP as implemented in June 2025.
