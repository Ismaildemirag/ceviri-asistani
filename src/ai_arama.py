import json
import threading
import re as _re
from langdetect import detect, LangDetectException
from config import GEMINI_API_KEY, GEMINI_MODEL, TAVILY_API_KEY, GROQ_API_KEY, GROQ_MODEL

_tavily_client = None
_gemini_client = None
_groq_client = None


def _tavily():
    global _tavily_client
    if _tavily_client is None and TAVILY_API_KEY:
        from tavily import TavilyClient
        _tavily_client = TavilyClient(api_key=TAVILY_API_KEY)
    return _tavily_client


def _gemini():
    global _gemini_client
    if _gemini_client is None and GEMINI_API_KEY:
        from google import genai
        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    return _gemini_client


def _groq():
    global _groq_client
    if _groq_client is None and GROQ_API_KEY:
        from groq import Groq
        _groq_client = Groq(api_key=GROQ_API_KEY)
    return _groq_client


def _zaman_asimili_calistir(fn, sure, *args, **kwargs):
    kutu = {}

    def hedef():
        try:
            kutu["deger"] = fn(*args, **kwargs)
        except Exception as e:
            kutu["hata"] = e

    t = threading.Thread(target=hedef, daemon=True)
    t.start()
    t.join(timeout=sure)
    if t.is_alive():
        print(f"[UYARI] {fn.__name__} zaman aşımına uğradı ({sure}s)")
        return None
    if "hata" in kutu:
        print(f"[UYARI] {fn.__name__} hata verdi: {kutu['hata']}")
        return None
    return kutu.get("deger")


def _groq_ham_cagri(prompt: str, max_tokens: int, temperature: float = 0.7):
    client = _groq()
    if not client:
        return None
    tamamlanan = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return (tamamlanan.choices[0].message.content or "").strip() or None


def _gemini_ham_cagri_duz(prompt: str, max_tokens: int):
    client = _gemini()
    if not client:
        return None
    yanit = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    return (yanit.text or "").strip() or None


def _llm_metin_uret(prompt: str, max_tokens: int = 500, kaynak_etiketi: dict = None,
                    temperature: float = 0.7, zaman_asimi: int = 10) -> str | None:
    sonuc = _zaman_asimili_calistir(_groq_ham_cagri, zaman_asimi, prompt, max_tokens, temperature)
    if sonuc:
        if kaynak_etiketi is not None:
            kaynak_etiketi["saglayici"] = "groq"
        return sonuc

    sonuc = _zaman_asimili_calistir(_gemini_ham_cagri_duz, max(zaman_asimi, 15), prompt, max_tokens)
    if sonuc:
        if kaynak_etiketi is not None:
            kaynak_etiketi["saglayici"] = "gemini"
        return sonuc

    return None


def _metin_turkce_mi(metin: str) -> bool:
    try:
        return detect(metin[:300]) == "tr"
    except LangDetectException:
        return False


def _tavily_ham_cagri(sorgu: str, n: int):
    client = _tavily()
    if not client:
        return None
    sonuc = client.search(query=sorgu, max_results=n)
    kaynaklar = [
        {"baslik": r.get("title", ""), "icerik": r.get("content", ""), "url": r.get("url", "")}
        for r in sonuc.get("results", [])
        if r.get("content") and "youtube.com" not in r.get("url", "") and "youtu.be" not in r.get("url", "")
    ]
    if not kaynaklar:
        return None
    kaynaklar.sort(key=lambda k: 0 if _metin_turkce_mi(k["icerik"]) else 1)
    return kaynaklar


def tavily_ara(sorgu: str, n: int = 5):
    return _zaman_asimili_calistir(_tavily_ham_cagri, 12, sorgu, n)


_CEVIRI_KOMUT_DESENI = _re.compile(r'\b(çevir|tercüme|translate)\b', _re.IGNORECASE)


def _gecmisi_metne_cevir(mesaj_gecmisi: list) -> str:
    if not mesaj_gecmisi:
        return ""

    gecerli = []
    son_mesajlar = mesaj_gecmisi[-8:]
    i = 0
    while i < len(son_mesajlar):
        m = son_mesajlar[i]
        if m["rol"] == "kullanici" and _CEVIRI_KOMUT_DESENI.search(m["icerik"]):
            i += 2  
            continue
        gecerli.append(m)
        i += 1

    if not gecerli:
        return ""

    satirlar = []
    for m in gecerli[-6:]:
        rol = "Kullanıcı" if m["rol"] == "kullanici" else "Asistan"
        satirlar.append(f"{rol}: {m['icerik'][:200]}")
    return "Önceki konuşma:\n" + "\n".join(satirlar) + "\n\n"



def llm_ile_yanitla(soru: str, kaynaklar: list, mesaj_gecmisi: list = None) -> str | None:
    if not kaynaklar:
        return None

    baglam = "\n\n".join(
        f"[Kaynak {i+1}: {k['baslik']}]\n{k['icerik'][:2000]}" for i, k in enumerate(kaynaklar)
    )
    gecmis_metni = _gecmisi_metne_cevir(mesaj_gecmisi)

    prompt = (
        "Aşağıdaki kaynaklara dayanarak soruyu YANITLA. "
        "SADECE verilen kaynaklardaki bilgiyi kullan, kendi bilgini katma. "
        "ÇOK ÖNEMLİ: İlk cevabın TAM ve KAPSAMLI olsun - kullanıcının 'daha fazla açıkla' "
        "demesini bekleme, kaynaklarda bulduğun TÜM ilgili bilgiyi şimdi ver. "
        "Kullanıcı 'hepsini say/listele' gibi bir şey istiyorsa, kaynakta bulduğun "
        "TÜM öğeleri eksiksiz listele, kısaltma. "
        "ÇOK ÖNEMLİ: Kaynaklarda soruyu yanıtlayacak yeterli/ilgili bilgi YOKSA, "
        "cevabını TAM OLARAK şu satırla başlat: YETERSIZ_KAYNAK\n"
        "ardından nedenini kısaca açıkla. Kaynaklar sorunun konusuyla ilgiliyse normal yanıt ver. "
        "ÇOK ÖNEMLİ: Sadece sorulan sorunun cevabını ver ve bitir. Cevabın sonuna "
        "'bu kaynakta X hakkında bilgi bulunmamaktadır', 'bu bilgiler kaynakların tümünü "
        "kapsamaktadır' gibi kaynakların kapsamıyla ilgili açıklama/not EKLEME. "
        "Metnin içinde '(Kaynak 1)', 'verilen kaynaklara göre' gibi kaynak numarası veya "
        "kaynak referansı da kullanma. "
        "ÇOK ÖNEMLİ: Kaynaklar İngilizce olsa bile, cevabını SADECE Türkçe yaz. "
        "Soru önceki konuşmaya bir takip sorusuysa bunu dikkate al.\n\n"
        f"{gecmis_metni}Kaynaklar:\n{baglam}\n\nSoru: {soru}\n\nYanıt (Türkçe, tam ve kapsamlı):"
    )

    etiket = {}
    metin = _llm_metin_uret(prompt, max_tokens=4500, kaynak_etiketi=etiket, temperature=0.3)
    if not metin:
        return None

    if metin.strip().startswith("YETERSIZ_KAYNAK"):
        return metin.replace("YETERSIZ_KAYNAK", "").strip()

    print(f"[BİLGİ] Yanıt sağlayıcı: {etiket.get('saglayici', 'bilinmiyor')}")  # sadece konsol için
    en_iyi_kaynak = kaynaklar[0]
    return f"{metin}\n\nKaynak: {en_iyi_kaynak['baslik']} ({en_iyi_kaynak['url']})"


def gelismis_arama_cevapla(soru: str, mesaj_gecmisi: list = None, arama_sorgusu: str = None) -> str | None:
    sorgu = (arama_sorgusu or soru).strip() or soru
    kaynaklar = tavily_ara(sorgu)
    if not kaynaklar:
        return None

    cevap = llm_ile_yanitla(soru, kaynaklar, mesaj_gecmisi)
    if cevap:
        return cevap

    onceki_kaynak_url = None
    if mesaj_gecmisi:
        for m in reversed(mesaj_gecmisi):
            if m["rol"] == "asistan" and "Kaynak:" in m["icerik"]:
                onceki_kaynak_url = m["icerik"].split("Kaynak:")[-1].strip()
                break

    secilen = kaynaklar[0]
    if onceki_kaynak_url and secilen["url"] in onceki_kaynak_url and len(kaynaklar) > 1:
        secilen = kaynaklar[1]

    icerik_temiz = secilen["icerik"][:600].rsplit(".", 1)[0] + "."
    return f"Bulduğum bilgi:\n\n{icerik_temiz}\n\nKaynak: {secilen['baslik']} ({secilen['url']})"


NIYET_PROMPT = """Kullanıcının mesajını ve (varsa) önceki konuşmayı analiz et. SADECE şu JSON formatında yanıt ver, başka hiçbir şey yazma, markdown kullanma:

{{"niyet": "...", "icerik": "...", "hedef_dil": "...", "sehir": "...", "arama_sorgusu": "..."}}

niyet şunlardan biri olmalı:
- "ceviri": kullanıcı bir metni/kelimeyi/belgeyi başka dile çevirmemi istiyor
- "ozet": kullanıcı AÇIKÇA bir metni/belgeyi/görseli özetlememi istiyor
("özetle", "özetlesene", "kısaca anlat"). Sadece bir konu veya kişi adı yazması
(örn. "Atatürk'ün hayatı") özet isteği DEĞİLDİR, "soru_cevap"tır.
- "hava_durumu": kullanıcı bir şehrin hava durumunu/sıcaklığını soruyor
- "soru_cevap": kullanıcı faktüel bir bilgi/soru soruyor
- "sohbet": günlük konuşma, selamlaşma, teşekkür, muhabbet, görüş isteme.
DİKKAT: Önceki konuşmada bir bilgi sorusu/cevabı varsa ve mesaj onun devamı niteliğindeyse ("daha fazla açıkla", "devam et", "peki ya X", "biraz daha anlat", "hepsini söyle") bu SOHBET DEĞİLDİR, "soru_cevap" olarak sınıflandır.
- "matematik": basit bir aritmetik işlem

icerik: niyet "ceviri" ise çevrilecek asıl kelime/metni çıkar; mesajda somut bir metin YOKSA (örn. sadece "çevir" denmişse, aktif bir belge/görsel çevrilecekse) icerik'i BOŞ bırak (""). Diğer niyetlerde orijinal mesajı yaz.
hedef_dil: "ceviri" niyetinde "en" veya "tr", diğerlerinde "".
sehir: niyet "hava_durumu" ise şehir adı, diğerlerinde "".

arama_sorgusu: SADECE niyet "soru_cevap" ise doldur. Önceki konuşmaya bakarak:
- Mesaj önceki konuyla İLGİLİYSE (zamir, "o zaman", "peki ya", "hepsini", "daha fazla" gibi referans içeriyorsa) önceki konuyu da katarak TEK, net, kendi başına anlamlı bir arama sorgusu oluştur.
- Mesaj YENİ ve BAĞIMSIZ bir konuysa, önceki konuşmayı KATMA.
- Kullanıcı belirli bir kaynak/site adı belirttiyse bunu sorguya dahil et.
Not: Önceki konuşma sadece EN SON soru-cevap turunu içerir.
"daha fazla açıkla", "devam et" gibi referanslar yalnızca o en son konuya aittir, başka konuları karıştırma.
Önceki konuşma:
{gecmis}

Mesaj: "{mesaj}"
"""


def niyet_belirle(mesaj: str, mesaj_gecmisi: list = None, belge_aktif: bool = False) -> dict | None:
    gecmis_metni = _gecmisi_metne_cevir(mesaj_gecmisi) or "(yok)"
    belge_notu = (
        "\nÖNEMLİ: Kullanıcının az önce yüklediği bir belge/görsel VAR ve aktif. "
        "Kullanıcı somut bir metin belirtmeden bir işlem istiyorsa, bu O BELGE "
        "üzerinde yapılması isteniyordur; icerik alanını BOŞ bırak.\n"
        if belge_aktif else ""
    )
    prompt = NIYET_PROMPT.format(mesaj=mesaj.replace('"', "'"), gecmis=gecmis_metni) + belge_notu
    metin = _llm_metin_uret(prompt, max_tokens=300, temperature=0)
    if not metin:
        return None
    try:
        temiz = metin.strip("`").replace("json", "", 1).strip()
        return json.loads(temiz)
    except Exception as e:
        print(f"[UYARI] Niyet JSON parse hatası: {e}")
        return None


def llm_ozetle(metin: str) -> str | None:
    kisaltilmis = metin[:8000]
    prompt = (
        "Aşağıdaki metni 3-5 cümlede, akıcı bir Türkçeyle özetle. "
        "Sadece özeti yaz, giriş cümlesi ekleme.\n\n"
        f"Metin:\n{kisaltilmis}"
    )
    return _llm_metin_uret(prompt, max_tokens=400)


def llm_sohbet(mesaj: str, mesaj_gecmisi: list = None) -> str | None:
    gecmis_metni = _gecmisi_metne_cevir(mesaj_gecmisi)
    prompt = (
        "Sen yardımsever ve samimi bir Türkçe asistansın. Kullanıcıyla doğal, "
        "kısa ve net konuş. Bilmediğin bir şeyi uydurma.\n\n"
        f"{gecmis_metni}Kullanıcı: {mesaj}\n\nAsistan:"
    )
    return _llm_metin_uret(prompt, max_tokens=500, temperature=0.7) 