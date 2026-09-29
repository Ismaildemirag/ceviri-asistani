import re
from unsloth import FastLanguageModel
import torch
from langdetect import detect, LangDetectException
from rag_setup import get_collections
from config import LOCAL_MODEL_PATH, MAX_SEQ_LENGTH
from web_arama import web_ara, alakali_mi, bilgi_degeri_dusuk_mu
import hashlib
import ast, operator

_model = None
_tokenizer = None


YASAKLI_SCRIPT_DESENI = re.compile(
    r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af\u0900-\u097f\u0600-\u06ff\u0370-\u03ff\u0400-\u04ff]'
)

_yasakli_token_id_cache = None

def yasakli_token_idlerini_hesapla(tokenizer):
    """Vocab'ı bir kez tarar, yabancı alfabe içeren token ID'lerini bulur ve önbelleğe alır."""
    global _yasakli_token_id_cache
    if _yasakli_token_id_cache is None:
        vocab = tokenizer.get_vocab()
        yasaklilar = []
        for token_str, token_id in vocab.items():
            temiz = token_str.replace("▁", "").replace("Ġ", "")
            if YASAKLI_SCRIPT_DESENI.search(temiz):
                yasaklilar.append(token_id)
        _yasakli_token_id_cache = yasaklilar
        print(f"[BİLGİ] {len(yasaklilar)} yabancı-alfabe token'ı üretimden yasaklandı.")
    return _yasakli_token_id_cache


def modeli_yukle():
    global _model, _tokenizer
    if _model is None:
        _model, _tokenizer = FastLanguageModel.from_pretrained(
            model_name=str(LOCAL_MODEL_PATH),
            max_seq_length=MAX_SEQ_LENGTH,
            dtype=None,
            load_in_4bit=True,
        )
        FastLanguageModel.for_inference(_model)
    return _model, _tokenizer


def _durma_tokenlari(tokenizer):
    """generate()'in <end_of_turn> gördüğünde de durmasını sağlar."""
    eos_ids = [tokenizer.eos_token_id]
    try:
        eot_id = tokenizer.convert_tokens_to_ids("<end_of_turn>")
        if eot_id is not None and eot_id != tokenizer.unk_token_id:
            eos_ids.append(eot_id)
    except Exception:
        pass
    return eos_ids


def dil_algila(metin: str) -> str:
    try:
        kod = detect(metin)
    except LangDetectException:
        kod = "en"
    return "tr" if kod == "tr" else "en"


CEVIRI_DESENI = re.compile(r'\bçevir(?!men)\w*\b|\btercüme\w*\b|\btranslate\b', re.IGNORECASE)

TRIGGER_SUFFIX = re.compile(
    r'\s*(bunu\s+|şunu\s+|lütfen\s+)?'
    r'(çevir(sene|iver|ir\s+misin|ebilir\s+misin|meni)?|tercüme\s+et(er\s+misin)?|translate(\s+this)?)'
    r'\s*[.!?]?\s*$',
    re.IGNORECASE
)


def ceviri_istegi_mi(metin: str) -> bool:
    return bool(CEVIRI_DESENI.search(metin))


def cevrilecek_icerigi_cikar(metin: str) -> str:
    return TRIGGER_SUFFIX.sub('', metin).strip()


SORU_KELIMELERI = re.compile(
    r'(kimdir|kim\b|nedir|ne\b|nerede|ne zaman|kaç|hangi|nasıl|neden|niçin|'
    r'what|who|where|when|why|how|which)',
    re.IGNORECASE
)

SOHBET_KELIMELERI = {
    "naber", "selam", "merhaba", "teşekkür", "teşekkürler", "sağol",
    "görüşürüz", "nasılsın", "iyiyim", "kötüyüm", "hoşçakal",
}


def soru_niteliginde_mi(metin: str) -> bool:
    if SORU_KELIMELERI.search(metin) or metin.strip().endswith("?"):
        return True
    kelimeler = metin.strip().split()
    if 1 <= len(kelimeler) <= 6:
        kucuk = metin.lower()
        sohbet_mi = any(k in kucuk for k in SOHBET_KELIMELERI)
        ozel_isim_var = any(k[:1].isupper() for k in kelimeler if k)
        if not sohbet_mi and ozel_isim_var:
            return True
    return False




_GUVENLI_OPERATORLER = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.USub: operator.neg,
}


def _guvenli_hesapla(node):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _GUVENLI_OPERATORLER:
        return _GUVENLI_OPERATORLER[type(node.op)](_guvenli_hesapla(node.left), _guvenli_hesapla(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _GUVENLI_OPERATORLER:
        return _GUVENLI_OPERATORLER[type(node.op)](_guvenli_hesapla(node.operand))
    raise ValueError("Desteklenmeyen ifade")


MATEMATIK_DESENI = re.compile(r'^[\d\s\.\,\+\-\*\/\(\)x×÷=]+$')


def matematik_ifadesi_mi(metin: str) -> bool:
    temiz = metin.replace("=", "").replace("kaç eder", "").replace("?", "").strip()
    return bool(MATEMATIK_DESENI.match(temiz)) and any(c.isdigit() for c in temiz)


def matematik_hesapla(metin: str) -> str | None:
    try:
        ifade = metin.replace("=", "").replace("kaç eder", "").replace("?", "").strip()
        ifade = ifade.replace("x", "*").replace("×", "*").replace("÷", "/").replace(",", ".")
        agac = ast.parse(ifade, mode="eval").body
        sonuc = _guvenli_hesapla(agac)
        return f"{ifade.strip()} = {sonuc}"
    except Exception:
        return None


def ilgili_terimleri_bul(metin, esik=1.0, n=3):
    cols = get_collections()
    sonuc = cols["terminoloji"].query(query_texts=[metin], n_results=n)
    return [doc for doc, mesafe in zip(sonuc["documents"][0], sonuc["distances"][0]) if mesafe < esik]


def ceviri_hafizasindan_bul(metin: str, yon: str, esik: float = 0.08):
    cols = get_collections()
    hafiza = cols["ceviri_hafizasi"]

    sonuc = hafiza.query(query_texts=[metin], n_results=3, where={"yon": yon})
    if not sonuc["documents"] or not sonuc["documents"][0]:
        return None, None

    for doc, meta in zip(sonuc["documents"][0], sonuc["metadatas"][0]):
        if doc.strip().lower() == metin.strip().lower():
            return "exact", meta["hedef"]

    en_yakin_mesafe = sonuc["distances"][0][0]
    if en_yakin_mesafe < esik:
        return "yakin", sonuc["documents"][0][0], sonuc["metadatas"][0][0]["hedef"]

    return None, None


def cevir(metin, yon="en-tr", terim_kullan=True, max_tokens=200):
    hafiza_sonucu = ceviri_hafizasindan_bul(metin, yon)
    if hafiza_sonucu[0] == "exact":
        return hafiza_sonucu[1]

    model, tokenizer = modeli_yukle()
    talimat = "Aşağıdaki İngilizce metni Türkçeye çevir." if yon == "en-tr" else "Aşağıdaki Türkçe metni İngilizceye çevir."

    baglam = ""
    if terim_kullan:
        terimler = ilgili_terimleri_bul(metin)
        if terimler:
            baglam += "İlgili terimler:\n" + "\n".join(terimler) + "\n\n"


    girdi = f"{baglam}{metin}" if baglam else metin
    text = f"<start_of_turn>user\n{talimat}\n\n{girdi}<end_of_turn>\n<start_of_turn>model\n"

    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    outputs = model.generate(
        **inputs,
        max_new_tokens=max_tokens,
        do_sample=False,
        eos_token_id=_durma_tokenlari(tokenizer),
        pad_token_id=tokenizer.eos_token_id,
        suppress_tokens=yasakli_token_idlerini_hesapla(tokenizer),
    )
    sonuc = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

    ceviriyi_hafizaya_kaydet(metin, sonuc, yon)
    return sonuc



def ceviriyi_hafizaya_kaydet(kaynak, hedef, yon):
    cols = get_collections()
    hafiza = cols["ceviri_hafizasi"]
    kararli_hash = hashlib.md5(f"{kaynak}_{yon}".encode("utf-8")).hexdigest()
    kayit_id = f"ceviri_{kararli_hash}"
    hafiza.upsert(ids=[kayit_id], documents=[kaynak], metadatas=[{"hedef": hedef, "yon": yon}])


def cumlelere_bol(paragraf: str) -> list[str]:
    cumleler = re.split(r'(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜ0-9])', paragraf.strip())
    parcalar = []
    for c in cumleler:
        kelimeler = c.split()
        if len(kelimeler) <= 35:
            parcalar.append(c.strip())
        else:
            alt_parcalar = re.split(r',\s+', c)
            gecici = []
            for ap in alt_parcalar:
                gecici.append(ap.strip())
                if sum(len(g.split()) for g in gecici) >= 25:
                    parcalar.append(", ".join(gecici))
                    gecici = []
            if gecici:
                parcalar.append(", ".join(gecici))
    return [p.strip() for p in parcalar if p.strip()]


def metni_cevir(metin: str, yon: str = None, ilerleme_callback=None) -> str:
    if yon is None:
        kaynak_dil = dil_algila(metin[:500])
        yon = "tr-en" if kaynak_dil == "tr" else "en-tr"

    paragraflar = [p.strip() for p in metin.split("\n") if p.strip()]
    if not paragraflar:
        return ""

    tum_cumleler = []
    for p in paragraflar:
        tum_cumleler.extend(cumlelere_bol(p))
        tum_cumleler.append(None)

    cevrilmis_paragraflar, guncel = [], []
    toplam = sum(1 for c in tum_cumleler if c is not None)
    sayac = 0

    for c in tum_cumleler:
        if c is None:
            if guncel:
                cevrilmis_paragraflar.append(" ".join(guncel))
                guncel = []
            continue
        sayac += 1
        if ilerleme_callback:
            ilerleme_callback(sayac, toplam)
        tahmini_token = min(int(len(c.split()) * 3) + 40, 180)
        guncel.append(cevir(c, yon=yon, terim_kullan=True, max_tokens=tahmini_token))

    if guncel:
        cevrilmis_paragraflar.append(" ".join(guncel))
    return "\n\n".join(cevrilmis_paragraflar)


def soru_cevapla(mesaj, max_tokens=300):
    cols = get_collections()

    if matematik_ifadesi_mi(mesaj):
        sonuc = matematik_hesapla(mesaj)
        if sonuc:
            return sonuc

    if soru_niteliginde_mi(mesaj):
        belge_sonuc = cols["belgeler"].query(query_texts=[mesaj], n_results=3)
        if belge_sonuc["documents"] and belge_sonuc["documents"][0]:
            ilgili = [d for d, m in zip(belge_sonuc["documents"][0], belge_sonuc["distances"][0]) if m < 0.6]
            if ilgili:
                return f"Yüklediğin belgede bulduğum ilgili bölüm:\n\n{ilgili[0][:500]}"

        web_sonuclari_1 = web_ara(mesaj, n=5)
        web_sonuclari_2 = web_ara(mesaj, n=5)
        web_sonuclari = web_sonuclari_1 + web_sonuclari_2
        web_sonuclari = [s for s in web_sonuclari if alakali_mi(mesaj, s)]
        web_sonuclari = [s for s in web_sonuclari if not bilgi_degeri_dusuk_mu(s)]
        web_sonuclari.sort(key=lambda s: web_sonuclari_1.count(s) + web_sonuclari_2.count(s) > 1, reverse=True)

        wiki_sonuclari = [s for s in web_sonuclari if "vikipedi" in s.lower() or "wikipedia" in s.lower()]
        if wiki_sonuclari:
            web_sonuclari = wiki_sonuclari

        if web_sonuclari:
            return f"Bulduğum bilgi:\n\n{web_sonuclari[0]}"
        else:
            return "Bu konuda güvenilir bir bilgi bulamadım."

    model, tokenizer = modeli_yukle()
    text = f"<start_of_turn>user\n{mesaj}<end_of_turn>\n<start_of_turn>model\n"
    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    outputs = model.generate(
        **inputs,
        max_new_tokens=max_tokens,
        do_sample=False,
        eos_token_id=_durma_tokenlari(tokenizer),
        pad_token_id=tokenizer.eos_token_id,
        suppress_tokens=yasakli_token_idlerini_hesapla(tokenizer),
    )
    return tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)


def mesaji_isle(metin: str) -> str:
    if ceviri_istegi_mi(metin):
        icerik = cevrilecek_icerigi_cikar(metin)
        if not icerik:
            return "Çevirmemi istediğin metni de yazar mısın?"
        return metni_cevir(icerik)
    return soru_cevapla(metin)