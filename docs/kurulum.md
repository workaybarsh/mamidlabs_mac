# Kurulum kılavuzu (macOS)

Bu kılavuz MamidLabs'ı macOS'a kurmayı, başlatmayı, güncellemeyi ve kaldırmayı
anlatır. Ayrıntılı teknik bilgi için [teknik-notlar.md](teknik-notlar.md).

## 1. Ön koşullar

| Gereksinim | Not |
|---|---|
| macOS 12 (Monterey)+ | Apple Silicon (arm64) önerilir; Intel x86-64 desteklenir |
| Python 3.11–3.13 | 3.12 önerilir. `brew install python@3.12` |
| `git`, `curl`, `unzip` | ComfyUI ve llama.cpp indirmeleri için (macOS'ta hazır gelir) |
| Homebrew | `brew install python@3.12 sevenzip` (sevenzip RAR için, isteğe bağlı) |
| Metal GPU | Tüm desteklenen Mac'lerde var. 27B profil için **32 GB**, LITE için **16 GB** birleşik bellek önerilir |
| Disk | LITE ~36 GB, MAX/FLASH ~52 GB |

Homebrew kurulu değilse:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python@3.12
```

> **Birleşik bellek:** macOS'ta ayrı VRAM yoktur; GPU sistem belleğini paylaşır.
> Bellek kapısı `vm_stat` ile geri kazanılabilir birleşik belleği ölçer.

## 2. Kurulum

```bash
git clone https://github.com/workaybarsh/mamidlabs_mac.git
cd mamidlabs_mac
./scripts/install-mamidlabs.sh --profile flash
```

`--profile` vermezseniz program dosyaları ve motorlar kurulur ama **dil modeli
indirilmez**; sonradan `./scripts/manage-mamidlabs.sh profiles` ile durumu görüp
indirebilirsiniz.

### Aşamalar

Kurulum sırayla şu aşamaları çalıştırır (`--stage` ile seçilebilir):

| Aşama | Yaptığı iş |
|---|---|
| `preflight` | Python/git/disk/Metal/7-Zip denetimi |
| `layout` | `venv/app`, uygulama paketi, başlatıcı, `MamidLabs.app` + `.icns` simge |
| `llama` | Sabitlenmiş `llama.cpp` (`b10998`) Metal `llama-server` indirir |
| `python` | `venv/imagegen`, `venv/asr`, `venv/ocr` ortamları (torch PyPI/MPS) |
| `comfyui` | Sabit commit ComfyUI + `ComfyUI-GGUF` + `comfyui-krea2edit` |
| `models` | `--profile` verilmişse dil modeli + mmproj indirir |
| `verify` | Kurulumu denetler (`python -m mamidlabs doctor`) |

Örnekler:

```bash
# Yalnızca program dosyalarını tazele (güncelleme)
./scripts/install-mamidlabs.sh --stage layout

# Medya/ses/OCR olmadan hafif kurulum
./scripts/install-mamidlabs.sh --profile lite --skip-media --skip-ocr

# Farklı köke kur
./scripts/install-mamidlabs.sh --root "$HOME/mamidlabs" --profile max
```

## 3. İlk çalıştırma

```bash
~/Library/Application\ Support/mamidlabs/mamidlabs-launch
```

ya da **Launchpad / Finder → Uygulamalar → MamidLabs** (kurulum
`~/Applications/MamidLabs.app` paketini oluşturur).

İlk açılışta:

1. Üstteki **Profil** kutusundan profili seçin (MAX / FLASH / LITE).
2. **Modeli başlat** düğmesine basın; durum çubuğu "Hazır" olana kadar bekleyin.
3. Mesajınızı yazıp **Gönder**'e basın (veya `⌘+Enter`).

### Çipler

| Çip | Açıkken |
|---|---|
| **İnternet** | Web araması ve sayfa okuma araçları sunulur |
| **Ajan** | Bağlı klasör araçları ve `ask_model` sunulur |
| **Tam erişim** | Yazma/çalıştırma araçları için onay sorulmaz |

## 4. API sağlayıcıları (isteğe bağlı)

Menü → **API bağlantıları…**. openai / claude / gemini / deepseek / custom
satırlarından birini seçip anahtarı girin. Anahtarlar tercihen **macOS oturum
anahtarlığında** (Keychain), yoksa `settings/api.json` içinde `0600` izinle
saklanır. `custom`, OpenAI uyumlu kendi ucunuzdur (Ollama, LM Studio, vLLM…);
taban adresi girin, anahtar isteğe bağlıdır.

## 5. Yönetim

```bash
./scripts/manage-mamidlabs.sh start [max|flash|lite]  # modeli başlat
./scripts/manage-mamidlabs.sh stop                    # durdur
./scripts/manage-mamidlabs.sh status                  # etkin profil
./scripts/manage-mamidlabs.sh comfy                   # ComfyUI başlat
./scripts/manage-mamidlabs.sh closecomfy              # boştaki ComfyUI'yi kapat
./scripts/manage-mamidlabs.sh doctor                  # kurulum denetimi
./scripts/manage-mamidlabs.sh profiles                # profil durumu
```

## 6. Güncelleme

1. Uygulamayı kapatın.
2. Depoyu çekin: `git pull`
3. Program dosyalarını tazeleyin: `./scripts/install-mamidlabs.sh --stage layout`

Kullanıcı verisi (`settings/`, `chats/`, `models/`, `outputs/`) korunur.

## 7. Kaldırma

```bash
./scripts/uninstall-mamidlabs.sh                  # tümü (onay ister)
./scripts/uninstall-mamidlabs.sh --keep-user-data # ayarlar/sohbetler/modeller kalır
./scripts/uninstall-mamidlabs.sh --dry-run        # yalnızca göster
```

## 8. Sorun giderme

| Belirti | Çözüm |
|---|---|
| "PySide6 bulunamadı" | `./scripts/install-mamidlabs.sh --stage layout` |
| "Yetersiz birleşik bellek" | Diğer uygulamaları kapatın; LITE profiline geçin |
| Model yüklenmiyor | `python -m mamidlabs doctor`; günlüklere bakın: `logs/` |
| Görsel üretimi çalışmıyor | `./scripts/manage-mamidlabs.sh comfy`; ComfyUI günlükleri: `logs/comfyui.*.log` |
| ComfyUI çok yavaş | macOS'ta MPS kullanılır (CUDA'ya göre yavaş); bazı özel düğümler CPU'da çalışır |
| Ses dökümü hata veriyor | `venv/asr` kurulu mu? `--skip-audio` ile atlanmış olabilir (macOS'ta CPU'da çalışır) |
| Web araması çalışmıyor | İnternet çipini açın; çevrimdışıysa model uydurmaz, bunu bildirir |
| `bash: bad substitution` | Betikler bash 3.2 ile uyumludur; farklı bir kabukta çalıştırmayın |

Günlükler `~/Library/Application Support/mamidlabs/logs/` altındadır:
`llama-server-*.std{out,err}.log`, `comfyui.{out,err}.log`, `audit.jsonl`,
`smoke-test-son.json`.
