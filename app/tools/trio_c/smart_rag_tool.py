import numpy as np
import os
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
laws_path = os.path.join(BASE_DIR, "data", "environmental_laws.txt")

with open(laws_path, encoding="utf-8") as f:
    laws = [
        line.strip()
        for line in f
        if line.strip() and not line.startswith("#")
    ]

law_embeddings = model.encode(laws, normalize_embeddings=True)

print(f"Smart RAG loaded {len(laws)} laws successfully")
def retrieve_laws(query: str, top_k: int = 3):

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