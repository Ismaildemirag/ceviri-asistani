import chromadb
from chromadb.utils import embedding_functions
from config import CHROMA_DB_PATH, EMBEDDING_MODEL

def get_chroma_client():
    return chromadb.PersistentClient(path=CHROMA_DB_PATH)

def get_embedding_fn():
    return embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)

def get_collections():
    client = get_chroma_client()
    embed_fn = get_embedding_fn()
    return {
        "terminoloji": client.get_or_create_collection("terminoloji", embedding_function=embed_fn),
        "belgeler": client.get_or_create_collection("belgeler", embedding_function=embed_fn),
        "ceviri_hafizasi": client.get_or_create_collection("ceviri_hafizasi", embedding_function=embed_fn),
    }

if __name__ == "__main__":
    cols = get_collections()
    print("ChromaDB hazır. Koleksiyonlar:", list(cols.keys()))