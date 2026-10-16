# MamidLabs — macOS

Tamamen **yerel**, çok modlu bir yapay zekâ çalışma alanı. Tek bir Qt6 penceresinde
sohbet, web araması, belge okuma/üretimi, OCR, görsel anlama, görsel üretimi,
fotoğraf düzenleme, video üretimi, grafik çizimi ve ses dökümü sunar. Dil modeli
**llama.cpp** (`llama-server`), görsel/video modelleri **ComfyUI** üzerinde,
Mac'in **Metal** hızlandırıcısında (llama.cpp Metal; torch/ComfyUI MPS) çalışır.
OpenAI, Claude, Gemini, DeepSeek ve OpenAI uyumlu özel uçlar isteğe bağlı API
sağlayıcılarıdır.

Bu depo, Windows sürümünün (`MamidLabsTR` / `MamidLabsENG`) **macOS portudur**.
WinForms/PowerShell macOS'ta çalışmadığı için uygulama tek dilde
(**Python 3.12 + PySide6/Qt6**) yazılmış; aynı motorları (llama.cpp, ComfyUI) ve
aynı Python araçlarını (web, belge, OCR, medya, döküm) kullanır.

Depo: `github.com/workaybarsh/mamidlabs_mac` · Varsayılan kurulum kökü:
`~/Library/Application Support/mamidlabs` (`MAMIDLABS_ROOT` ile değiştirilir).

---

## Özellikler

| Yetenek | Nasıl çalışır |
|---|---|
| Sohbet (akışlı) | Yerel `llama-server` (llama.cpp, Metal) ya da API sağlayıcısı; düşünme + yanıt ayrı gösterilir |
| Web araması / sayfa okuma | `ddgs` + sayfa çıkarma; **başarısızsa uydurmaz**, dürüst bildirir |
| Belge okuma / üretimi | PDF, Word, Excel, PowerPoint, ZIP, RAR okuma; PDF/DOCX/PPTX/XLSX üretimi |
| OCR | PaddleOCR (CPU) — isteğe bağlı bileşen |
| Görsel anlama | Modelin görsel projektörü (mmproj) ile görsel okuma |
| Görsel üretimi / düzenleme | Yerel ComfyUI (Krea-2 Turbo, MPS; kimlik düzenleme MAX/FLASH) veya API |
| Video üretimi | Yerel ComfyUI (Wan 2.2 TI2V 5B) veya API |
| Grafik çizimi | matplotlib; bar/line/pie/scatter/function (güvenli ifade çözümleyici) |
| Ses dökümü | faster-whisper `large-v3-tr` + AST ses olayları + opsiyonel konuşmacı ayrımı (CPU) |
| Araç çağırma | `search_web`, `fetch_page`, `read_document`, `create_document`, `generate_image`, `generate_video`, `generate_chart`, `ask_model`, bağlı klasör araçları, `run_command` |
| Onay akışı | Yazma/çalıştırma araçları kullanıcı izni ister; "Tam erişim" çipi açıksa sorulmaz |
| API sağlayıcıları | openai, claude, gemini, deepseek, custom (OpenAI uyumlu) |

**Güvenlik davranışları (Windows sürümüyle aynı):** İstenmeden belge/görsel/video/grafik
üretilmez; web araması başarısızsa ya da İnternet kapalıyken güncel bilgi istenirse
model **uydurmak yerine** bunu açıkça bildirir; `read_document` yalnızca belge
bağlamı varken sunulur.

---

## Gereksinimler

- **macOS 12 (Monterey)** veya üzeri — Apple Silicon (arm64) önerilir; Intel x86-64 desteklenir
- **Python 3.11–3.13** (3.12 önerilir; `brew install python@3.12`), `git`, `curl`, `unzip`
- **Homebrew** (isteğe bağlı ama önerilir: `brew install sevenzip` RAR için, `python@3.12` için)
- Metal destekli GPU (tüm desteklenen Mac'lerde var). 27B profil için **32 GB**,
  LITE profil için **16 GB** birleşik bellek önerilir.
- Disk: **LITE ~36 GB**, **MAX/FLASH ~52 GB** (modeller + ComfyUI + ortamlar)

> **Birleşik bellek (unified memory) notu:** macOS'ta ayrı VRAM yoktur; GPU sistem
> belleğini paylaşır. Bellek kapısı bu yüzden **geri kazanılabilir birleşik bellek**
> (`vm_stat`) üzerinden hesaplanır, `nvidia-smi` kullanılmaz.

---

## Kurulum

```bash
git clone https://github.com/workaybarsh/mamidlabs_mac.git
cd mamidlabs_mac
./scripts/install-mamidlabs.sh --profile flash
```

Kurulum aşamaları: `preflight → layout → llama → python → comfyui → models → verify`.
Ayrı ayrı çalıştırmak için `--stage` kullanın; örneğin yalnızca program dosyalarını
güncellemek için:

```bash
./scripts/install-mamidlabs.sh --stage layout
```

Faydalı seçenekler:

| Seçenek | Etki |
|---|---|
| `--root <yol>` | Kurulum kökü (varsayılan `~/Library/Application Support/mamidlabs`) |
| `--profile max\|flash\|lite` | Model indirme profili (varsayılan: indirmez) |
| `--skip-media` | ComfyUI ve görsel/video bileşenlerini atla |
| `--skip-audio` | Ses dökümü ortamını (`venv/asr`) atla |
| `--skip-ocr` | OCR ortamını (`venv/ocr`) atla |
| `--skip-models` | Dil modeli indirmeyi atla |
| `--no-desktop` | `MamidLabs.app` paketini kurma |
| `--force` | Var olanı yeniden kur |

Kurulum kökü düzeni:

```
~/Library/Application Support/mamidlabs/
  llama.cpp/<build>/llama-server   sabitlenmiş llama.cpp yapısı (Metal)
  models/                          GGUF dil modelleri (+ mmproj)
  ComfyUI/                         sabit commit ComfyUI + models/
  venv/{app,imagegen,asr,ocr}/     Python ortamları (her biri kendi işi için)
  tools/{hf-home,downloads,pip-cache}/
  settings/api.json                tüm kullanıcı ayarları (gizli anahtarlar 0600)
  chats/  outputs/  logs/          sohbetler, üretilen dosyalar, günlükler
  mamidlabs-launch                 başlatıcı (.app paketinin çağırdığı betik)
```

Kurulum ayrıca `~/Applications/MamidLabs.app` paketini oluşturur (ikon `.icns`
olarak üretilir); Finder/Dock/Launchpad'den çalıştırılabilir.

---

## Kullanım

Uygulamayı başlat:

```bash
~/Library/Application\ Support/mamidlabs/mamidlabs-launch
```

Ya da **Launchpad / Finder → Uygulamalar → MamidLabs** (kurulum `~/Applications`
altına `MamidLabs.app` paketini koyar).

Model yönetimi:

```bash
./scripts/manage-mamidlabs.sh start flash    # yerel modeli başlat
./scripts/manage-mamidlabs.sh stop           # durdur
./scripts/manage-mamidlabs.sh status         # etkin profil
./scripts/manage-mamidlabs.sh comfy          # ComfyUI başlat (medya için)
./scripts/manage-mamidlabs.sh closecomfy     # boştaki ComfyUI'yi kapat
./scripts/manage-mamidlabs.sh doctor         # kurulumu denetle
./scripts/manage-mamidlabs.sh profiles       # profil durumu
```

Komut satırı (GUI olmadan):

```bash
python -m mamidlabs doctor
python -m mamidlabs profiles --json
python -m mamidlabs manage start --profile lite
```

---

## Kaldırma

```bash
./scripts/uninstall-mamidlabs.sh                  # tümü (sorar)
./scripts/uninstall-mamidlabs.sh --keep-user-data # ayarlar/sohbetler/modeller kalır
./scripts/uninstall-mamidlabs.sh --dry-run        # yalnızca göster
```

Kaldırıcı yalnızca kurulum köküne ve `~/Applications/MamidLabs.app` paketine
dokunur; kök dışındaki hiçbir dosyayı silmez.

---

## Donanım gerçekleri

macOS'ta hız Metal'e ve birleşik bellek miktarına bağlıdır. Aşağıdaki sayılar
Windows/NVIDIA sürümünden **referanstır**; Apple Silicon'da sohbet token hızı
genelde benzer, görsel/video üretimi (MPS) ise CUDA'ya göre daha yavaştır.

| | 32 GB (27B MAX/FLASH) | 16 GB (9B LITE) |
|---|---|---|
| Sohbet | Metal'de akıcı (MTP açık) | Metal'de akıcı (MTP açık) |
| Görsel (`yeni`) | dakikalar mertebesi (MPS) | dakikalar mertebesi (MPS) |
| Fotoğraf düzenleme (`kimlik_duzenle`) | desteklenir | **desteklenmiyor** (bellek yetmez) |
| Ses dökümü | CPU (int8) | CPU (int8) |

ComfyUI varsayılan olarak **yalnızca medya üretiminde** çalışır ve dil modeli
yüklenmeden önce kapatılır (boşta ne bellek ne GPU tutar).

---

## Testler

```bash
python3 -m pip install pytest -r requirements/app.txt
python3 -m pytest -q
```

Uçtan uca doğrulama (kurulu kökte, gerçek modellerle):

```bash
./scripts/smoke-test.sh --profile flash
```

---

## Katkı ve geliştirme

Kod tabanının nasıl başlatıldığını, parçaların nasıl konuştuğunu ve bilinen
tuzakları **[AGENTS.md](AGENTS.md)** anlatır. Yeni bir özellik eklediğinizde
aynı commit'te `AGENTS.md` ve `CHANGELOG.md`'yi de güncelleyin.

---

## Lisans

Tescilli yazılım — **tüm hakları saklıdır**. Telif: **Aybars Haydar Altuntaş**.
Ayrıntılar için [LICENSE](LICENSE) ve [EULA.txt](EULA.txt).
