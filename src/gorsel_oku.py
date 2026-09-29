import easyocr

_reader = None

def _reader_yukle():
    global _reader
    if _reader is None:
        _reader = easyocr.Reader(['tr', 'en'], gpu=True)
    return _reader

def gorselden_metin_cikar(dosya_yolu: str) -> str:
    reader = _reader_yukle()
    sonuclar = reader.readtext(dosya_yolu, detail=0)
    return " ".join(sonuclar)