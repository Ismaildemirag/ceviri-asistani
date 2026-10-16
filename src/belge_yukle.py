from pathlib import Path
from pypdf import PdfReader
from docx import Document as DocxDocument


def metni_oku(dosya_yolu: str) -> str:
    yol = Path(dosya_yolu)
    uzanti = yol.suffix.lower()

    if uzanti == ".pdf":
        reader = PdfReader(str(yol))
        return "\n".join(sayfa.extract_text() or "" for sayfa in reader.pages)

    elif uzanti == ".docx":
        doc = DocxDocument(str(yol))
        return "\n".join(p.text for p in doc.paragraphs)

    elif uzanti == ".txt":
        return yol.read_text(encoding="utf-8")

    else:
        raise ValueError(f"Desteklenmeyen dosya türü: {uzanti}")