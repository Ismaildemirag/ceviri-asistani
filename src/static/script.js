const mesajAlani = document.getElementById("mesaj-alani");
const metinInput = document.getElementById("metin-input");
const gonderBtn = document.getElementById("gonder-btn");
const dosyaBtn = document.getElementById("dosya-btn");
const dosyaInput = document.getElementById("dosya-input");
const mikBtn = document.getElementById("mik-btn");

let secilenDosya = null;

function mesajEkle(metin, kimden) {
  const div = document.createElement("div");
  div.className = `mesaj ${kimden}`;
  div.textContent = metin;
  mesajAlani.appendChild(div);
  mesajAlani.scrollTop = mesajAlani.scrollHeight;
}

metinInput.addEventListener("input", () => {
  metinInput.style.height = "auto";
  metinInput.style.height = metinInput.scrollHeight + "px";
});

function durumTahminEt(metin) {
  const kucuk = metin.toLowerCase();
  if (/çevir|tercüme|translate/.test(kucuk)) return "Çevriliyor...";
  return "Düşünüyor...";
}

async function gonder() {
  const metin = metinInput.value.trim();

  if (secilenDosya) {
    const dosya = secilenDosya;
    secilenDosya = null;
    dosyaInput.value = "";
    dosyaBtn.textContent = "📎";

    mesajEkle(`📄 ${dosya.name}` + (metin ? ` — ${metin}` : ""), "kullanici");
    metinInput.value = "";
    metinInput.style.height = "auto";

    const uzanti = dosya.name.split(".").pop().toLowerCase();
    let durumMesaji = ["png", "jpg", "jpeg"].includes(uzanti) ? "Görsel okunuyor..." : "Belge inceleniyor...";
    if (/çevir|tercüme|translate/.test(metin.toLowerCase())) durumMesaji = "Çevriliyor...";

    mesajEkle(durumMesaji, "asistan");
    const yukleniyorEl = mesajAlani.lastChild;

    const formData = new FormData();
    formData.append("dosya", dosya);
    formData.append("not", metin);

    const yanit = await fetch("/api/dosya", { method: "POST", body: formData });
    const veri = await yanit.json();
    yukleniyorEl.textContent = veri.cevap || veri.hata;
    return;
  }

  if (!metin) return;
  mesajEkle(metin, "kullanici");
  metinInput.value = "";
  metinInput.style.height = "auto";

  mesajEkle(durumTahminEt(metin), "asistan");
  const yukleniyorEl = mesajAlani.lastChild;

  const yanit = await fetch("/api/mesaj", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ metin }),
  });
  const veri = await yanit.json();
  yukleniyorEl.textContent = veri.cevap || veri.hata;
}

gonderBtn.addEventListener("click", gonder);
metinInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    gonder();
  }
});

dosyaBtn.addEventListener("click", () => dosyaInput.click());
dosyaInput.addEventListener("change", () => {
  const dosya = dosyaInput.files[0];
  if (!dosya) return;
  secilenDosya = dosya;
  dosyaBtn.textContent = "📎✓";  // dosya seçildiğini görsel olarak belirt
  metinInput.focus();
});

// --- Mikrofon (aynı kalıyor) ---
let mediaRecorder, kayitParcalari = [];

mikBtn.addEventListener("click", async () => {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    mikBtn.classList.remove("kayit-aktif");
    return;
  }

  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  mediaRecorder = new MediaRecorder(stream);
  kayitParcalari = [];

  mediaRecorder.ondataavailable = (e) => kayitParcalari.push(e.data);
  mediaRecorder.onstop = async () => {
    const blob = new Blob(kayitParcalari, { type: "audio/webm" });
    const formData = new FormData();
    formData.append("ses", blob, "kayit.webm");

    metinInput.placeholder = "Ses metne çevriliyor...";
    const yanit = await fetch("/api/ses", { method: "POST", body: formData });
    const veri = await yanit.json();
    metinInput.value = veri.metin || "";
    metinInput.placeholder = "Bir şey sor ya da çevirmek istediğin metni yaz...";
    metinInput.dispatchEvent(new Event("input"));
    metinInput.focus();
  };

  mediaRecorder.start();
  mikBtn.classList.add("kayit-aktif");
});