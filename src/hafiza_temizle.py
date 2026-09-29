from rag_setup import get_chroma_client

client = get_chroma_client()
client.delete_collection("ceviri_hafizasi")
print("'ceviri_hafizasi' koleksiyonu tamamen temizlendi.")