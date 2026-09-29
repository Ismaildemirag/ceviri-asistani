from rag_setup import get_collections

terimler = [
    {"en": "machine learning", "tr": "makine öğrenimi"},
    {"en": "neural network", "tr": "sinir ağı"},
    {"en": "deep learning", "tr": "derin öğrenme"},
    {"en": "artificial intelligence", "tr": "yapay zeka"},
    {"en": "data science", "tr": "veri bilimi"},
]

def terimleri_yukle():
    cols = get_collections()
    terminoloji = cols["terminoloji"]

    ids = [f"terim_{i}" for i in range(len(terimler))]
    documents = [f"{t['en']} = {t['tr']}" for t in terimler]
    metadatas = [{"en": t["en"], "tr": t["tr"]} for t in terimler]

    terminoloji.upsert(ids=ids, documents=documents, metadatas=metadatas)
    print(f"{len(terimler)} terim yüklendi.")

def terim_ara(sorgu, n=3):
    cols = get_collections()
    terminoloji = cols["terminoloji"]
    sonuc = terminoloji.query(query_texts=[sorgu], n_results=n)
    return sonuc

if __name__ == "__main__":
    terimleri_yukle()