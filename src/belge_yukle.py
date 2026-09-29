from config import BASE_DIR
from pathlib import Path
from pypdf import PdfReader
from docx import Document as DocxDocument
from rag_setup import get_collections

def metni_oku(dosya_yolu: str) -> str:
    yol = Path(dosya_yolu)
    uzanti = yol.suffix.lower()

    if uzanti == ".pdf":
        reader = PdfReader(str(yol))
        return "\n".join(sayfa.extract_text() or "" for sayfa in reader.pages)

    elif uzanti == ".docx":
        doc = DocxDocument(str(yol))
        return "\n".join(p.text for p in doc.paragraphs)

    elif uzanti == ".txt":
        return yol.read_text(encoding="utf-8")

    else:
        raise ValueError(f"Desteklenmeyen dosya türü: {uzanti}")

def parcalara_bol(metin: str, parca_boyutu=500, ortusme=50) -> list[str]:
    kelimeler = metin.split()
    parcalar = []
    i = 0
    while i < len(kelimeler):
        parca = " ".join(kelimeler[i:i + parca_boyutu])
        if parca.strip():
            parcalar.append(parca)
        i += parca_boyutu - ortusme
    return parcalar

def belge_yukle(dosya_yolu: str):
    yol = Path(dosya_yolu)
    metin = metni_oku(dosya_yolu)
    parcalar = parcalara_bol(metin)

    cols = get_collections()
    belgeler = cols["belgeler"]

    ids = [f"{yol.stem}_parca_{i}" for i in range(len(parcalar))]
    metadatas = [{"kaynak": yol.name, "parca_no": i} for i in range(len(parcalar))]

    belgeler.upsert(ids=ids, documents=parcalar, metadatas=metadatas)
    print(f"'{yol.name}' yüklendi: {len(parcalar)} parça oluşturuldu.")
    return len(parcalar)

def belgede_ara(sorgu: str, n=3, kaynak_filtre: str = None):
    cols = get_collections()
    belgeler = cols["belgeler"]
    kwargs = {"query_texts": [sorgu], "n_results": n}
    if kaynak_filtre:
        kwargs["where"] = {"kaynak": kaynak_filtre}
    return belgeler.query(**kwargs)