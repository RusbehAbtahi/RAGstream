# RAGstream HTTP Reverse Proxy Architecture (Route 53 → EC2 → nginx → Streamlit on localhost)

```mermaid
%%{init: {"theme":"default"}}%%
graph TD

subgraph Client["Client (User side)"]
  U["User"]
  B["Browser: http://ragstream.rusbehabtahi.com"]
  U --> B
end

subgraph DNS["DNS resolution (how the browser finds the IP)"]
  RES["Recursive DNS resolver (ISP / OS / Router DNS)"]
  R53["Route 53 authoritative DNS: ragstream.rusbehabtahi.com -> EC2 public IPv4"]
  RES --> R53
end

subgraph Internet["Public Internet"]
  NET["Internet routing"]
end

subgraph AWS["AWS VPC (public subnet)"]
  EDGE["AWS Edge: Public IPv4 endpoint + 1:1 NAT to instance private IPv4"]
  SG["Security Group check (firewall): allow inbound TCP 80 to instance ENI"]
  ENI["EC2 network interface (ens5) + Private IPv4 (e.g., 172.31.x.x)"]
  EDGE --> SG
  SG --> ENI
end

subgraph EC2["EC2 Instance (Linux)"]
  NGINX["nginx on host: listens on 0.0.0.0:80"]
  LOOP["Loopback on host: 127.0.0.1:8501"]
  DOCKER["Docker port publish: host 127.0.0.1:8501 -> container 8501"]
  ST["Streamlit in Docker container: listens on 0.0.0.0:8501 (inside container)"]
end

B -->|"1) DNS query: ragstream.rusbehabtahi.com"| RES
R53 -->|"2) DNS answer: <ec2-public-ip>"| RES
RES -->|"3) Browser learns <ec2-public-ip>"| B

B -->|"4) HTTP request to <ec2-public-ip>:80 (default for http)"| NET
NET --> EDGE
ENI --> NGINX

NGINX -->|"5) Reverse proxy to http://127.0.0.1:8501"| LOOP
LOOP --> DOCKER
DOCKER --> ST

ST -->|"6) Response"| DOCKER
DOCKER --> LOOP
LOOP --> NGINX
NGINX -->|"7) Response back to client"| ENI
ENI --> EDGE
EDGE --> NET
NET --> B

NGINX --- NOTE1["nginx selects the correct server block using the HTTP Host header: ragstream.rusbehabtahi.com"]
NGINX --- NOTE2["The user never connects to port 8501; only nginx connects to 127.0.0.1:8501 on the same EC2"]
NGINX --- NOTE3["nginx forwards request context via headers (e.g., Host, X-Real-IP, X-Forwarded-For, X-Forwarded-Proto)"]

classDef client fill:#85c1e9,stroke:#2e86c1,stroke-width:1px;
classDef dns fill:#d2b4de,stroke:#7d3c98,stroke-width:1px;
classDef net fill:#d5dbdb,stroke:#707b7c,stroke-width:1px;
classDef aws fill:#f9e79f,stroke:#b7950b,stroke-width:1px;
classDef svc fill:#82e0aa,stroke:#27ae60,stroke-width:1px;
classDef app fill:#f5b7b1,stroke:#c0392b,stroke-width:1px;
classDef note fill:#f8f9f9,stroke:#7b7d7d,stroke-width:1px;

class U,B client
class RES,R53 dns
class NET net
class EDGE,SG,ENI aws
class NGINX,LOOP,DOCKER svc
class ST app
class NOTE1,NOTE2,NOTE3 note
```

## What happens when a user opens ragstream.rusbehabtahi.com (HTTP)

1. DNS resolution (Route 53)

* The browser asks a recursive DNS resolver: “What IP belongs to ragstream.rusbehabtahi.com?”
* That resolver asks Route 53 (authoritative DNS for your domain).
* Route 53 returns the current EC2 public IPv4 address (<ec2-public-ip>) (because your EC2 startup script updates the A record).
* DNS returns only an IP address. DNS does not include ports.

2. Why the browser uses port 80

* The user entered an HTTP URL (http://...).
* For HTTP, the browser automatically uses port 80.
* This is equivalent to requesting [http://ragstream.rusbehabtahi.com:80](http://ragstream.rusbehabtahi.com:80).

3. AWS networking and the Security Group (important correction)

* The request targets the EC2 *public* IPv4, but the EC2 instance does not “own” that public IP on its Linux interface.
* AWS performs a 1:1 NAT at the AWS edge: the instance actually receives the traffic on its *private* IP (172.31.x.x) via its network interface (often named ens5).
* The Security Group is a firewall check applied to that network interface. It is not a “routing hop”; it simply allows/blocks inbound traffic (e.g., TCP 80).

4. nginx receives the request on port 80

* nginx runs on the EC2 host and listens on 0.0.0.0:80 (port 80 on all host interfaces).
* The HTTP request contains a Host header (ragstream.rusbehabtahi.com).
* nginx matches that Host header to server_name ragstream.rusbehabtahi.com in its config and chooses the correct server block.

5. Reverse proxy to localhost:8501 (host-local only)

* nginx forwards the request internally to [http://127.0.0.1:8501](http://127.0.0.1:8501) using proxy_pass.
* 127.0.0.1 is the loopback interface: it is reachable only inside the same EC2 machine.
* This means the Streamlit backend is not directly exposed to the internet; only nginx can reach it.

5.1) Why Docker is in the middle (because Streamlit runs in a container)

* Streamlit listens on port 8501 *inside the container*.
* Docker publishes that container port to the EC2 host at 127.0.0.1:8501.
* nginx talks to the host-local port (127.0.0.1:8501), and Docker forwards it to the container.

6. Response path back to the user

* Streamlit returns the response to nginx (through Docker’s port mapping).
* nginx returns that response to the browser.
* To the user it feels like they are talking directly to ragstream.rusbehabtahi.com, but technically they talk to nginx, and nginx talks to Streamlit on their behalf.

## Why the headers matter (high level)

* Because Streamlit is behind nginx, the direct TCP connection to Streamlit comes from nginx (not from the user).
* nginx forwards original request context via headers so the backend can still know:

  * the original domain (Host)
  * the real client IP (X-Real-IP / X-Forwarded-For)
  * the original protocol (X-Forwarded-Proto)

## Two quick sanity signatures (useful for debugging)

* If DNS is stale (TTL caching) or the A record points to an old IP: the domain may fail or hit the wrong machine for a few minutes.
* If nginx is reachable but the backend is down / not mapped: nginx typically returns 502 Bad Gateway.
* If the Security Group blocks port 80: nginx will never see the request at all.

```
::contentReference[oaicite:0]{index=0}
