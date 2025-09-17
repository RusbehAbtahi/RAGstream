from pathlib import Path
from datetime import datetime
from hashlib import blake2b
import time

from ragstream.ingestion.loader import DocumentLoader
from ragstream.ingestion.chunker import Chunker
from ragstream.ingestion.embedder import Embedder
from ragstream.ingestion.vector_store_np import VectorStoreNP  # keep if your module is named this way

# tests/ is one level below repo root
REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR  = REPO_ROOT / "data"

WORKSPACE = "project1"  # or pass via CLI/ENV

RAW_DIR = DATA_DIR / "doc_raw"      / WORKSPACE
DB_DIR  = DATA_DIR / "np_store"     / WORKSPACE   # or DATA_DIR / "vector_pkls" / WORKSPACE to match Requirements

def stable_id(path: str, chunk_text: str) -> str:
    h = blake2b(digest_size=16)
    h.update(path.encode("utf-8")); h.update(b"||"); h.update(chunk_text.encode("utf-8"))
    return h.hexdigest()

def main():
    t0 = time.perf_counter()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DB_DIR.mkdir(parents=True, exist_ok=True)

    print("REPO_ROOT:", REPO_ROOT)
    print("RAW_DIR:", RAW_DIR)
    print("DB_DIR:", DB_DIR)

    # 1) Load docs from data/doc_raw/<workspace>
    loader = DocumentLoader(DATA_DIR / "doc_raw")
    docs = loader.load_documents(WORKSPACE)
    print("Loaded docs:", len(docs))

    # 2) Chunk
    chunker = Chunker()
    chunks = []
    for file_path, text in docs:
        chunks.extend(chunker.split(file_path, text, chunk_size=500, overlap=100))
    print("Chunks produced:", len(chunks))
    if not chunks:
        print("No chunks produced. Exiting.")
        return

    # 3) Embed (requires OPENAI_API_KEY)
    embedder = Embedder()
    texts = [chunk_text for _, chunk_text in chunks]
    t1 = time.perf_counter()
    vectors = embedder.embed(texts)
    t2 = time.perf_counter()
    print("Embeddings returned:", len(vectors), "embed_time_s:", round(t2 - t1, 3))

    # 4) Save to NumPy VectorStore under data/np_store/<workspace>
    ids = [stable_id(path, chunk_text) for path, chunk_text in chunks]
    meta = [{"source": path} for path, _ in chunks]

    vs = VectorStoreNP(str(DB_DIR))
    vs.add(ids, vectors, meta)
    vs.snapshot(datetime.now().strftime("%Y%m%d_%H%M%S"))

    # 5) Quick query using the first vector
    top_ids = vs.query(vectors[0], k=3)
    print("Top result IDs:", top_ids)

    print("DB path:", DB_DIR)
    print("DONE total_s:", round(time.perf_counter() - t0, 3))

if __name__ == "__main__":
    main()
