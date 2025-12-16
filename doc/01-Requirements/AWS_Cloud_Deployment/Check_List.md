# Check_List.md

Roozbeh Abtahi <roosbab@gmail.com>  
Fr., 5. Dez., 21:38 (vor 3 Tagen)  
an mich

RAGstream → EC2/Docker/GitHub Pipeline – Bootstrap Facts (Bootstrap Brain v2)  
Author: Rusbeh Abtahi  
Date: 2025-12-05

==================================================
0. Interaction rules for the assistant
==================================================

- The user is in charge. Do not push your own agenda.
- No hallucinations. If something is unclear, ask explicitly instead of assuming.
- No placeholders like "…" or "TBD" in code or config. Either give a concrete value or mark it clearly as "OPEN DECISION".
- Respect the user’s time: keep answers compact unless explicitly asked for deep detail.
- The goal of this file is to give you enough context so you can continue designing and implementing the EC2/Docker/GitHub pipeline for RAGstream without seeing the previous chat history.

==================================================
1. Local project and repository
==================================================

- Host machine: Windows 11.
- Linux environment: WSL2, Ubuntu-24.04.
- RAGstream repo root (WSL): /home/rusbeh_ab/project/RAGstream
- RAGstream repo root (Windows UNC): \\wsl.localhost\Ubuntu-24.04\home\rusbeh_ab\project\RAGstream
- GitHub repo: https://github.com/RusbehAbtahi/RAGstream
- Default branch: main (single branch workflow for now).

- Local virtual environment:
  - Path: /home/rusbeh_ab/venvs/ragstream
  - This venv is currently large (~2 GB) because it includes training-related libraries, but for deployment we will rely on a curated requirements.txt.

- Streamlit entrypoint:
  - From repo root: ragstream/app/ui_streamlit.py
  - Local run command (inside venv, from /home/rusbeh_ab/project/RAGstream):
    - streamlit run ragstream/app/ui_streamlit.py

- Project structure (top-level, relevant for this pipeline):
  - RAGstream/ (repo root)
    - ragstream/        → Python package (backend, orchestration, tools, etc.)
    - data/
      - chroma_db/      → vector store (small, ~7 MB) that may be needed on EC2
      - doc_raw/        → raw documents for ingestion (not performance-critical)
    - doc/              → Requirements, Architecture, UML, etc. (no runtime impact)
    - requirements.txt  → curated runtime dependencies for RAGstream (the “small” one)
    - requirements_large.txt or similar → pip freeze dump (for safety, not for deployment)

- The canonical runtime dependency list for deployment is requirements.txt (the smaller, hand-maintained one). The large frozen list is only for debugging and must not be used to build the Docker image.

==================================================
2. Target deployment architecture (high level)
==================================================

Goal: Run RAGstream + Streamlit on AWS so that:

- Local development stays on WSL with the existing venv and manual streamlit run.
- When a CI/CD workflow is explicitly triggered (manual or special tag), it builds a Docker image of the app and pushes it to ECR.
- An EC2 instance, when started, pulls the latest image from ECR and runs Streamlit.
- The Streamlit app is reachable via a stable URL:
  - Initially: EC2 public DNS (e.g. http://ec2-x-x-x-x.eu-central-1.compute.amazonaws.com:80 or 8501)
  - Later: optional custom domain via Route 53 or any domain registrar.

Behavior expected by the user:

- If the app works locally (e.g. new agent, retrieval, reranker, new GUI buttons),
  and the user commits and pushes to main,
  and then explicitly triggers a deployment workflow (for example via a tag or manual dispatch),
  then whenever EC2 is started, the same URL should serve the new version without extra manual deployment steps.
- EC2 is normally stopped (for cost reasons) and started only for demos / presentations.

==================================================
3. AWS environment and constraints
==================================================

- Region: eu-central-1 (Frankfurt).
- AWS account ID: 108782059508.

- IAM situation:
  - The main IAM user (the owner) currently has wide permissions (AdministratorAccess etc.).
  - For GitHub CI, the plan is:
    - Create a dedicated IAM user, for example: github-ragstream-ci
    - Give it minimal permissions only for CI:
      - ECR: create repository (once), describe repositories, push images, read images.
      - Optionally: SSM Parameter Store or Secrets Manager read rights if CI ever needs secrets (not required in v1).
    - Generate an access key + secret for github-ragstream-ci and store them as GitHub secrets.
    - EC2 control from GitHub is NOT required in v1; user starts/stops EC2 manually in the console. The container will pull the latest image on boot.

- EC2 instance:
  - Purpose: host the Dockerized RAGstream/Streamlit app.
  - Default state: stopped, only started for demos.
  - Planned instance type: t3.medium or similar (4 GB RAM) to handle:
    - Python runtime
    - Streamlit
    - ChromaDB
    - Reranker (eventually E5/EBERT via sentence-transformers; not heavy training, only inference).
  - Network:
    - Public subnet with public IPv4 address (no NAT Gateway).
    - Security group allows inbound HTTP (port 80 or 8501) from “0.0.0.0/0” for demo purposes.
    - Outbound internet access allowed (for OpenAI API calls, etc.).

- Domain:
  - Currently no custom domain.
  - Initial deployment uses raw EC2 public DNS.
  - Later, a domain can be attached (Route 53 or external registrar) and mapped to the EC2 (or to an Application Load Balancer if needed).
  - The user is aware a domain costs roughly a low two-digit Euro amount per year and wants to be warned before adding extra paid components.

- Costs awareness:
  - EC2: pay-per-hour; the user plans to run it only a few hours per month.
  - ECR: small image storage costs; acceptable.
  - Data transfer: low volume for demos.
  - GitHub Actions: free tier is sufficient for this project if pipelines are not abused.
  - The assistant must explicitly warn the user before suggesting any new resource that may incur non-trivial recurring cost (e.g. NAT Gateway, additional load balancers, extra domains).

==================================================
4. Secrets and security model
==================================================

- OpenAI key:
  - Currently stored locally in KEYS.txt and available in WSL as OPEN_AI_KEY=sk-... (user can export it as an environment variable).
  - Security requirement:
    - Never commit the OpenAI API key to Git.
    - Never bake the OpenAI API key into the Docker image.
  - Target approach:
    - Store the OpenAI API key in AWS Secrets Manager or SSM Parameter Store (SecureString).
    - On EC2 instance boot (or container start), inject OPENAI_API_KEY into the container environment from the secret / parameter.
    - For local development, continue using .env or simple exports (this is acceptable on the local machine).

- GitHub secrets:
  - The RAGstream repo currently has no secrets configured.
  - The other repo (Aistratus) already uses some GitHub secrets (AWS_GITHUB_ROLE etc.) but they are not used here.
  - For RAGstream we will add:
    - AWS_ACCESS_KEY_ID (for IAM user github-ragstream-ci).
    - AWS_SECRET_ACCESS_KEY (for IAM user github-ragstream-ci).
    - AWS_REGION=eu-central-1.
    - Possibly a secret name or ARN for the OpenAI key if the build process ever requires it (preferred is to read it only at runtime on EC2, not during build).

- Instance hardening:
  - EC2 will be in a public subnet but used only for short-lived demos.
  - The assistant should not suggest reckless configurations (like wide-open SSH with weak keys).
  - For a first version it is acceptable to:
    - Allow HTTP from anywhere (for demo).
    - Use SSH with key pair for admin-only access.

==================================================
5. CI/CD behaviour and desired pipeline
==================================================

High-level CI/CD path:

1) Local development:
   - User develops on WSL in /home/rusbeh_ab/project/RAGstream, using venv /home/rusbeh_ab/venvs/ragstream.
   - User runs:
     - streamlit run ragstream/app/ui_streamlit.py
   - User tests new agents, retrieval, reranker, GUI buttons locally.

2) Git commit and push:
   - User commits changes to main branch and pushes to GitHub.
   - This alone should NOT automatically trigger deployment.
   - Deployment only happens when a dedicated “deploy” workflow is triggered (for example: pushing a tag deploy-* or manual workflow_dispatch).

3) GitHub Actions:
   - Trigger: explicit deployment event, e.g.:
     - manual workflow_dispatch, or
     - a new tag with a pattern like deploy-*, or
     - another simple condition we define together.
   - Steps (simplified):
     - Check out repo.
     - Log in to ECR using AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_REGION stored as GitHub secrets (IAM user github-ragstream-ci).
     - Build Docker image for RAGstream using requirements.txt (not the large freeze).
     - Tag the image with something like: latest and git SHA.
     - Push image to ECR repository (e.g. ragstream-web).

4) EC2 runtime:
   - EC2 instance has Docker installed.
   - On instance boot (user starts it via console or script), a startup mechanism (e.g. systemd service or user-data script) performs:
     - docker pull <ECR repo>:latest
     - docker run (or docker compose up) with:
       - port mapping, e.g. host:80 -> container:8501
       - environment variables including OPENAI_API_KEY, etc.
       - working directory and volume if needed for chroma_db.
   - When EC2 is on:
     - The user accesses the app via:
       - http://<EC2-public-DNS>/  (if mapped to port 80), or
       - http://<EC2-public-DNS>:8501/

5) Software update:
   - When the user has a new “demo-ready” version:
     - Commit + push normally.
     - Then explicitly trigger the deploy workflow (tag/dispatch).
     - GitHub Action builds and pushes the new Docker image.
   - On the next EC2 restart (or manual docker pull + restart), the instance pulls the updated image.
   - Result: same URL, new functionality, no manual copying of code.

This design fulfils the user’s core requirement:
- “If it works locally and I push, then when EC2 is started (after I triggered a deploy), the same URL uses the new version.”

==================================================
6. Data files (Chroma DB, logs, statefulness)
==================================================

- Current plan:
  - For the first pipeline version, the app can be considered “stateless” on EC2 with respect to conversation history.
  - The only necessary runtime data are:
    - Model weights / embeddings loaded via Python packages.
    - ChromaDB index under data/chroma_db (small; can be included in the Docker image or mounted from an EBS volume).
  - For now, EC2 does not need to persist conversation logs or user-specific history; that can be added later.

- For a future, more advanced version:
  - Logs, embeddings, and conversation history might be stored in:
    - S3 buckets
    - An RDS instance
    - Or another managed database.
  - This is explicitly out of scope for the first iteration of the pipeline, but the assistant should be aware that future stateful extensions may come.

==================================================
7. Checklist for new chat (what is already decided)
==================================================

This is a quick checklist a new assistant instance should use as “facts”:

- Local:
  - Codebase lives in /home/rusbeh_ab/project/RAGstream (WSL).
  - Streamlit entrypoint: ragstream/app/ui_streamlit.py.
  - venv: /home/rusbeh_ab/venvs/ragstream.
  - requirements.txt is the canonical runtime dependency list for deployment.

- GitHub:
  - Repo: https://github.com/RusbehAbtahi/RAGstream
  - Branch: main.
  - CI/CD will be implemented via GitHub Actions.
  - Docker builds will happen in GitHub Actions, not on the user’s laptop in the final design (local Docker is available but not required for the pipeline).
  - Deployments must NOT run on every push; they are triggered only by explicit deploy events (manual or tag).

- AWS:
  - Region: eu-central-1.
  - Account ID: 108782059508.
  - Use ECR to store images for RAGstream.
  - Use EC2 (t3.medium or similar) in a public subnet with public IP for the app.
  - No NAT Gateway (to avoid monthly fixed cost).
  - Initial access via raw EC2 public DNS.
  - EC2 is mostly stopped; started manually by the user for demos.
  - Secrets (OpenAI key) must be stored in AWS Secrets Manager or SSM Parameter Store, not in code or image.
  - For GitHub → AWS, v1 uses a dedicated IAM user (github-ragstream-ci) with static keys stored as GitHub secrets. OIDC + role assumption is a possible future hardening step, not v1.

- Behaviour:
  - When a deploy workflow is triggered, GitHub Action builds and pushes a Docker image to ECR.
  - On EC2 boot (or container restart), the instance pulls the latest image and runs Streamlit.
  - When EC2 is running, the same URL serves the latest deployed version without manual copying of code.

==================================================
8. Open decisions that can be discussed with the new assistant
==================================================

These are intentionally left as open design choices that the new chat can help refine:

- Exact Dockerfile structure:
  - Base image choice (e.g. python:3.12-slim).
  - How to copy data/chroma_db into the image or attach as volume.
  - Whether to use multi-stage builds.

- Exact naming:
  - ECR repo name (e.g. ragstream-web vs ragstream-app).
  - IAM user name for GitHub (github-ragstream-ci is the current plan; can be adjusted).

- Secrets integration details:
  - Use AWS Systems Manager Parameter Store vs Secrets Manager.
  - How to wire secrets into Docker env vars on EC2 (user-data script, systemd, or other).

- EC2 bootstrap mechanism:
  - Use user-data only vs user-data + systemd unit.
  - Whether to use docker run directly or Docker Compose.

- Custom domain:
  - Whether to add a Route 53 hosted zone and map a domain later.
  - Whether to add a load balancer in front (not required for the first simple version).

This file should be given to any new assistant instance before continuing the design and implementation of the RAGstream EC2/Docker/GitHub pipeline, so that it knows the current facts, constraints, and goals.
