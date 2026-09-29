from faster_whisper import WhisperModel

_model = None

def _model_yukle():
    global _model
    if _model is None:
        _model = WhisperModel("small", device="cuda", compute_type="float16")
    return _model

def sesten_metin_cikar(dosya_yolu: str) -> str:
    model = _model_yukle()
    segmentler, _ = model.transcribe(dosya_yolu, language=None)  # dil otomatik algılanır
    return " ".join(s.text for s in segmentler).strip()