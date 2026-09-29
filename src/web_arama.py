from ddgs import DDGS
import requests

HEADERS = {"User-Agent": "CeviriAsistaniProjesi/1.0 (personal project; contact: ornek@mail.com)"}


def web_ara(sorgu: str, n: int = 3) -> list[str]:
    for deneme in range(2):
        try:
            with DDGS(timeout=20) as ddgs:
                sonuclar = list(ddgs.text(sorgu, max_results=n))
            return [f"{r['title']}: {r['body']}" for r in sonuclar if r.get("body")]
        except Exception as e:
            print(f"[DEBUG] Web arama hatası (deneme {deneme + 1}): {e}")
    return []


def alakali_mi(sorgu: str, snippet: str) -> bool:
    durak_kelimeler = {"kaç", "yılında", "ne", "zaman", "nedir", "kimdir", "nasıl", "hangi"}
    sorgu_kelimeleri = [k.lower() for k in sorgu.split() if len(k) > 3 and k.lower() not in durak_kelimeler]
    if not sorgu_kelimeleri:
        return True

    sorgu_bosluksuz = "".join(sorgu.lower().split())
    snippet_bosluksuz = "".join(snippet.lower().split())
    if sorgu_bosluksuz in snippet_bosluksuz:
        return True

    snippet_kucuk = snippet.lower()
    eslesen = sum(1 for k in sorgu_kelimeleri if k in snippet_kucuk)
    return eslesen / len(sorgu_kelimeleri) >= 0.5


DUSUK_DEGER_KELIMELERI = ["takipçi", "followers", "following", "gönderi", "posts"]


def bilgi_degeri_dusuk_mu(snippet: str) -> bool:
    kucuk = snippet.lower()
    return sum(1 for k in DUSUK_DEGER_KELIMELERI if k in kucuk) >= 2