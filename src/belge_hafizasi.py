import re
import numpy as np
from rag_setup import get_embedding_fn

_aktif_belge = {"parcalar": [], "vektorler": None, "kaynak_adi": None, "ham_metin": None}
_embed_fn = None


def _embed():
    global _embed_fn
    if _embed_fn is None:
        _embed_fn = get_embedding_fn()
    return _embed_fn


def belgeyi_indeksle(metin: str, kaynak_adi: str, parca_boyutu: int = 200, ortusme: int = 30) -> int:
    kelimeler = metin.split()
    parcalar = []
    i = 0
    while i < len(kelimeler):
        parca = " ".join(kelimeler[i:i + parca_boyutu])
        if parca.strip():
            parcalar.append(parca)
        i += parca_boyutu - ortusme

    if not parcalar:
        belgeyi_temizle()
        return 0

    pasaj_versiyonu = [f"passage: {p}" for p in parcalar]
    vektorler = np.array(_embed()(pasaj_versiyonu))

    _aktif_belge["parcalar"] = parcalar
    _aktif_belge["vektorler"] = vektorler
    _aktif_belge["kaynak_adi"] = kaynak_adi
    _aktif_belge["ham_metin"] = metin
    return len(parcalar)


def aktif_belge_var_mi() -> bool:
    return bool(_aktif_belge["parcalar"])


def aktif_belge_adi() -> str | None:
    return _aktif_belge["kaynak_adi"]


def belgede_ara(soru: str, n: int = 3, esik: float = 0.80):
    if not aktif_belge_var_mi():
        return []
    soru_vektor = np.array(_embed()([f"query: {soru}"])[0])
    vektorler = _aktif_belge["vektorler"]
    benzerlikler = vektorler @ soru_vektor / (
        np.linalg.norm(vektorler, axis=1) * np.linalg.norm(soru_vektor) + 1e-8
    )
    en_iyi_indeksler = benzerlikler.argsort()[::-1][:n]
    return [
        (_aktif_belge["parcalar"][i], float(benzerlikler[i]))
        for i in en_iyi_indeksler if benzerlikler[i] >= esik
    ]


NUMARALI_CUMLE_DESENI = re.compile(r'(\d+)\s*\.?\s*(cümle|cumle)', re.IGNORECASE)


def numarali_cumle_istegi_mi(metin: str) -> int | None:
    """'2. cümlesini' gibi bir istek varsa cümle numarasını döndürür, yoksa None."""
    eslesme = NUMARALI_CUMLE_DESENI.search(metin)
    return int(eslesme.group(1)) if eslesme else None


def numarali_cumleyi_getir(numara: int) -> str | None:
    if not aktif_belge_var_mi() or not _aktif_belge["ham_metin"]:
        return None
    cumleler = re.split(r'(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜ0-9])', _aktif_belge["ham_metin"].strip())
    if 1 <= numara <= len(cumleler):
        return cumleler[numara - 1].strip()
    return None


def belgeyi_temizle():
    _aktif_belge["parcalar"] = []
    _aktif_belge["vektorler"] = None
    _aktif_belge["kaynak_adi"] = None
    _aktif_belge["ham_metin"] = None


def ham_metni_al() -> str | None:
    return _aktif_belge["ham_metin"]