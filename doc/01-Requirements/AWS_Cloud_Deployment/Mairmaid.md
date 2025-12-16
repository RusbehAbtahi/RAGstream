graph TD

subgraph InternetLayer["Internet and Home Network"]
    I[Internet]
    R[FritzBox Router NAT Firewall]
    LAN[Home LAN 192 168 X X]
    I --> R
    R --> LAN
end

subgraph Laptop["Your Laptop"]
    HW[Physical Hardware]
    OS[Windows 11]
    B[Browser Chrome or Edge]
    HW --> OS
    OS --> B
end

subgraph WSL["WSL2 Linux VM inside Windows"]
    LNX[Linux OS WSL2]
    DD[Docker Daemon]
    OS --> LNX
    LNX --> DD
end

subgraph ContainerLayer["Docker Container ragstream local"]
    IMG[Image FS python 3 11 slim plus RAGstream code]
    PY[Python Runtime]
    ST[Streamlit App ragstream app ui_streamlit py]
    CNET[Container Network virtual NIC]
    IMG --> PY
    PY --> ST
    ST --> CNET
end

%% Connections between layers
B -- HTTP localhost 8501 --> OS
OS -- localhost 8501 --> DD
DD -- port mapping 8501 to 8501 --> CNET
LAN --- OS

%% Colors
classDef physical fill:#f4d03f,stroke:#b7950b,stroke-width:1px;
classDef os fill:#85c1e9,stroke:#2e86c1,stroke-width:1px;
classDef runtime fill:#82e0aa,stroke:#27ae60,stroke-width:1px;
classDef app fill:#f5b7b1,stroke:#c0392b,stroke-width:1px;
classDef net fill:#d2b4de,stroke:#7d3c98,stroke-width:1px;
classDef security fill:#f9e79f,stroke:#b7950b,stroke-width:1px;
classDef fs fill:#f8f9f9,stroke:#7b7d7d,stroke-width:1px;

class HW physical
class OS,LNX os
class DD,PY runtime
class B,ST app
class I,LAN,CNET net
class R security
class IMG fs
