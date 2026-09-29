import json
from rag_setup import get_collections
from config import BASE_DIR
import re

YABANCI_ALFABE_DESENI = re.compile(
    r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af\u0900-\u097f\u0600-\u06ff]'
)

def dil_temiz_mi(metin: str) -> bool:
    return not YABANCI_ALFABE_DESENI.search(metin)

def veri_setini_hafizaya_yukle(dosya_yollari: list[str], parti_boyutu: int = 500):
    cols = get_collections()
    hafiza = cols["ceviri_hafizasi"]
    gorulen_ciftler = set()

    kaynaklar, hedefler, yonler, idler = [], [], [], []
    toplam_eklenen = 0
    global_sayac = 0

    for dosya_yolu in dosya_yollari:
        print(f"\n--- İşleniyor: {dosya_yolu} ---")
        with open(dosya_yolu, "r", encoding="utf-8") as f:
            for satir in f:
                global_sayac += 1
                try:
                    kayit = json.loads(satir)
                except json.JSONDecodeError:
                    continue

                talimat_ham = kayit.get("instruction") or ""
                talimat = talimat_ham.replace("İ", "i").replace("I", "i").lower()
                girdi = (kayit.get("input") or "").strip()
                cikti = (kayit.get("output") or "").strip()

                if not girdi or not cikti:
                    continue
                if "ingilizce" in talimat and "türkçe" in talimat and "çevir" in talimat:
                    yon = "en-tr" if talimat.index("ingilizce") < talimat.index("türkçe") else "tr-en"
                else:
                    continue
                if not girdi or not cikti:
                    continue
                if not dil_temiz_mi(girdi) or not dil_temiz_mi(cikti):
                    continue 

                anahtar = (girdi.strip().lower(), yon)
                if anahtar in gorulen_ciftler:
                    continue
                gorulen_ciftler.add(anahtar)

                kaynaklar.append(girdi)
                hedefler.append(cikti)
                yonler.append(yon)
                idler.append(f"toplu_{global_sayac}")

                if len(kaynaklar) >= parti_boyutu:
                    hafiza.upsert(
                        ids=idler, documents=kaynaklar,
                        metadatas=[{"hedef": h, "yon": y} for h, y in zip(hedefler, yonler)],
                    )
                    toplam_eklenen += len(kaynaklar)
                    print(f"[İLERLEME] {toplam_eklenen} çeviri hafızaya eklendi...")
                    kaynaklar, hedefler, yonler, idler = [], [], [], []

    if kaynaklar:
        hafiza.upsert(
            ids=idler, documents=kaynaklar,
            metadatas=[{"hedef": h, "yon": y} for h, y in zip(hedefler, yonler)],
        )
        toplam_eklenen += len(kaynaklar)

    print(f"\nTamamlandı: toplam {toplam_eklenen} çeviri çifti hafızaya yüklendi (tekrarlar hariç).")


if __name__ == "__main__":
    veri_klasoru = BASE_DIR / "data"
    dosyalar = [
        str(veri_klasoru / "proje_veriseti.jsonl"),     
        str(veri_klasoru / "opus_veriseti.jsonl"),      
        str(veri_klasoru / "cturan_veriseti.jsonl"),     
        str(veri_klasoru / "karmasik_cumleler.jsonl"),    
    ]
    veri_setini_hafizaya_yukle(dosyalar)