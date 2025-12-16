````md
# RAGstream Docker + ECR manual runbook (WSL Ubuntu 24.04.3)

This file documents the exact CLI commands we used and what each one does.
No secrets are written here.

## 0) Local context (what runs where)

- Windows browser connects to http://localhost:8501
- WSL2 forwards Windows localhost:8501 into Linux
- Docker maps Linux host port 8501 to container port 8501 (-p 8501:8501)
- Streamlit listens inside the container on 0.0.0.0:8501

Note:
- 0.0.0.0 is for a server bind (listen on all interfaces), not a browser URL.
- In browser use localhost or 127.0.0.1 or your LAN IP (e.g. 192.168.178.51).

## 1) Build the Docker image locally

Command:
```bash
cd /home/rusbeh_ab/project/RAGstream
docker build -t ragstream-local .
````

Meaning:

* Builds an image from Dockerfile in the current folder.
* Tags (names) the image as ragstream-local:latest.

## 2) Run the container locally and test Streamlit

Command:

```bash
docker run --rm -p 8501:8501 -e OPENAI_API_KEY="$OPENAI_API_KEY" ragstream-local
```

Meaning:

* --rm: delete the container when it stops (image stays).
* -p 8501:8501: map host port 8501 (WSL/Linux) to container port 8501.
* -e OPENAI_API_KEY=...: passes the environment variable into the container.
* ragstream-local: the image name to run.

Browser:

* [http://localhost:8501](http://localhost:8501)

## 3) Verify Linux / WSL version (diagnostics)

Command:

```bash
cat /etc/os-release
```

## 4) Install AWS CLI v2 on WSL Ubuntu 24.04 (official installer)

Command:

```bash
cd ~
sudo apt update
sudo apt install -y unzip
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
aws --version
```

Meaning:

* Installs AWS CLI v2 as a standalone tool (not tied to your Python venv).

## 5) Configure AWS CLI profile for the CI IAM user

Profile name used:

* github-ragstream-ci

Command:

```bash
aws configure --profile github-ragstream-ci
```

Prompts you for (do not paste secrets into this file):

* AWS Access Key ID: <your-access-key-id>
* AWS Secret Access Key: <your-secret-access-key>
* Default region name: eu-central-1
* Default output format: json

Verify identity:

```bash
aws sts get-caller-identity --profile github-ragstream-ci --region eu-central-1
```

## 6) Log Docker into ECR (token-based registry login)

ECR registry/repo pattern: <account-id>.dkr.ecr.<region>.amazonaws.com/<repository-name>:<tag>

Fixed parts:

* <account-id> fixed: 108782059508
* dkr.ecr fixed: Docker endpoint for ECR
* <region> fixed for this registry: eu-central-1

Chosen parts:

* <repository-name> chosen: ragstream-web
* <tag> chosen: latest

Docker registry host (no repo, no tag): <account-id>.dkr.ecr.<region>.amazonaws.com
= 108782059508.dkr.ecr.eu-central-1.amazonaws.com

Command:

```bash
aws ecr get-login-password --region eu-central-1 --profile github-ragstream-ci \
  | docker login --username AWS --password-stdin 108782059508.dkr.ecr.eu-central-1.amazonaws.com
```

Meaning:

* aws ecr get-login-password: AWS CLI requests a temporary registry login token from ECR.
* pipe (|): sends that token directly into docker login via stdin.
* docker login stores the token for that registry host in ~/.docker/config.json.

## 7) Tag the local image with the ECR repository URI

Command:

```bash
docker tag ragstream-local:latest 108782059508.dkr.ecr.eu-central-1.amazonaws.com/ragstream-web:latest
```

Meaning:

* No rebuild, no upload.
* Adds a second name pointing to the same local image ID.
* This name tells docker push which registry + repository to upload to.

Check local images (short output):

```bash
docker images | head
```

## 8) Push the image to ECR

Command:

```bash
docker push 108782059508.dkr.ecr.eu-central-1.amazonaws.com/ragstream-web:latest
```

Meaning:

* Uploads the image layers to ECR repository ragstream-web using the stored docker login token.
* This is the manual equivalent of what GitHub Actions will do later (build -> tag -> push).

## 9) Security notes (factual)

* AWS CLI credentials are stored in: ~/.aws/credentials (protected by Linux file permissions).
* Docker registry login token is stored in: ~/.docker/config.json (also protected by Linux file permissions).
* Check permissions:

```bash
ls -l ~/.aws/credentials ~/.docker/config.json
```

```

If you want, I can also add a second section to this same file later for the GitHub Actions steps (build/tag/push in YAML) and the EC2 pull/run steps (still one step at a time in the chat).
::contentReference[oaicite:0]{index=0}
```
