import json
import time
from collections import defaultdict
from pathlib import Path

from ai_arama import niyet_belirle

YOL = Path(__file__).resolve().parent.parent / "tests" / "niyet_testleri.json"


def main():
    testler = json.loads(YOL.read_text(encoding="utf-8"))
    dogru = 0
    basarisiz = 0
    kategori = defaultdict(lambda: [0, 0])

    for t in testler:
        sonuc = niyet_belirle(t["input"], t.get("gecmis"), belge_aktif=t.get("belge_aktif", False))
        tahmin = sonuc.get("niyet") if sonuc else "BASARISIZ"
        beklenen = t["beklenen_niyet"]
        ok = tahmin == beklenen

        kategori[beklenen][1] += 1
        if ok:
            dogru += 1
            kategori[beklenen][0] += 1
        if tahmin == "BASARISIZ":
            basarisiz += 1

        print(f"{'OK  ' if ok else 'HATA'} '{t['input'][:60]}' -> beklenen: {beklenen}, gelen: {tahmin}")
        time.sleep(2.5)

    toplam = len(testler)
    print(f"\nGenel: {dogru}/{toplam} doğru (%{dogru / toplam * 100:.0f})")
    if basarisiz:
        print(f"Not: {basarisiz} istek sağlayıcı hatası/zaman aşımı yüzünden başarısız oldu.")
    for ad, (d, n) in sorted(kategori.items()):
        print(f"  {ad}: {d}/{n}")


if __name__ == "__main__":
    main()