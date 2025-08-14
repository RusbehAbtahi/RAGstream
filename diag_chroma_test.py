from pathlib import Path
print("START")
import chromadb
from chromadb import PersistentClient
p = Path(r"C:\0000\Prompt_Engineering\Projects\GTPRusbeh\RAGstream\data\chroma_db\diag_cmd")
p.mkdir(parents=True, exist_ok=True)
print("PERSIST_DIR:", p)
client = PersistentClient(path=str(p))
print("CLIENT_OK")
coll = client.get_or_create_collection(name="diag_vectors", embedding_function=None)
print("COLLECTION_OK")
coll.add(ids=["a"], embeddings=[[0.1,0.2,0.3]], metadatas=[{"source":"diag_a"}])
print("ADD_OK")
res = coll.query(query_embeddings=[[0.1,0.2,0.3]], n_results=1)
print("QUERY_OK", res.get("ids"))
