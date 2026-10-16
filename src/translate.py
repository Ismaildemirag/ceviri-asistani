import re
import hashlib
import ast, operator
from unsloth import FastLanguageModel
import torch
from langdetect import detect, LangDetectException

from rag_setup import get_collections
from config import LOCAL_MODEL_PATH, MAX_SEQ_LENGTH
from web_arama import web_ara, alakali_mi, bilgi_degeri_dusuk_mu
from belge_hafizasi import belgede_ara, aktif_belge_var_mi, numarali_cumle_istegi_mi, numarali_cumleyi_getir, ham_metni_al
from ai_arama import gelismis_arama_cevapla, niyet_belirle, llm_ozetle, llm_sohbet
from hava_durumu import hava_durumu_getir, sehir_cikar

HAVA_DESENI = re.compile(r'\b(hava|derece|sıcaklık)\b', re.IGNORECASE)

_model = None
_tokenizer = None

YASAKLI_SCRIPT_DESENI = re.compile(
    r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af\u0900-\u097f\u0600-\u06ff\u0370-\u03ff\u0400-\u04ff]'
)
_yasakli_token_id_cache = None


def yasakli_token_idlerini_hesapla(tokenizer):
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


TRIGGER_SUFFIX = re.compile(
    r'\s*(bunu\s+|şunu\s+|lütfen\s+)?'
    r'(çevir(sene|iver|ir\s+misin|ebilir\s+misin|meni)?|tercüme\s+et(er\s+misin)?|translate(\s+this)?)'
    r'\s*[.!?]?\s*$',
    re.IGNORECASE
)


def ceviri_istegi_mi(metin: str) -> bool:
    return bool(TRIGGER_SUFFIX.search(metin))


def cevrilecek_icerigi_cikar(metin: str) -> str:
    return TRIGGER_SUFFIX.sub('', metin).strip()


SORU_KELIMELERI = re.compile(
    r'(kimdir|kim\b|nedir|ne\b|nerede|ne zaman|kaç|hangi|nasıl|neden|niçin|'
    r'söyle|anlat|listele|sırala|göster|bahset|açıkla|'
    r'what|who|where|when|why|how|which)',
    re.IGNORECASE
)

SOHBET_KELIMELERI = {
    "naber", "selam", "merhaba", "teşekkür", "teşekkürler", "sağol",
    "görüşürüz", "nasılsın", "iyiyim", "kötüyüm", "hoşçakal",
}


def soru_niteliginde_mi(metin: str) -> bool:
    kelimeler = metin.strip().split()
    if not kelimeler:
        return False
    kucuk = metin.lower()
    if len(kelimeler) <= 3 and any(k in kucuk for k in SOHBET_KELIMELERI):
        return False
    if SORU_KELIMELERI.search(metin) or metin.strip().endswith("?"):
        return True
    if 1 <= len(kelimeler) <= 20:
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


OZET_DESENI = re.compile(r'\b(özetle|özet|özetler misin|kısaca anlat|kısaca özetle)\b', re.IGNORECASE)


def ozet_istegi_mi(metin: str) -> bool:
    return bool(OZET_DESENI.search(metin))


def metni_ozetle(metin: str) -> str:
    llm_sonuc = llm_ozetle(metin)
    if llm_sonuc:
        return llm_sonuc

    model, tokenizer = modeli_yukle()
    kisaltilmis = " ".join(metin.split()[:300])
    text = f"<start_of_turn>user\nAşağıdaki metni 3 cümlede özetle:\n\n{kisaltilmis}<end_of_turn>\n<start_of_turn>model\n"
    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    outputs = model.generate(
        **inputs, max_new_tokens=150, do_sample=False,
        eos_token_id=_durma_tokenlari(tokenizer),
        pad_token_id=tokenizer.eos_token_id,
        suppress_tokens=yasakli_token_idlerini_hesapla(tokenizer),
    )
    sonuc = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    return f"{sonuc}\n\n(Not: AI servisleri şu an meşgul, bu özet sınırlı kaliteli yerel model ile üretildi.)"


def sohbet_cevapla(mesaj: str, mesaj_gecmisi=None, max_tokens: int = 150) -> str:
    cevap = llm_sohbet(mesaj, mesaj_gecmisi)
    if cevap:
        return cevap

    model, tokenizer = modeli_yukle()
    text = f"<start_of_turn>user\n{mesaj}<end_of_turn>\n<start_of_turn>model\n"
    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    outputs = model.generate(
        **inputs, max_new_tokens=max_tokens, do_sample=False,
        repetition_penalty=1.2, no_repeat_ngram_size=3,
        eos_token_id=_durma_tokenlari(tokenizer),
        pad_token_id=tokenizer.eos_token_id,
        suppress_tokens=yasakli_token_idlerini_hesapla(tokenizer),
    )
    return tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)


def soru_cevapla(mesaj, mesaj_gecmisi=None, arama_sorgusu=None, max_tokens=300):
    if matematik_ifadesi_mi(mesaj):
        sonuc = matematik_hesapla(mesaj)
        if sonuc:
            return sonuc

    if HAVA_DESENI.search(mesaj):
        sehir = sehir_cikar(mesaj)
        if sehir:
            hava_sonuc = hava_durumu_getir(sehir)
            if hava_sonuc:
                return hava_sonuc

    if aktif_belge_var_mi():
        cumle_no = numarali_cumle_istegi_mi(mesaj)
        if cumle_no:
            cumle = numarali_cumleyi_getir(cumle_no)
            if cumle:
                return f"Belgenin {cumle_no}. cümlesi:\n\n{cumle}"
            return f"Belgede {cumle_no}. bir cümle bulamadım."

        belge_sonuclari = belgede_ara(mesaj)
        if belge_sonuclari:
            en_ilgili_parca = belge_sonuclari[0][0]
            return f"Yüklediğin belgede bulduğum ilgili bölüm:\n\n{en_ilgili_parca}"

    if arama_sorgusu or soru_niteliginde_mi(mesaj):
        etkin_sorgu = arama_sorgusu or mesaj

        gelismis_cevap = gelismis_arama_cevapla(mesaj, mesaj_gecmisi, arama_sorgusu=etkin_sorgu)
        if gelismis_cevap:
            return gelismis_cevap

        web_sonuclari = web_ara(etkin_sorgu, n=5)
        web_sonuclari = [s for s in web_sonuclari if alakali_mi(etkin_sorgu, s)]
        web_sonuclari = [s for s in web_sonuclari if not bilgi_degeri_dusuk_mu(s)]

        wiki_sonuclari = [s for s in web_sonuclari if "vikipedi" in s.lower() or "wikipedia" in s.lower()]
        if wiki_sonuclari:
            web_sonuclari = wiki_sonuclari

        if web_sonuclari:
            return f"Bulduğum bilgi:\n\n{web_sonuclari[0]}"
        else:
            return "Bu konuda güvenilir bir bilgi bulamadım."

    return sohbet_cevapla(mesaj, mesaj_gecmisi)


_TAKIP_SORUSU_DESENI = re.compile(
    r"^(?:daha\s+fazla(?:\s+(?:açıkla|anlat|bilgi\s+ver))?|"
    r"biraz\s+daha(?:\s+(?:açıkla|anlat|anlatır\s+mısın))?|"
    r"devam\s+et|devam\s+etsene|"
    r"en\s+iyisi\s+hangisiydi|hangisi\s+daha\s+iyi(?:ydi)?|"
    r"peki\s+ya\s+.+|neden|niçin|nasıl\s+yani|"
    r"bunu\s+(?:açıkla|anlat|detaylandır)|"
    r"hepsini\s+(?:söyle|anlat|listele)|"
    r"biraz\s+daha\s+detay(?:lı)?(?:\s+anlat)?)[.!?…]*$",
    re.IGNORECASE,
)


def _takip_sorusu_sorgusu(metin: str, mesaj_gecmisi=None):
    """Kısa takip sorusunu son bağımsız kullanıcı konusuna bağlar."""
    temiz = metin.strip()
    if not temiz or len(temiz.split()) > 8 or ceviri_istegi_mi(temiz):
        return None
    if not _TAKIP_SORUSU_DESENI.fullmatch(temiz):
        return None
    for kayit in reversed(mesaj_gecmisi or []):
        if kayit.get("rol") != "kullanici":
            continue
        onceki = (kayit.get("icerik") or "").strip()
        if not onceki or ceviri_istegi_mi(onceki):
            continue
        if _TAKIP_SORUSU_DESENI.fullmatch(onceki):
            continue
        return f"{onceki[:180]} {temiz}"
    return None


def mesaji_isle(metin: str, mesaj_gecmisi=None) -> str:
    # Belge/görsel çevirisi ve özetleme isteklerini mevcut akışta bırak.
    if not aktif_belge_var_mi() or not (ceviri_istegi_mi(metin) or ozet_istegi_mi(metin)):
        baglamli_sorgu = _takip_sorusu_sorgusu(metin, mesaj_gecmisi)
        if baglamli_sorgu:
            return soru_cevapla(metin, mesaj_gecmisi=mesaj_gecmisi, arama_sorgusu=baglamli_sorgu)

    niyet_sonuc = niyet_belirle(metin, mesaj_gecmisi, belge_aktif=aktif_belge_var_mi())

    if niyet_sonuc:
        niyet = niyet_sonuc.get("niyet")
        icerik = (niyet_sonuc.get("icerik") or metin).strip()

        if niyet == "ceviri":
            if aktif_belge_var_mi():
                cumle_no = numarali_cumle_istegi_mi(metin)
                if cumle_no:
                    cumle = numarali_cumleyi_getir(cumle_no)
                    if cumle:
                        return metni_cevir(cumle) 
                    return f"Belgede {cumle_no}. bir cümle bulamadım."

                if len(metin.split()) <= 4 or not icerik:
                    tam_metin = ham_metni_al()
                    if tam_metin:
                        return metni_cevir(tam_metin)

            if icerik:
                return metni_cevir(icerik)

            return "Çevirmemi istediğin metni de yazar mısın?"

        if niyet == "ozet":
            if aktif_belge_var_mi() and len(icerik.split()) < 15:
                tam_metin = ham_metni_al()
                if tam_metin:
                    return metni_ozetle(tam_metin)

            if len(icerik.split()) >= 15:
                return metni_ozetle(icerik)

            if ozet_istegi_mi(metin) and mesaj_gecmisi:
                son_cevaplar = [m["icerik"] for m in mesaj_gecmisi if m["rol"] == "asistan"]
                if son_cevaplar:
                    return metni_ozetle(son_cevaplar[-1])

            return soru_cevapla(metin, mesaj_gecmisi=mesaj_gecmisi)

        if niyet == "hava_durumu":
            sehir = (niyet_sonuc.get("sehir") or "").strip() or sehir_cikar(metin)
            if sehir:
                hava_sonuc = hava_durumu_getir(sehir)
                if hava_sonuc:
                    return hava_sonuc

        if niyet == "sohbet":
            return sohbet_cevapla(metin, mesaj_gecmisi)

        if niyet == "matematik":
            sonuc = matematik_hesapla(metin)
            if sonuc:
                return sonuc

        if niyet == "soru_cevap":
            arama_sorgusu = (niyet_sonuc.get("arama_sorgusu") or "").strip() or None
            return soru_cevapla(metin, mesaj_gecmisi=mesaj_gecmisi, arama_sorgusu=arama_sorgusu)

    if aktif_belge_var_mi():
        cumle_no = numarali_cumle_istegi_mi(metin)
        if cumle_no and ceviri_istegi_mi(metin):
            cumle = numarali_cumleyi_getir(cumle_no)
            if cumle:
                return metni_cevir(cumle)
            return f"Belgede {cumle_no}. bir cümle bulamadım."

        if ozet_istegi_mi(metin):
            tam_metin = ham_metni_al()
            if tam_metin:
                return metni_ozetle(tam_metin)

        if ceviri_istegi_mi(metin) and re.search(r'\b(belge|belgeyi|metni|metnin|dosyayı)\b', metin.lower()):
            tam_metin = ham_metni_al()
            if tam_metin:
                return metni_cevir(tam_metin)

    if ceviri_istegi_mi(metin):
        icerik = cevrilecek_icerigi_cikar(metin)
        if not icerik and aktif_belge_var_mi():
            tam_metin = ham_metni_al()
            if tam_metin:
                return metni_cevir(tam_metin)
        if not icerik:
            return "Çevirmemi istediğin metni de yazar mısın?"
        return metni_cevir(icerik)

    return soru_cevapla(metin, mesaj_gecmisi=mesaj_gecmisi)