import re
import requests

def sehir_cikar(mesaj: str) -> str | None:
    kelimeler = mesaj.replace("'", "").split()
    for k in kelimeler:
        if re.search(r'(da|de|ta|te)$', k, re.IGNORECASE) and len(k) > 4:
            govde = re.sub(r'(da|de|ta|te)$', '', k, flags=re.IGNORECASE)
            if govde[:1].isupper():
                return govde
    for i, k in enumerate(kelimeler):
        if i > 0 and k[:1].isupper():
            return k
    return None


def hava_durumu_getir(sehir: str) -> str | None:
    try:
        geo_url = "https://geocoding-api.open-meteo.com/v1/search"
        geo_r = requests.get(geo_url, params={"name": sehir, "count": 1, "language": "tr"}, timeout=10)
        geo_r.raise_for_status()
        sonuclar = geo_r.json().get("results")
        if not sonuclar:
            return None
        lat, lon, bulunan_isim = sonuclar[0]["latitude"], sonuclar[0]["longitude"], sonuclar[0].get("name", sehir)

        hava_url = "https://api.open-meteo.com/v1/forecast"
        hava_r = requests.get(
            hava_url,
            params={"latitude": lat, "longitude": lon, "current": "temperature_2m,weather_code", "timezone": "auto"},
            timeout=10,
        )
        hava_r.raise_for_status()
        sicaklik = hava_r.json().get("current", {}).get("temperature_2m")
        if sicaklik is None:
            return None
        return f"{bulunan_isim} için güncel sıcaklık: {sicaklik}°C"
    except Exception as e:
        print(f"[DEBUG] Hava durumu hatası: {e}")
        return None