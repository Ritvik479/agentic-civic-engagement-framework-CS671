import numpy as np
import os

_MODEL = None
_LAW_EMBEDDINGS = None
_LAWS = None

def _get_rag_resources():
    global _MODEL, _LAW_EMBEDDINGS, _LAWS
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer
        print("  [smart_rag] Loading SentenceTransformer model...")
        _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
        
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        laws_path = os.path.join(BASE_DIR, "data", "environmental_laws.txt")
        
        with open(laws_path, encoding="utf-8") as f:
            _LAWS = [
                line.strip()
                for line in f
                if line.strip() and not line.startswith("#")
            ]
        
        print(f"  [smart_rag] Encoding {len(_LAWS)} laws...")
        _LAW_EMBEDDINGS = _MODEL.encode(_LAWS, normalize_embeddings=True)
        print("  [smart_rag] Resources loaded successfully.")
    
    return _MODEL, _LAWS, _LAW_EMBEDDINGS

def retrieve_laws(query: str, top_k: int = 3):
    model, laws, law_embeddings = _get_rag_resources()
    
    query_embedding = model.encode([query], normalize_embeddings=True)[0]

    scores = np.dot(law_embeddings, query_embedding)

    top_indices = np.argsort(scores)[::-1][:top_k]

    results = []

    for i in top_indices:
        results.append({
            "law": laws[i],
            "score": round(float(scores[i]), 3)
        })

    return results