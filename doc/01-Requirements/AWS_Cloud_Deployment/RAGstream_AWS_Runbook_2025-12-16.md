RAGstream AWS deployment runbook (working notes)
Date: 2025-12-16
Owner: Rusbeh Abtahi
Scope: Local WSL2 -> Docker -> ECR -> EC2 (Ubuntu 24.04) + SSM Parameter Store (OpenAI key)

0) What this file is
This is a single “study file” that captures the commands we executed and the reasoning behind them, so you can reread and re-derive everything later.
I will keep extending this file as we progress (you can ask me any time to regenerate it with new steps).

1) Current architecture (high level)
- Dev machine:
  - Windows 11
  - WSL2 Ubuntu 24.04.3
  - Docker engine running in WSL2
  - You build and test the Streamlit app locally (container or venv)
- AWS:
  - ECR private repository: ragstream-web
  - EC2 Ubuntu 24.04 instance
  - EC2 instance role: ragstream-ec2-ecr-pull
  - SSM Parameter Store SecureString: /ragstream/prod/OPENAI_API_KEY
  - Domain in Route 53: rusbehabtahi.com (registered, DNS not yet configured to point to the EC2 app)

2) Deterministic naming patterns (so you can rebuild from scratch)
ECR registry URL pattern:
  <account-id>.dkr.ecr.<region>.amazonaws.com/<repository-name>:<tag>

Where:
- account-id: fixed for your AWS account (108782059508)
- dkr.ecr: fixed string for ECR Docker registry endpoints
- region: fixed for that registry (eu-central-1)
- repository-name: you choose when creating the ECR repo (ragstream-web)
- tag: you choose (latest, git-sha, etc.)

Your current image reference:
  108782059508.dkr.ecr.eu-central-1.amazonaws.com/ragstream-web:latest

3) Local image build (WSL2)
Goal:
- Produce a Docker image that runs Streamlit and your RAGstream code.
- Confirm it runs locally before involving AWS.

Typical build:
```bash
cd /home/rusbeh_ab/project/RAGstream
docker build -t ragstream-local:latest .
```

Typical run:
```bash
docker run --rm -p 8501:8501 -e OPENAI_API_KEY="$OPENAI_API_KEY" ragstream-local:latest
```

Why “-p 8501:8501” matters:
- Left side (host port): 8501 on your machine/WSL host
- Right side (container port): 8501 inside container where Streamlit listens
Docker publishes host:8501 and forwards traffic to container:8501.

Why Streamlit prints http://0.0.0.0:8501:
- 0.0.0.0 means “bind to all network interfaces” inside the container/host.
- It is not a browser address you should type.
For browser you typically use:
- http://127.0.0.1:8501
- or http://localhost:8501
- or your LAN IP (example: http://192.168.178.51:8501) if accessing from another device on the same LAN.

4) Tagging for ECR
Goal:
- Keep the same local image ID, but give it a second name that points to the ECR repository.

Command:
```bash
docker tag ragstream-local:latest 108782059508.dkr.ecr.eu-central-1.amazonaws.com/ragstream-web:latest
```

What this does:
- It does not copy image data.
- It creates an additional reference (“tag”) to the same local image layers, but under the ECR registry/repo name.

5) Authenticating Docker to ECR
Goal:
- Docker needs credentials to push/pull to a private ECR registry.
- ECR uses short-lived tokens (so you re-login when needed).

Command (token pipeline):
```bash
aws ecr get-login-password --region eu-central-1 --profile github-ragstream-ci   | docker login --username AWS --password-stdin 108782059508.dkr.ecr.eu-central-1.amazonaws.com
```

Macro explanation:
- Left side (aws ecr get-login-password ...) prints a temporary password token to stdout.
- The pipe “|” sends that printed token into docker login via stdin.
- docker login stores credentials in ~/.docker/config.json (warning is about “unencrypted at rest” on that file).

Micro explanation of the pipe:
- “cmdA | cmdB” means: take stdout of cmdA and connect it to stdin of cmdB.
- Here: token text never needs to be typed manually.

6) Push image to ECR
Command:
```bash
docker push 108782059508.dkr.ecr.eu-central-1.amazonaws.com/ragstream-web:latest
```

Why no “aws” prefix:
- The actual upload is a Docker registry protocol operation.
- After docker login, Docker already has a token for that registry endpoint, so it can push directly.

About image size and push time:
- Docker pushes layers.
- If only small files change and you build in a cache-friendly way, most layers will be reused and push is faster.
- If you rebuild a layer that includes “pip install …” or “COPY . …” of large directories, you’ll trigger more layer changes.

7) EC2 baseline (what we did)
Goal:
- Create one EC2 instance that can pull from ECR and run the container.
- Attach a role so EC2 can pull without storing long-term AWS keys on the instance.

EC2 keypair:
- You created a keypair (RAGstream_Key.pem).
- You placed it under ~/.ssh and fixed permissions:
```bash
chmod 600 ~/.ssh/RAGstream_Key.pem
```

SSH into EC2 (example):
```bash
ssh -i ~/.ssh/RAGstream_Key.pem ubuntu@<EC2-public-ip>
```

Docker install and access:
- Installed Docker and added ubuntu user to docker group:
```bash
sudo usermod -aG docker ubuntu
```
Then you re-logged in so group membership applies.

Sanity check:
```bash
docker ps
```

8) EC2 role and identity check
Goal:
- Confirm the instance role is active (no access keys stored on instance).

Command:
```bash
aws sts get-caller-identity --region eu-central-1
```

You saw an assumed-role ARN like:
arn:aws:sts::<account>:assumed-role/ragstream-ec2-ecr-pull/<instance-id>

This confirms:
- AWS CLI on the instance is using temporary credentials provided by the instance profile (IMDS).
- No static keys are required on that EC2.

9) OpenAI key via SSM Parameter Store
Goal:
- Never bake OpenAI keys into images.
- Fetch the key at runtime on EC2 with IAM permission.

You created:
- SecureString parameter: /ragstream/prod/OPENAI_API_KEY
- Using KMS key: alias/aws/ssm (AWS-managed key for SSM encryption)

SSM fetch command used inside scripts:
```bash
aws ssm get-parameter   --name "/ragstream/prod/OPENAI_API_KEY"   --with-decryption   --query 'Parameter.Value'   --output text   --region eu-central-1
```

What the flags do:
- --with-decryption: because SecureString is encrypted at rest; SSM returns plaintext only if IAM allows it
- --query 'Parameter.Value' --output text: extract only the value, not the whole JSON

10) EC2 runtime start script (ragstream-start)
Goal:
- One command that:
  - reads OPENAI_API_KEY from SSM
  - logs Docker into ECR
  - pulls latest image
  - replaces the running container (if exists)
  - runs Streamlit container on port 8501

You created:
/usr/local/bin/ragstream-start

Contents:
```bash
#!/usr/bin/env bash
set -euo pipefail

REGION="eu-central-1"
REGISTRY="108782059508.dkr.ecr.eu-central-1.amazonaws.com"
IMAGE="108782059508.dkr.ecr.eu-central-1.amazonaws.com/ragstream-web:latest"
SSM_PARAM="/ragstream/prod/OPENAI_API_KEY"
CONTAINER_NAME="ragstream"
PORT="8501"

OPENAI_API_KEY="$(aws ssm get-parameter   --name "$SSM_PARAM"   --with-decryption   --query 'Parameter.Value'   --output text   --region "$REGION")"

aws ecr get-login-password --region "$REGION"   | docker login --username AWS --password-stdin "$REGISTRY"

docker pull "$IMAGE"

if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  docker rm -f "$CONTAINER_NAME"
fi

docker run -d   --name "$CONTAINER_NAME"   --restart unless-stopped   -p "${PORT}:${PORT}"   -e OPENAI_API_KEY="$OPENAI_API_KEY"   "$IMAGE"
```

What “set -euo pipefail” means:
- -e: exit immediately if a command fails
- -u: treat unset variables as errors
- -o pipefail: if a pipeline fails in any part, return failure

11) Important clarification (boot vs manual script)
Right now:
- ragstream-start exists, and when you run it, it pulls and starts the container.
It does NOT automatically run on EC2 boot yet unless we connect it to a boot mechanism.

To make it run automatically on boot, we need one of:
- EC2 user-data (cloud-init) approach, or
- systemd service that runs ragstream-start at startup

We will implement exactly one of these next (most likely systemd service, because it is explicit, debuggable, and re-runnable).

12) What we have NOT implemented yet (next main tasks)
A) Boot automation:
- Ensure ragstream-start runs automatically every time the EC2 instance starts.

B) Domain -> IP mapping:
- Route 53 record that always points to the current EC2 public IP.
Because EC2 public IP changes after stop/start unless using Elastic IP.
Low-cost approach: update Route 53 A record at boot (dynamic DNS update).

C) CI/CD:
- GitHub Actions workflow that builds and pushes images to ECR automatically.

(You already have the manual build/push path working; we’ll turn it into CI.)

End of file (will be extended).
