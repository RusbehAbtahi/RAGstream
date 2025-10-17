
 # 🦙 TL-FIF v1.0 — Expanded Requirement List (RQL 1-Detail, PART 1/3)

 ## 1️⃣ Desktop GUI — Python Tkinter (cross-platform)

 ### 1.1 Visible Widgets & Behaviour

 | ID      | Widget          | Description                                                                                 | UX Purpose/Notes                                            |
 |---------|-----------------|---------------------------------------------------------------------------------------------|-------------------------------------------------------------|
 | 1.1.1   | **PromptBox**   | Multiline `tk.Text` box (5 lines). `Ctrl+Enter` triggers send.                              | Allows long prompts, code blocks; intuitive for power users. |
 | 1.1.2   | **SendBtn**     | Green `ttk.Button`. Disabled while sending; spinner overlay during inference call.           | Prevents double submission, shows progress.                 |
 | 1.1.3   | **StopGpuBtn**  | Red `ttk.Button`. Calls `awsctl.stop_gpu()` (triggers EC2 stop via API).                    | Gives user hard “kill switch” for cost control.             |
 | 1.1.4   | **IdleTimeout** | `ttk.Spinbox` (1–30 min, default 5). Value saved to `~/.tl-fif.ini`.                        | User can set auto-stop idle time per session.               |
 | 1.1.5   | **CostLabel**   | `tk.Label` polling every 30s. Displays AWS cost via CloudWatch custom metric.                | Live cost transparency; no surprises.                       |
 | 1.1.6   | **OutputPane**  | Read-only `tk.ScrolledText`. Renders model reply as plain text + latency/time stamp.         | Full conversation & result history visible.                 |

 ### 1.2 Security & Auth Flow
 - On first launch, the GUI opens Cognito-hosted login in your browser for secure AWS auth.
 - After login, an ID token is received via localhost callback and stored in memory (not on disk).
 - Every API call adds an `Authorization: Bearer <id_token>` header.
 - **Reason:** Your desktop app never stores long-lived AWS keys, making it more secure and stateless.

 ### 1.3 Resilience Rules
 - On temporary network/API errors (`502/504`), the GUI auto-retries up to three times (backoff: 0.5s, 1s, 2s).
 - If all retries fail, the GUI shows: “Server likely cold-starting (~90s). Will retry.”
 - While EC2 is cold-starting, cost polling pauses to avoid AWS throttling and false alarms.

 ---

 ## 2️⃣ External API Layer — Amazon API Gateway (HTTP API)

 ### 2.1 Endpoints

 | Route   | Method | Payload                                  | Purpose                           |
 |---------|--------|------------------------------------------|-----------------------------------|
 | /infer  | POST   | `{"prompt": str, "idle": int}`           | Main inference for LLM            |
 | /stop   | POST   | none                                     | Immediately stop GPU instance     |
 | /ping   | GET    | —                                        | GUI health check                  |

 ### 2.2 Authorizer
 - Uses AWS Cognito user-pool; JWT token TTL 60 min.
 - API-level throttle: 5 requests/second per user.
 - **Reason:** This method is simple, robust, and minimizes security risks.

 ### 2.3 Logging & CORS
 - All access logs are sent to CloudWatch group `/apigw/tl-fif` in JSON format for easy monitoring.
 - CORS policy allows `http://localhost:*` (desktop GUI) and can add mobile domains later.

 ---

 ## 3️⃣ Lambda Router v2 — Python 3.12 (512 MB, 30 s)

 ### 3.1 Code Path (Happy Flow)
 1. Verifies JWT claims from the API request.
 2. If EC2 is stopped, calls `start_instances()` and immediately returns `{"status":"starting", "eta":90}` to GUI.
 3. Otherwise, generates a unique job ID, writes prompt/job to Redis (TTL 300s).
 4. Sends a custom CloudWatch metric (`Requests` +1).
 5. Returns `{"status":"queued","id":uuid}` so GUI can poll S3 for result.

 ### 3.2 Stop Path
 - `/stop` endpoint calls `stop_instances()` for the GPU and logs a `ManualStops` CloudWatch metric.

 ### 3.3 Why 512 MB?
 - Ensures Lambda cold-starts are under 500ms, enough memory for lightweight routing logic.

 ### 3.4 Why DynamoDB ActiveSessions?
 - Prepares for future multi-user: fast lookup of which EC2 instance is linked to each user (not critical now, but easy to expand later).

 ### 3.5 Deployment & Rollback
 - Lambda code zipped by CodeBuild and deployed as a versioned alias `prod`.
 - SSM Parameter `/tl-fif/lambda_prod_version` updated post-deploy for tracking.

 ---

 ## 4️⃣ Job Queue — ElastiCache Redis 6.2

 ### 4.1 Cluster Spec
 - Runs on a small, cost-efficient `t4g.small` Graviton node (~1.1 GiB RAM), in private subnet group `tl-fif-priv`.
 - For speed and savings, encryption-in-transit is disabled inside the VPC (can be enabled later).

 ### 4.2 Message Protocol
 - Each job key is `job:{uuid}` and includes:
   ```json
   {
     "prompt": "...",
     "idle": 5,
     "reply_s3": "s3://tl-fif-responses/{uuid}.json",
     "timestamp": <epoch_ms>
   }
   ```
 - The idle-minutes are passed through so the EC2 node knows when to auto-stop.

 ### 4.3 Security Groups
 - Only Lambda’s security group can reach Redis on port 6379 (no public or wide access).
 - All outbound allowed by default, but no public endpoint (inspector rule blocks 0.0.0.0/0).

 ### 4.4 Reasoning vs SQS
 - Redis gives ultra-fast response times and easy cleanup via TTL.
 - SQS would be cheaper for big workloads, but has polling lag and extra fees—Redis is best for this single-GPU, low-rate setup.

 ---

 # 🦙 TL-FIF v1.0 — Expanded Requirement List (RQL 1-Detail, PART 2/3)

 ## 5️⃣ Inference EC2 — “GPU-node” AMI

 | ID    | Spec / Step         | Exact Implementation & Details                                                                                                           | Rationale / Notes                                         |
 |-------|---------------------|-----------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------|
 | 5.1   | Instance type       | `g4dn.xlarge` (4 vCPU, 16 GiB RAM, T4 GPU, on-demand only); root EBS: gp3 100 GiB, 3,000 IOPS, 250 MiB/s.                               | Cost-efficient, meets vLLM/TinyLlama resource needs.      |
 | 5.2   | AMI content         | Ubuntu 22.04 LTS, CUDA 12, Python 3.10, vLLM 0.4.2, `tinyllama-1.1B-chat.gguf`, `run_vllm.service` (systemd unit).                      | Pre-baking slashes boot time to under 50 s.               |
 | 5.3   | Boot signalling     | `/etc/rc.local` posts timestamp to SSM param `/tl-fif/ready/$INSTANCE_ID`.                                                              | Lets Lambda poll for “hot” readiness—decoupled from logs. |
 | 5.4   | Inference runtime   | `vllm.api_server` binds to 127.0.0.1:8000; nginx reverse-proxy exposes HTTPS 443, ACM cert `api.tl-fif.local`, SG self-ref.             | Secure (no public API), easy TLS, scalable.               |
 | 5.5   | Watcher daemon      | `watcher.py` (via supervisord): pops Redis jobs, runs vLLM inference, writes result to `/tmp/$UUID.json`, uploads to S3 responses.      | One process for reliability, async for future scale.      |
 | 5.6   | Auto-stop logic     | `idle_timer` thread counts down from user-chosen idle value (default 5 min), then uses IMDSv2-signed `ec2:StopInstances` on self.       | Local, serverless cost-control; no external Lambda cost.  |
 | 5.7   | No SSH stance       | SSH port 22 is closed; SSM Agent pre-installed; only IAM/SSM access for admin/break-glass.                                              | Removes key-pair headaches; full audit.                   |
 | 5.8   | Hot-swap LoRA (future) | Redis job may include `adapter_uri`; watcher can live-reload LoRA with `vllm.reload_lora()`—no reboot required.                         | Ready for personal fine-tuning in next stage.             |

 **Cold boot timeline:**  
 1. `start_instances` (3s) → AWS hypervisor (15–20s) → Kernel/init (10s) → vLLM model load (~25s) → rc.local posts READY.  
 2. **Total cold start:** usually under 90 seconds, measured with this AMI approach.

 ---

 ## 6️⃣ Cost & Metrics Strategy

 | Layer      | Metric/Control                      | Tooling/Service                    | Frequency   | Purpose/Reason                                            |
 |------------|-------------------------------------|-------------------------------------|-------------|-----------------------------------------------------------|
 | EC2        | GPU Util %, vRAM %, p95 latency     | CloudWatch Agent + `statsd_exporter`| 10s         | Detect saturation, early alarms, capacity planning.       |
 | Lambda     | ColdStarts, Requests, Errors        | `put_metric_data`                   | Per call    | Ops dashboard, SLOs, alerting.                           |
 | Budget     | *CurrentSpendEUR* (hourly)          | Lambda → Cost Explorer → CloudWatch | 1h          | GUI shows live spend; triggers €15 alarm.                 |
 | Hard kill  | Budget overrun → stop GPU           | AWS Budgets → SNS → Lambda (killer) | On breach   | Prevents runaway cost if usage spikes.                    |
 | Idle miss  | No inference 15 min & EC2 running   | CloudWatch composite + Stop action  | 60s eval    | Safety net if watchdog fails.                             |

 **Cost estimates (Frankfurt):**
 - g4dn.xlarge on-demand: ~$0.526/hr; a 5-min session ≈ $0.044.
 - Redis t4g.small: $0.025/hr.
 - CloudWatch, Lambda, API GW: pennies/month (<$3/mo).

 ---

 ## 7️⃣ AMI Build & CI/CD Pipeline

 | Step/Stage     | Action/Detail                                                                                               | Notes/Rationale                                |
 |---------------|-------------------------------------------------------------------------------------------------------------|------------------------------------------------|
 | 7.1 Packer     | Template (`ami.json`) parameterized: `base_os`, `weights_url`, `vllm_version`.                              | All model/weights/versioning managed in code.  |
 |               | Installs OS, Python, CUDA, vLLM, TinyLlama weights, systemd, watcher, SSM.                                  | Minimal image drift; ready for quick rebuild.  |
 | 7.2 CodePipeline | Stages: Source (GitHub) → Build (CodeBuild, unit test ≥90%) → Bake (Packer) → Manual Approval → Deploy.   | Slack/email notif on approval required.        |
 |               | Deploy step updates SSM Parameter `/tl-fif/latest_ami_id` (used in EC2 LaunchTemplate).                      | Allows seamless AMI roll-forward/rollback.     |
 | 7.3 Rollback   | Keep 5 AMI versions; LaunchTemplate points to SSM param.                                                    | Rollback = update param, restart EC2.          |
 | 7.4 Lifecycle & Cost | EBS snapshots ~12GiB ≈ $0.60/mo each; Packer on Graviton, each build ≈ $0.02 (10min).                 | Retention policy controls storage cost.        |

 **Packer Example (JSON Skeleton):**
 ```json
 {
   "builders": [{
     "type": "amazon-ebs",
     "instance_type": "m7g.large",
     "ami_name": "tl-fif-{{timestamp}}",
     "source_ami_filter": {"name":"ubuntu/images/*22.04-arm64*"},
     "ssh_username":"ubuntu",
     "ami_regions":["eu-central-1"],
     "launch_block_device_mappings":[{"device_name":"/dev/xvda","volume_size":100,"volume_type":"gp3"}]
   }],
   "provisioners": [
     { "type":"shell","inline":[
       "sudo apt update && sudo apt -y install python3-pip nginx supervisor",
       "pip install --no-cache-dir vllm==0.4.2 torch --index-url https://download.pytorch.org/whl/cu121",
       "mkdir -p /opt/llm && wget -q $WEIGHTS_URL -O /opt/llm/tiny.gguf",
       "cp files/run_vllm.service /etc/systemd/system/",
       "cp files/watcher.py /usr/local/bin/"
     ]}
   ]
 }
 ```

 ---

 # 🦙 TL-FIF v1.0 — Expanded Requirement List (RQL 1-Detail, PART 3/3)

 ## 8️⃣ IAM Roles & Security Boundary Design

 | ID    | Role / Policy             | Trust & Permissions (summary)                                                                                            | Rationale / Notes                                            |
 |-------|---------------------------|--------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------|
 | 8.1   | tl-fif-gui-role           | Trust: Cognito; Permission: `execute-api:Invoke` on API ID only.                                                         | GUI only uses short-lived ID token; no AWS keys on device.   |
 | 8.2   | tl-fif-lambda-router-role | Trust: Lambda; Inline: `ec2:Start/Stop/Describe` (tag-limited), `elasticache:Publish`, `dynamodb:PutItem`, `cloudwatch:PutMetricData` | Least-privilege, tag-constrained, isolates routing actions.  |
 | 8.3   | tl-fif-ec2-role           | Trust: EC2; `s3:GetObject` (models, responses), `ssm:PutParameter`, `ec2:StopInstances` (self-only), `cloudwatch:PutMetricData`       | Lets EC2 self-stop, signal, and pull weights securely.       |
 | 8.4   | tl-fif-codebuild-role     | Trust: CodeBuild; `iam:PassRole`, `ec2:CreateImage/Tags/DeregisterImage`, `ssm:PutParameter`                              | Only needed for AMI bake/rotate; never impacts running jobs. |
 | 8.5   | (optional) RAM share      | Share AMI + EBS snapshot with prod via AWS RAM; read-only ARNs.                                                          | Clean dev/prod isolation, test prod before wide rollout.     |

 - IAM Access Analyzer enabled for account.
 - All inline policies managed in code (`/infra/iam/*.json`).
 - S3 buckets for models/responses use **MFA-delete**.

 ---

 ## 9️⃣ Networking / VPC Topology

 | Component         | Config / Addressing                         | Reasoning / Notes                                      |
 |-------------------|---------------------------------------------|--------------------------------------------------------|
 | VPC               | 10.20.0.0/22                                | Plenty for PoC, simple routing.                        |
 | Subnets           | Public-a: 10.20.0.0/24 (NAT GW); Private-a: 10.20.1.0/24 (Redis+Lambda); Private-b: 10.20.2.0/24 (EC2) | Spreads risk, isolates sensitive compute/data.          |
 | NAT Gateway       | In Public-a; Elastic IP                     | Outbound S3/SSM/ACM for private subnets.               |
 | NLB               | Public-a; targets EC2 on 443                | Static DNS; Lambda not exposed; TLS on EC2.            |
 | Security Groups   | GPU: in 443 from NLB, out to NAT only. Redis: in 6379 from Lambda only. Default deny all else.         | Strong allow-list, block all public/SSH access.         |
 | VPC Endpoints     | Interface endpoints for SSM, S3, CloudWatch | Keeps traffic private and reduces data transfer costs.  |

 **Data Flow:**  
 GUI ⇄ API Gateway ⇄ Lambda (ENI) → Redis → NLB → EC2.  
 Inference result is written to S3, then fetched by GUI.

 ---

 ## 🔟 Disaster Recovery & Compliance

 | Area           | Control / Setting                                       | Schedule/Action                | Audit/Reason                |
 |----------------|--------------------------------------------------------|-------------------------------|-----------------------------|
 | Snapshots      | Daily EBS snapshot (GPU root); 7-day retention         | Data Lifecycle Manager        | Fast AMI rebuild/recovery   |
 | S3 Lifecycle   | Responses: Glacier after 30d, delete after 1y          | Automated                     | Controls storage cost       |
 | CloudTrail     | All regions/events to log bucket `org-cloudtrail-logs` | Always on                     | Audits all IAM activity     |
 | AWS Config     | Rules: encrypted-volumes, required-tags, no-public-S3  | Continuous                    | Marks/isolates violations   |
 | Backup Test    | Monthly AMI spin-up test (`TL-FIF-DR-Test` SSM doc)    | Automated                     | Ensures DR snapshots boot   |
 | Budget Enforce | Lambda `BudgetKiller` stops GPU at €20/month           | Automated                     | No runaway cost             |

 ---

 ## 1️⃣1️⃣ Future-Proof Hooks — Personal LoRA & Multi-Model

 | Feature/Hook      | Implemented? | Future Action                                        |
 |-------------------|--------------|------------------------------------------------------|
 | Adapter URI       | Yes          | Redis job JSON field; watcher can hot-load LoRA      |
 | Multi-GPU Scale   | Yes (template)| ASG desired >1, tracking queue depth                 |
 | Model registry    | Yes (S3+SSM)  | Add DynamoDB catalog for meta; router picks GPU type |
 | Agent-routing     | Yes (enum)    | Lambda Router can add more provider backends         |

 ---

 ## ✅ Final Acceptance Checklist

 | Category      | KPI / Evidence                                              | Pass When                                    | Owner     |
 |---------------|-------------------------------------------------------------|----------------------------------------------|-----------|
 | Cold-start    | `/infer` returns first token in ≤90s (end-to-end)           | Measured by stopwatch via GUI                | DevOps    |
 | Cost          | ≤€20/month for 30 sessions                                  | AWS Budgets/Cost Explorer report             | FinOps    |
 | Security      | No public S3, no SSH, all EBS encrypted                     | AWS Config = 0 non-compliant                 | SecEng    |
 | DR            | Snapshot boots, `/infer` works on new node                  | Monthly SSM DR test passes                   | DevOps    |
 | GUI UX        | Prompt send works, live cost ticks, Stop GPU <10s           | QA on Windows/macOS                          | PO        |

 *Sign-off*: When all boxes ticked, tag Git `release-mvp-v1.0` and freeze documentation.

 ---
 ## 1️⃣2️⃣ Dual Backend Support — AWS TinyLlama & OpenAI (Permanent Feature)

## Dual Backend Support (Permanent Feature)

### GUI Behavior:
- Add a dropdown menu to the main interface with two options:
  - AWS TinyLlama API (default)
  - OpenAI GPT API (permanent, equal status with AWS)
- User can select backend at any time; the GUI uses the chosen backend for all prompt actions.

### Technical Implementation:
- Define a simple `BackendClient` interface (abstract class/protocol) in the controllers package.
- Provide two backend implementations:
    - `AwsTinyLlamaClient` for all AWS API interactions
    - `OpenAiApiClient` for direct OpenAI API usage
- Both classes must implement minimal core methods (e.g., `send_prompt`, `get_response`, `handle_errors`).
- The controller(s) route requests to the current backend, depending on GUI selection.

### Constraints and Scope:
- Keep the implementation as minimal and modular as possible.
- No backend-specific GUI features (the user experience remains the same for both).
- All code for backend selection and switching must be cleanly separated and easy to extend.
- All error handling and logging should distinguish backend origin clearly.

### Acceptance Criteria:
- GUI functions identically and stays responsive with either backend.
- Switching between AWS and OpenAI is instant and seamless; no GUI freezing or instability.
- Error and response handling work equally well for both backends.
- The codebase remains clean, modular, and easy to extend for future orchestration (e.g., combining both via "RusbehGTP" meta-backend).
