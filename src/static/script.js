const mesajAlani = document.getElementById("mesaj-alani");
const metinInput = document.getElementById("metin-input");
const gonderBtn = document.getElementById("gonder-btn");
const dosyaBtn = document.getElementById("dosya-btn");
const dosyaInput = document.getElementById("dosya-input");
const mikBtn = document.getElementById("mik-btn");

let secilenDosya = null;

function asagiKaydir() {
  window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "smooth" });
}

function kacis(metin) {
  const d = document.createElement("div");
  d.textContent = metin;
  return d.innerHTML;
}

function basitMarkdown(metin) {
  let g = kacis(metin);
  g = g.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  g = g.replace(/(https?:\/\/[^\s)]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
  return g;
}

function karsilamaKaldir() {
  const k = mesajAlani.querySelector(".karsilama");
  if (k) k.remove();
}

function mesajEkle(metin, kimden) {
  karsilamaKaldir();
  const satir = document.createElement("div");
  satir.className = `mesaj-satiri ${kimden}`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = kimden === "kullanici" ? "S" : "AI";

  const balon = document.createElement("div");
  balon.className = "mesaj";
  balon.innerHTML = basitMarkdown(metin);

  satir.appendChild(avatar);
  satir.appendChild(balon);
  mesajAlani.appendChild(satir);
  asagiKaydir();
  return balon;
}

function yaziyorGoster() {
  const balon = mesajEkle("", "asistan");
  balon.innerHTML = '<div class="yaziyor"><span></span><span></span><span></span></div>';
  return balon;
}

metinInput.addEventListener("input", () => {
  metinInput.style.height = "auto";
  metinInput.style.height = metinInput.scrollHeight + "px";
});

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

    const balon = yaziyorGoster();

    const formData = new FormData();
    formData.append("dosya", dosya);
    formData.append("not", metin);

    const yanit = await fetch("/api/dosya", { method: "POST", body: formData });
    const veri = await yanit.json();
    balon.innerHTML = basitMarkdown(veri.cevap || veri.hata || "Bir şeyler ters gitti.");
    asagiKaydir();
    return;
  }

  if (!metin) return;
  mesajEkle(metin, "kullanici");
  metinInput.value = "";
  metinInput.style.height = "auto";

  const balon = yaziyorGoster();

  const yanit = await fetch("/api/mesaj", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ metin }),
  });
  const veri = await yanit.json();
  balon.innerHTML = basitMarkdown(veri.cevap || veri.hata || "Bir şeyler ters gitti.");
  asagiKaydir();
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
  dosyaBtn.textContent = "📎✓";
  metinInput.focus();
});

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