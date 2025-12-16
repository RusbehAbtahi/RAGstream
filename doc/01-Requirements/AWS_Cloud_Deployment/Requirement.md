Requirements.md (updated, status as of 2025-12-16)

1. Goal

* You want a demo-grade, internet-accessible RAGstream Streamlit app that:

  * you can update by pushing code to GitHub
  * then a CI pipeline builds a Docker image and pushes to ECR
  * then the EC2 demo endpoint serves the newest version at a constant URL (domain-based), with minimal manual steps and minimal monthly cost. 

2. Non-goals for phase 1

* No multi-tenant production hardening.
* No full “self-service public users trigger EC2 start” in phase 1 (that is phase 2).
* No persistent user chat history / database expansion beyond the small ChromaDB folder you already have. 

3. Fixed constants (your real values)

* AWS account-id: 108782059508
* AWS region: eu-central-1
* ECR registry pattern: <account-id>.dkr.ecr.<region>.amazonaws.com
* Your ECR registry: 108782059508.dkr.ecr.eu-central-1.amazonaws.com
* ECR repository: ragstream-web
* Image reference (current): 108782059508.dkr.ecr.eu-central-1.amazonaws.com/ragstream-web:latest
* Streamlit port: 8501

4. Current status (DONE)
   4.1 Local (WSL)

* Docker image built locally and runs.
* AWS CLI installed in WSL.
* AWS profile configured for IAM user github-ragstream-ci.
* ECR login from WSL works (aws ecr get-login-password | docker login).
* Image push to ECR works.

4.2 AWS IAM / ECR

* ECR repository created: ragstream-web (private).
* IAM user created: github-ragstream-ci, used for CI/push-to-ECR only. 
* EC2 instance role created and attached: ragstream-ec2-ecr-pull.
* Verified from EC2: sts get-caller-identity shows assumed-role ragstream-ec2-ecr-pull (so the instance profile is correctly active).

4.3 AWS EC2

* EC2 is running Ubuntu 24.04.
* Docker installed, docker commands work.
* Image pulled from ECR successfully.
* Streamlit is reachable publicly via http://<public-ip>:8501 (security group allows inbound 8501).

4.4 Route 53 domain

* Domain registered in Route 53: rusbehabtahi.com
* Status currently “in progress”; email validation clicked; waiting for registrar completion (automated).

5. IAM model (FINAL for phase 1)
   5.1 github-ragstream-ci (CI only)
   Purpose: GitHub Actions (or your manual CLI) can push images to ECR.
   Permissions: ECR push (and only what’s required for that).
   Security intent: if these keys leak, attacker can push/pull images, but cannot create/stop EC2 or touch your admin resources. 

5.2 ragstream-ec2-ecr-pull (EC2 runtime role)
Purpose: EC2 pulls from ECR and (later) reads secrets + updates Route 53 record automatically at boot.
Permissions (needed soon):

* ECR pull permissions (already effectively working)
* SSM Parameter Store read (for OpenAI key) (to add)
* Route 53 change record sets (for dynamic DNS update) (to add)

6. Secrets and configuration (DECISION)
   6.1 OpenAI key handling

* Must NOT be baked into the Docker image.
* Must be injected at runtime on EC2.
* Phase 1 decision: store OPENAI_API_KEY in SSM Parameter Store as SecureString, and have the EC2 boot script read it and pass it to docker run as an env var. 

6.2 GitHub secrets

* AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are stored in GitHub Secrets for the CI workflow.
* AWS_REGION is not a secret (it can be a normal variable), but you may keep it in Secrets for convenience.

7. Deployment architecture (phase 1)
   7.1 Build + push path
   Developer laptop (WSL) or GitHub Actions
   -> docker build
   -> tag to ECR name
   -> docker push to ECR

7.2 Run path
EC2 instance (with instance profile role)
-> docker pull newest image
-> docker run -p 8501:8501 …image…
-> users access: http://<public-ip-or-domain>:8501

8. Constant URL (domain) decision for low monthly cost
   8.1 Constraint

* If you stop/start EC2, the public IPv4 changes (unless you pay to keep one reserved).
* You want a constant link.

8.2 Decision (recommended for your “few hours per month” usage)

* Do NOT use Elastic IP for phase 1.
* Use Route 53 dynamic update at instance boot:

  * at startup, EC2 fetches its current public IPv4 from instance metadata
  * EC2 updates Route 53 A record demo.rusbehabtahi.com -> <current-public-ip>
    This avoids paying for an always-reserved public IPv4 when the instance is stopped. AWS charges for public IPv4 addresses, and keeping one reserved while stopped can ruin your “almost-zero when off” goal.

9. Cost model (what you should expect)
   9.1 Domain registration

* Domain cost is billed yearly (you saw rusbehabtahi.com is 15 USD/year in the console).

9.2 Hosted zone

* Route 53 hosted zone has a monthly charge (commonly cited as about 0.50 USD/month for a standard hosted zone).

9.3 DNS queries

* You’ll pay per DNS query; for a personal demo with low traffic it’s usually tiny.

9.4 EC2 + public IPv4

* While EC2 is running, the public IPv4 usage is billed hourly (AWS publishes a per-hour public IPv4 price).
* Compute (instance) cost depends on instance type and runtime hours.

9.5 EBS volume

* EBS storage is billed per GB-month and continues even if the instance is stopped.

10. What remains (TODO), in strict order
    10.1 Domain/DNS

* Wait until rusbehabtahi.com registration completes.
* Confirm the Route 53 hosted zone exists and note:

  * Hosted Zone ID
  * Name servers (NS records)
* Create a record name we will standardize on:

  * demo.rusbehabtahi.com  -> A record to EC2 public IPv4 (updated dynamically)

10.2 Store OpenAI key in AWS (SSM Parameter Store)

* Create SecureString parameter (example name we will use consistently):

  * /ragstream/prod/OPENAI_API_KEY

10.3 Extend EC2 role permissions

* Add permission to ragstream-ec2-ecr-pull to:

  * ssm:GetParameter (for that one parameter path)
  * route53:ChangeResourceRecordSets (for only your hosted zone)

10.4 EC2 boot automation (eliminate manual steps)

* Add a user-data (cloud-init) script that on every boot:

  * installs docker (if needed)
  * logs into ECR
  * pulls latest image
  * reads OPENAI_API_KEY from SSM
  * starts the container
  * updates Route 53 record to current public IP

10.5 CI/CD (GitHub Actions)

* Add a workflow that on push to main:

  * builds image
  * tags as:

    * :latest
    * :<git-sha>
  * pushes to ECR
* No EC2 restart yet; your phase-1 operational model is:

  * start EC2 when you want to demo
  * boot script pulls latest automatically

11. Immediate next step (one step only)
    Tell me the current EC2 public IPv4 you want to use for the demo right now (you already did this before, but I need the current one after your latest start), and I’ll give you the single exact Route 53 DNS record you should create first (no placeholders).
