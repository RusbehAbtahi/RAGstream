# Mid_Requirment.md

## 0. Overall Goal

We want a reproducible way to run the RAGstream Streamlit app on AWS, behind a stable URL, so that:

* I develop and test locally as usual (WSL, Streamlit, agents, retrieval, reranker, etc.).
* When I commit and push to GitHub (under defined conditions), a new Docker image is built and pushed to ECR.
* When I start the EC2 instance, it automatically runs the latest image and exposes the same Streamlit UI on a public URL.
* EC2 is normally stopped (zero or minimal cost); I only start it when I want to show or test the app.

---

## 1. Local Baseline (already true, just documented)

Goal: Fix what “local truth” is for RAGstream so the deployment targets a stable entry point.

What this means

* Project root on WSL:  
  `/home/rusbeh_ab/project/RAGstream`
* Main app entry for UI:  
  `ragstream/app/ui_streamlit.py`
* Local dev command (inside venv):  
  `streamlit run ragstream/app/ui_streamlit.py`
* Python dependencies described in `requirements.txt` (the smaller, curated one, not the huge freeze file).

This step is just to state: “This is the code and entry point that AWS will run.”

---

## 2. Containerization Concept

Goal: Be clear how the app will run in a container before we write any Dockerfile.

What we want

* One Docker image that:
  * Installs `requirements.txt`
  * Copies the RAGstream repo into the image
  * Sets the working directory to the project root
  * Sets default command to:

    * `streamlit run ragstream/app/ui_streamlit.py --server.address 0.0.0.0 --server.port 8501`

* The container exposes port 8501 internally.
* Environment variables (OpenAI key, possibly model settings) are injected at runtime, not hard-coded into the image.

Implementation later

* Write a Dockerfile that does exactly the above.
* Test locally with `docker run -p 8501:8501 ...` once, to check container behaviour.

---

## 3. AWS Infrastructure Shape (EC2 + ECR, no fancy extras)

Goal: Minimal but realistic AWS setup that can host the container and pull updates.

Decisions

* Region: `eu-central-1`
* Container registry: Amazon ECR
* Compute: single EC2 instance (e.g. `t3.medium`) in a public subnet.
* No load balancer, no NAT gateway, no autoscaling (cost control).
* Security:
  * EC2 Security Group open for HTTP (port 80) and/or 8501 from the internet, or from a restricted IP range later.
  * EC2 has an instance role that can pull images from ECR.

What we will create later

* One ECR repository, e.g. `ragstream-web`.
* One EC2 instance with:
  * Docker installed.
  * A simple startup mechanism (user data script or systemd) that:
    * pulls `ragstream-web:latest` image from ECR
    * runs the container and maps port 8501 → 80 or 8501 on the instance.

---

## 4. Secrets and Configuration Strategy

Goal: Keep the OpenAI key and similar secrets out of the image and out of the Git repo.

Decisions

* OpenAI API key lives in AWS as a parameter or secret:
  * Either Systems Manager Parameter Store or Secrets Manager (one parameter is enough).
* The same value is also stored as a GitHub secret for CI only if needed (not required for v1 image build), but not baked into the image.
* EC2:
  * Reads the secret at startup (via instance role) and exports it as `OPENAI_API_KEY` before running the container.
  * Or passes it as an environment variable when starting `docker run`.

What we will do later

* Create one secret/parameter: `OPENAI_API_KEY`.
* Give the EC2 instance role permission to read it.
* In startup script, fetch the value and pass it to Docker.

---

## 5. IAM Model For CI/CD (Simple: IAM User + GitHub Secrets)

Goal: Allow GitHub Actions to push images to ECR without overcomplicating IAM.

Decisions

* Create a dedicated IAM user, e.g. `github-ragstream-ci`.
* Attach minimal permissions:
  * ECR: create repository, push images, list images.
  * Optionally SSM/Secrets read if needed in CI (not strictly necessary for v1).
* Generate access key + secret for this user.
* Store them as GitHub secrets in the RAGstream repo:
  * `AWS_ACCESS_KEY_ID`
  * `AWS_SECRET_ACCESS_KEY`
  * `AWS_REGION=eu-central-1`

Important:  
No OIDC in v1. Keep it simple and working. OIDC can be a future hardening step.

---

## 6. CI/CD Behaviour (GitHub Actions → ECR, decoupled from EC2)

Goal: Define exactly what the CI pipeline does and when it runs.

What the workflow should do

* Trigger conditions:
  * Not on every push to main.
  * Either:
    * manual (`workflow_dispatch`), or
    * when a tag like `deploy-*` is pushed, or
    * when specific paths change (e.g. `ragstream/**`, `Dockerfile`, `requirements.txt`) AND we decide that such a change is “deploy-worthy”.
* Steps:
  1. Checkout the repo.
  2. Log in to ECR using the GitHub secrets (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`).
  3. Build Docker image for RAGstream (using the Dockerfile from step 2).
  4. Tag image as `latest` (and optionally with commit SHA or tag).
  5. Push image to the ECR repo `ragstream-web`.

Key point

* CI works even when EC2 is stopped.  
  CI only builds and uploads images → ECR.  
  EC2 later pulls the latest image when it is started.

---

## 7. EC2 Runtime Behaviour (Manual start, automatic app)

Goal: When I manually start EC2, the latest app should come up without extra manual steps.

Target behaviour

* EC2 is normally in “stopped” state.
* When I need a demo:
  * I start EC2 via console/CLI.
  * Cloud-init/user-data or a systemd service executes:
    * `docker pull <account>.dkr.ecr.eu-central-1.amazonaws.com/ragstream-web:latest`
    * `docker run ...` exposing required port(s) and environment variable(s).
  * The Streamlit app is then reachable at:
    * `http://<EC2-public-IP>:8501` or via an Nginx/port 80 mapping.

When I am done

* I stop EC2 again.
* Billing for compute stops; ECR storage cost remains minimal (small image).

---

## 8. URL and Domain (Optional, later)

Goal: Optionally expose a nice human-readable URL instead of raw EC2 IP.

Basic version

* Use the EC2 public DNS name (e.g. `ec2-xx-yy-zz.eu-central-1.compute.amazonaws.com:8501`).

Later upgrade

* Buy a cheap domain (e.g. via Route 53 or another registrar).
* Create a DNS A or CNAME record pointing domain → EC2 public DNS.
* Optionally, front it with a basic reverse proxy (Nginx) and get HTTPS via Let’s Encrypt or ACM + Load Balancer (only if you really need HTTPS and are okay with extra AWS cost).

---

## 9. Data: Chroma DB And Logs

Goal: Decide what is in the image and what is not.

For now (v1)

* Include small, static Chroma DB(s) inside the image or as part of the repo under `data/chroma_db` if size is small.
* No persistent user memory/history on EC2. The service is “stateless” between runs.
* Logs are only for debugging; no long-term storage.

Later

* If you add dynamic memory or uploads, we can move Chroma and logs to:
  * An attached EBS volume, or
  * S3, or
  * A managed vector store (future decision).

---

## 10. Summary Of The Flow

1. Develop locally in WSL, run Streamlit as usual.
2. When a new version is “demo-ready”:
   * Commit and push to GitHub.
   * Trigger the GitHub Action (manually or via tag).
3. GitHub Action:
   * Builds Docker image and pushes to ECR as `ragstream-web:latest`.
4. When you want to show it:
   * Start EC2.
   * EC2 startup script pulls `latest` and runs the container with your OpenAI key from a secret.
   * You open the EC2 URL (or domain) in a browser and use RAGstream.
5. When finished:
   * Stop EC2.

This is the mid-level requirement and implementation map (v2, aligned with IAM user + conditional deploy triggers). You can now freeze it and later translate each step into concrete commands, YAML, and scripts.
