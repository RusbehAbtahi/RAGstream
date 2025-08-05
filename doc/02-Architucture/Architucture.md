````
                                     ┌───────────────────────────────────┐
                                     │      🔄  Ingestion Pipeline       │
                                     │───────────────────────────────────│
 User adds / updates docs  ─────────►│ 1  DocumentLoader (paths / watch) │
                                     │ 2  Chunker  (recursive splitter)  │
                                     │ 3  Embedder (E5 / BGE model)      │
                                     │ 4  VectorStore.add() (Chroma)     │
                                     └───────────────────────────────────┘
                                                      ▲
                                                      │ builds / refreshes
                                                      │
╔═════════════════════════════════════════════════════════════════════════════╗
║                               MAIN QUERY FLOW                               ║
╚═════════════════════════════════════════════════════════════════════════════╝
                                                                           
[User Prompt] ───▶ 🎛️  Streamlit GUI                                            
                    ├── Per-file **Attention Sliders**  (wᵢ 0-100 %)          
                    │                                                                                    
                    ▼                                                                                    
              🔍  **Retriever**  (VectorStore + Embedder)                                                      
                    │  (top-N dense search, scores · wᵢ)                                                     
                    │                                                                                    
        🏅  **Reranker**  (MiniLM cross-encoder)                                                              
                    │  (refines ranking)                                                                  
                    ▼                                                                                    
         🚦  **PromptBuilder**  (template composition)                                                      
                    │                                                                                    
                    ├─────────────▶ 🛠️  **ToolDispatcher**  (detect & run)                                 
                    │                 ├── MathTool (SymPy/NumPy)                                          
                    │                 └── PyTool   (safe CPython sandbox)                                 
                    │                     (optional – only triggers when                                   
                    │                      prompt explicitly requests)                                     
                    ▼                                                                                    
           📡  **LLMClient**  (OpenAI GPT-3.5/4 API)                                                    
                    │                                                                                    
                    ▼                                                                                    
        🖥️  **Streamlit GUI**                                             
            • shows retrieved chunks + scores & citations                                                  
            • shows tool output (if any)                                                                    
            • displays final answer                                                                        

Notes
─────
1.  Ingestion pipeline runs on demand or in background file-watch mode; it **feeds**
    the VectorStore used by the Retriever.

2.  **Attention Sliders** supply weights wᵢ that are multiplied into the similarity
    scores *before* reranking → instant, transparent influence.

3.  **ToolDispatcher** intercepts prompts of the form  
       ```calc: 2*(3+5)```  or  
       ```py: for i in range(3): print(i)```  
    executes locally, injects the result back into the context the LLM sees.

4.  Every box maps 1-for-1 to a < 100-line Python class from the UML:
       • DocumentLoader, Chunker, Embedder, VectorStore  
       • Retriever, Reranker, AttentionWeights  
       • ToolRegistry / Dispatcher / Tools  
       • PromptBuilder, LLMClient  
       • Controller (ties everything), StreamlitUI        

5.  Zero external infra: all compute is local except the outbound HTTPS call to
    OpenAI.  Swap-in a local LLM later by replacing **LLMClient** only.
````
