from flask import Flask, render_template, request, jsonify
from pathlib import Path
import tempfile, threading

from translate import mesaji_isle, ceviri_istegi_mi, metni_cevir, soru_cevapla, ceviriyi_hafizaya_kaydet
from belge_yukle import metni_oku
from gorsel_oku import gorselden_metin_cikar
from ses_tanit import sesten_metin_cikar

MODEL_KILIDI = threading.Lock()
app = Flask(__name__)


def gorsel_niyeti_belirle(not_metni: str) -> str | None:
    kucuk = not_metni.lower()
    if any(k in kucuk for k in ["çevir", "tercüme", "translate"]):
        return "cevir"
    if any(k in kucuk for k in ["ne yazıyor", "oku", "aktar"]):
        return "oku"
    if any(k in kucuk for k in ["çöz", "hesapla", "kaç eder", "sonucu"]):
        return "coz"
    return None


@app.route("/")
def anasayfa():
    return render_template("index.html")


@app.route("/api/mesaj", methods=["POST"])
def mesaj_gonder():
    veri = request.get_json()
    metin = veri.get("metin", "").strip()
    if not metin:
        return jsonify({"hata": "Boş mesaj"}), 400

    with MODEL_KILIDI:
        cevap = mesaji_isle(metin)
    return jsonify({"cevap": cevap})


@app.route("/api/dosya", methods=["POST"])
def dosya_gonder():
    dosya = request.files.get("dosya")
    kullanici_notu = request.form.get("not", "").strip()
    if not dosya:
        return jsonify({"hata": "Dosya yok"}), 400

    uzanti = Path(dosya.filename).suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=uzanti) as tmp:
        dosya.save(tmp.name)
        tmp_yolu = tmp.name

    with MODEL_KILIDI:
        if uzanti in [".png", ".jpg", ".jpeg"]:
            dosya_metni = gorselden_metin_cikar(tmp_yolu)

            if not dosya_metni.strip():
                return jsonify({"cevap": "Görselde okunabilir bir metin bulamadım."})

            niyet = gorsel_niyeti_belirle(kullanici_notu) if kullanici_notu else "oku"
            if niyet == "cevir":
                cevap = metni_cevir(dosya_metni)
            elif niyet == "coz":
                cevap = soru_cevapla(dosya_metni)
            else:
                cevap = f"Görselde şu yazıyor:\n\n{dosya_metni}"
            return jsonify({"cevap": cevap})

        dosya_metni = metni_oku(tmp_yolu)
        if not dosya_metni.strip():
            return jsonify({"cevap": "Bu dosyadan okunabilir bir içerik çıkaramadım."})

        if kullanici_notu and ceviri_istegi_mi(kullanici_notu):
            cevap = metni_cevir(dosya_metni)
        else:
            soru_girdisi = f"{kullanici_notu}\n\n{dosya_metni}" if kullanici_notu else dosya_metni
            cevap = soru_cevapla(soru_girdisi)
        return jsonify({"cevap": cevap})


@app.route("/api/ses", methods=["POST"])
def ses_gonder():
    ses = request.files.get("ses")
    if not ses:
        return jsonify({"hata": "Ses yok"}), 400

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        ses.save(tmp.name)
        ses_yolu = tmp.name

    with MODEL_KILIDI:
        metin = sesten_metin_cikar(ses_yolu)
    return jsonify({"metin": metin})


@app.route("/api/duzelt", methods=["POST"])
def ceviri_duzelt():
    veri = request.get_json()
    kaynak = veri.get("kaynak", "").strip()
    dogru_hedef = veri.get("dogru_hedef", "").strip()
    yon = veri.get("yon", "en-tr")

    if not kaynak or not dogru_hedef:
        return jsonify({"hata": "Eksik bilgi"}), 400

    with MODEL_KILIDI:
        ceviriyi_hafizaya_kaydet(kaynak, dogru_hedef, yon)
    return jsonify({"basari": True})


if __name__ == "__main__":
    app.run(port=5000, threaded=True, use_reloader=False, debug=True)