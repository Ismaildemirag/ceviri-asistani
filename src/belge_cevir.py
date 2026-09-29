from pathlib import Path
from belge_yukle import metni_oku
from translate import metni_cevir
from config import BASE_DIR

def belge_cevir(dosya_yolu: str, ilerleme_callback=None) -> str:
    metin = metni_oku(dosya_yolu)
    return metni_cevir(metin, yon=None, ilerleme_callback=ilerleme_callback)

def belge_cevir_ve_kaydet(dosya_yolu: str) -> Path:
    kaynak = Path(dosya_yolu)
    cevrilmis = belge_cevir(dosya_yolu)

    cikti_klasoru = BASE_DIR / "data" / "ciktilar"
    cikti_klasoru.mkdir(parents=True, exist_ok=True)

    cikti_yolu = cikti_klasoru / f"{kaynak.stem}_cevrilmis.txt"
    cikti_yolu.write_text(cevrilmis, encoding="utf-8")
    return cikti_yolu