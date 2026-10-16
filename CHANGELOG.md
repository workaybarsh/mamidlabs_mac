# Değişiklik Günlüğü

Bu dosya kullanıcıya görünen değişiklikleri listeler. Biçim
[Keep a Changelog](https://keepachangelog.com/tr/1.1.0/) temellidir ve sürümler
[Anlamsal Sürümleme](https://semver.org/lang/tr/) izler.

Sürümün tek kaynağı `mamidlabs/__init__.py` içindeki `__version__` ve
`pyproject.toml` içindeki `version` alanıdır (ikisi eşit olmalıdır).

## [1.0.0] — 2026-10-16

### Eklendi
- **MamidLabs macOS sürümü.** Windows sürümünün (`MamidLabsTR` / `MamidLabsENG`)
  tam macOS portu: WinForms/PowerShell yerine tek dilde **Python 3.12 + PySide6
  (Qt6)** masaüstü uygulaması.
- Qt6 ana pencere: akışlı sohbet, profil/sağlayıcı/model seçicileri, İnternet /
  Ajan / Tam erişim çipleri, model başlat-durdur, araç onay penceresi.
- API bağlantıları penceresi; anahtarlar tercihen **macOS Keychain (keyring)**
  üzerinden, yoksa `0600` izinli ayar dosyasında saklanır.
- Komut satırı arayüzü: `python -m mamidlabs {doctor,profiles,manage}`.
- Bash kurulum/yönetim betikleri: `install-mamidlabs.sh` (aşamalı),
  `manage-mamidlabs.sh`, `uninstall-mamidlabs.sh`, `smoke-test.sh`
  (hepsi macOS bash 3.2 ile uyumlu).
- **`MamidLabs.app`** uygulama paketi (`Info.plist` + yürütücü) ve PNG'den üretilen
  `.icns` simge; Launchpad/Finder/Dock'dan çalıştırılabilir.
- Çekirdek modüller: `paths` (macOS kurulum kökü), `settings`, `profiles`,
  `providers` (OpenAI ↔ Claude dönüştürücüleri + akış), `manage`
  (`ModelManager`, birleşik bellek kapısı, ComfyUI/orphan temizliği), `inference`
  (sohbet döngüsü, araç döngüsü, onay, bağlam sıkıştırma), `tools`
  (araç kaydı + kapılar + web başarısızlık dürüstlüğü), `chart`, `runner`.
- Python işçileri macOS'a taşındı (web, belge, OCR, medya, whisper/transcriber,
  `mtp_inject`, `hf-hub`, `api-media`); kurulum kökü artık `MAMIDLABS_ROOT`'tan
  okunur (`__file__`'dan türetilmez).
- Birim testleri (`pytest`); bellek kapısı ve platforma duyarlı yol testleri dahil.

### Değişti (Windows sürümüne göre)
- Windows **DPAPI** yerine macOS **Keychain** / `0600` dosya.
- Windows **PowerShell 7 gömülü çalışma zamanı** yerine sistem Python'u
  (kurulum kökünde `runtime/` yok).
- Windows **WinForms** yerine **Qt6**; `System.Drawing` grafikleri yerine
  **matplotlib**.
- **NVIDIA/CUDA yerine Metal:** llama.cpp `macos-arm64`/`macos-x64` yapısı,
  torch/ComfyUI **MPS** (torch PyPI'dan; CUDA index'i ve `nvidia-*` paketleri yok).
- **VRAM kapısı → birleşik bellek kapısı:** `nvidia-smi` yerine `vm_stat`
  (geri kazanılabilir sayfalar) + `hw.pagesize`; `MAMIDLABS_FREE_MEM_MIB` ile
  geçersiz kılınabilir.
- Ses dökümü macOS'ta **CPU'da** (CTranslate2'nin Metal arka ucu yok).
- 7-Zip yolu Homebrew (`/opt/homebrew/bin`, `/usr/local/bin`) + PATH; PDF yazı
  tipleri macOS sistem fontları + matplotlib DejaVu; HTTP User-Agent `Macintosh`.
- `.desktop` yerine **`.app` paketi**; `run_command` `/bin/zsh -lc` ile çalışır.

### Korundu
- Profil takma adları (`qwen3.8-27b-max` / `-flash`, `qwen3.5-9b-lite`), model
  kimlikleri, araç adları, sunucu argüman demetleri, MTP, bellek kapısı payları ve
  ComfyUI yaşam döngüsü — Windows sürümüyle birebir.
