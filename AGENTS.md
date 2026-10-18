# MamidLabs · Geliştirici ve yapay zekâ ajanları için altyapı rehberi (macOS)

Bu dosya MamidLabs macOS sürümü üzerinde çalışan geliştiriciler ve yapay zekâ
ajanları için tek doğru kaynaktır. Kod tabanının nasıl başlatıldığını, parçaların
nasıl konuştuğunu, nerede ne durduğunu ve bilinen tuzakları anlatır.

> **Zorunlu kural:** Yeni bir özellik eklediğinde, bir davranışı değiştirdiğinde ya
> da yeni bir tuzak bulduğunda **aynı commit'te** bu dosyayı güncelle: ilgili
> bölümü düzelt ve en alttaki [Değişiklik günlüğü](#15-değişiklik-günlüğü)'ne bir
> satır ekle. Kullanıcıya görünen değişiklikler `CHANGELOG.md`'ye de yazılır. Kod
> ile bu dosya çelişirse **kod doğrudur**; çelişkiyi fark eden bu dosyayı düzeltir.

Kullanıcıyla iletişim dili **Türkçe**dir. Kod yorumları ve betik metinleri Türkçedir.

---

## 1. Ürün tek paragrafta

MamidLabs, macOS'ta tamamen yerel çalışan çok modlu bir yapay zekâ çalışma
alanıdır. Tek bir Qt6 penceresinde sohbet, web araması, belge okuma/üretimi, OCR,
görsel anlama, görsel üretimi, fotoğraf düzenleme, video üretimi, grafik çizimi ve
ses dökümü sunar. Dil modeli `llama.cpp` (`llama-server`), görsel/video modelleri
`ComfyUI` üzerinde, Mac'in **Metal** hızlandırıcısında çalışır (llama.cpp Metal;
torch/ComfyUI MPS). OpenAI, Claude, Gemini, DeepSeek ve OpenAI uyumlu özel uçlar
isteğe bağlı API sağlayıcılarıdır. Depo: `github.com/workaybarsh/mamidlabs_mac`.
Varsayılan kurulum kökü `~/Library/Application Support/mamidlabs`.

Bu sürüm, Windows sürümünün (`MamidLabsTR` / `MamidLabsENG`) **macOS portudur**:
WinForms/PowerShell yerine **Python 3.12 + PySide6 (Qt6)**. Sabitler, davranışlar
ve araç kümesi Windows sürümüyle birebir tutulur.

## 2. Depo haritası

| Yol | İçerik |
|---|---|
| `mamidlabs/__main__.py` | Giriş noktası: `doctor`, `profiles`, `manage` alt komutları; aksi halde GUI |
| `mamidlabs/ui/app.py` | Qt6 `QApplication` + ana pencere kurulumu |
| `mamidlabs/ui/main_window.py` | Ana pencere, sohbet, profil/sağlayıcı seçicileri, çipler, `TurnWorker`/`ManageWorker` |
| `mamidlabs/ui/settings_dialog.py` | API bağlantıları penceresi, anahtar doğrulama |
| `mamidlabs/ui/theme.py` | Qt stil sayfası |
| `mamidlabs/core/i18n.py` | Çalışma anı yerelleştirme (TR kaynak; EN geri düşer) |
| `mamidlabs/locales/{tr,en}.json` | Arayüz metinleri (TR kaynak, EN çeviri) |
| `mamidlabs/core/hwinfo.py` | Donanım ölçümü + profil önerisi (birleşik bellek; sihirbaz 5. adım) |
| `mamidlabs/wizard/` | Kurulum sihirbazı: `__init__.py` (saf yardımcılar), `setup.py` (Qt6 `QWizard`, 13 sayfa), `__main__.py` (giriş + masaüstü denetimi) |
| `mamidlabs/core/paths.py` | macOS kurulum kökü ve tüm yollar (`is_macos`, `default_root`) |
| `mamidlabs/core/settings.py` | `api.json` deposu (atomik yazım, `0600`), `SecretStore`, `secret_backend` |
| `mamidlabs/core/profiles.py` | Profil kataloğu, takma adlar, hedef yollar, eksik dosyalar |
| `mamidlabs/core/providers.py` | Sağlayıcı tablosu, OpenAI ↔ Claude dönüştürücüleri, akış (SSE) |
| `mamidlabs/core/manage.py` | `ModelManager`: başlat/durdur, bellek kapısı, `server_args`, ComfyUI/orphan temizliği, `FileLock` |
| `mamidlabs/core/inference.py` | `InferenceEngine`: sohbet döngüsü, sistem istemi, araç döngüsü, onay, sıkıştırma, web dürüstlüğü |
| `mamidlabs/core/tools.py` | `ToolRegistry` (kapılar + işleyiciler), `WebTracker`, `MediaBridge` |
| `mamidlabs/core/chart.py` | matplotlib grafik üretimi + güvenli ifade çözümleyici |
| `mamidlabs/core/runner.py` | `WorkerRunner`: işçileri JSON stdin/stdout ile çalıştırır |
| `mamidlabs/workers/` | Platformdan bağımsız Python işçileri (aşağıya bakın) |
| `scripts/install-mamidlabs.sh` | Aşamalı kurulum (Homebrew/Metal/MPS) |
| `scripts/manage-mamidlabs.sh` | Model/ComfyUI yönetimi, doctor, profiles |
| `scripts/uninstall-mamidlabs.sh` | Tam kaldırma (kök dışına dokunmaz) |
| `scripts/smoke-test.sh` | Gerçek modellerle uçtan uca doğrulama |
| `scripts/mamidlabs-setup.sh` | Kurulum sihirbazını başlatır (`python3 -m mamidlabs.wizard`) |
| `packaging/macos/build-dmg.sh` | `.dmg` üretir (sihirbaz `.app`'i gömer); `packaging/macos/README.md` |
| `packaging/Info.plist`, `packaging/MacOS-MamidLabs` | uygulama `.app` şablonları (`@VERSION@`, `@ROOT@` yer tutucuları) |
| `packaging/macos/Info.plist`, `packaging/macos/MacOS-MamidLabsSetup` | sihirbaz `.app` şablonları |
| `packaging/mamidlabs.png`, `packaging/mamidlabs.svg` | Simge (`.icns` derlemede üretilir) |
| `requirements/{app,imagegen,asr,ocr}.txt` | Python paketleri (sabit sürümler) |
| `tests/` | pytest (211 test; PySide6 gerektirmez) |
| `docs/` | `kurulum.md`, `teknik-notlar.md` |
| `.github/workflows/tests.yml` | CI (macos-latest, Python 3.12) |
| `.github/workflows/kurulum-paketi.yml` | Yayın: `v*` etiketinde `.dmg` derler, sabit adla (`MamidLabs.dmg`) GitHub Release'e yükler |
| `AGENTS.md` | Bu rehber. Kurulum köküne kopyalanmaz. |

### İşçiler (`mamidlabs/workers/`)

Tek-atımlık JSON stdin/stdout sözleşmesi. Her işçi kendi sanal ortamında çalışır.

| İşçi | Ortam | İş |
|---|---|---|
| `mamidlabs-agent-tools.py` | app | Web araması (`ddgs`), sayfa okuma, referans görsel |
| `office-tools.py` | app | PDF/Word/Excel/PPTX/ZIP/RAR okuma, PDF/DOCX/PPTX/XLSX üretimi |
| `ocr-tools.py` | ocr | PaddleOCR (CPU) |
| `media-tools.py` | imagegen | Video kare çıkarma (PyAV) |
| `api-media.py` | app | API ile görsel/video üretimi |
| `hf-hub.py` | app | Hugging Face indirme (boyut + SHA256 doğrulamalı, kaldığı yerden sürer) |
| `mtp_inject.py` | app | LITE GGUF'una MTP/nextn başlığı ekleme |
| `whisper-tools.py` | asr | Ses dökümü (`transcriber/` paketini çağırır; macOS'ta CPU) |
| `transcriber/` | asr | faster-whisper + AST + pyannote hattı |
| `rag-tools.py` | app | Bağlı klasörde yerel (çevrimdışı) BM25 araması (`search_folder`) |
| `_root.py` | — | İşçilerin kurulum kökünü okuması (`MAMIDLABS_ROOT` → Library) |

## 3. Kurulum kökü düzeni

```
~/Library/Application Support/mamidlabs/
  llama.cpp/b10998/llama-server     sabit llama.cpp yapısı (Metal)
  models/                           GGUF dil modelleri (+ mmproj)
  ComfyUI/                          sabit commit; custom_nodes: ComfyUI-GGUF, comfyui-krea2edit
  venv/{app,imagegen,asr,ocr}/      Python ortamları (bin/python)
  tools/{hf-home,downloads,pip-cache,backup,rag}/
  settings/api.json                 tüm kullanıcı ayarları (gizli anahtarlar 0600)
  chats/  outputs/{images,videos,documents,charts,refs,thumbs,input}/
  logs/                             llama-server-*.std{out,err}.log, comfyui.*.log, audit.jsonl
  mamidlabs-launch                  başlatıcı (.app paketinin çağırdığı betik)
```

Kurulum ayrıca **`~/Applications/MamidLabs.app`** paketini oluşturur
(`Contents/Info.plist`, `Contents/MacOS/MamidLabs`, `Contents/Resources/mamidlabs.icns`).

Windows'ta olduğu gibi **gömülü bir çalışma zamanı yok** (`runtime/` yoktur):
uygulama sistem Python'u ile çalışır.

## 4. Başlatma zinciri

1. `MamidLabs.app` → `Contents/MacOS/MamidLabs` (kurulumda `@ROOT@` ile üretilir).
2. Bu betik `~/Library/Application Support/mamidlabs/mamidlabs-launch` betiğini çalıştırır.
3. Başlatıcı: `MAMIDLABS_ROOT` ayarlar, `venv/app/bin/python -m mamidlabs` çalıştırır.
4. `mamidlabs/__main__.py` argümanları ayrıştırır; alt komut yoksa `ui/app.py:main`.
5. `ui/app.py`: `Paths`, `Settings`, `QApplication`, `MainWindow`.
6. `MainWindow` yolları hazırlar, `ModelManager`/`ToolRegistry`/`InferenceEngine` kurar.
7. Kullanıcı profili seçip **Modeli başlat**'a basınca `ManageWorker` → `ModelManager.start`.
8. Uygulama kapanınca sunucu ve boştaki ComfyUI kapatılır (bellek boşalır).

## 5. Süreçler ve portlar

| Süreç | Port | Sahibi |
|---|---|---|
| `llama-server` | 8080 | `core/manage.py` (`ModelManager`) |
| ComfyUI | 8188 | medya köprüsü / `manage-mamidlabs.sh comfy` |
| Ses döküm işçisi | rastgele (127.0.0.1) | `core/inference.py` |

**Profiller** (`core/profiles.py`; takma adlar Windows'la aynı):

| Profil | Alias | Önemli bayraklar |
|---|---|---|
| MAX | `qwen3.8-27b-max` | ctx 32768, predict 8192, gpu-layers 99, q4_0 KV, cache-reuse 256, batch 512/256, threads 6/12, `--mmproj --no-mmproj-offload --image-min-tokens 1024`, `--reasoning-effort xhigh`, MTP varsa `--spec-type draft-mtp` |
| FLASH | `qwen3.8-27b-flash` | aynı dosyalar; `--reasoning-effort low` |
| LITE | `qwen3.5-9b-lite` | ctx `liteContext` (32768), predict 8192, batch 256/128, threads 4/8, `--image-min-tokens 512`, `--reasoning-effort low`, MTP varsa `--spec-type draft-mtp` |

Sunucu argümanları Windows sürümüyle **birebir aynıdır**; macOS'ta Metal zaten
varsayılan arka uçtur, ayrı bir bayrak gerekmez (`--gpu-layers 99` Metal'e de
uygulanır). MAX ve FLASH aynı dosyaları kullanır → arayüzde tek "Qwen3.8 MAX"
girdisi (`catalog_for_display`). Kimliğe göre arama tam kataloğu (`get_profile`)
kullanır.

**MTP.** `--spec-type draft-mtp` yalnızca GGUF gerçekten MTP/`nextn` katmanı
taşıyorsa eklenir (`manage.gguf_has_mtp`); taşımayan modele verilirse llama.cpp
açılmaz. LITE'ın 9B GGUF'u başlığı dönüşümde kaybeder, indirmede `mtp_inject.py`
ile geri eklenir. `settings.mtp=false` ile kapatılır.

**Otomatik çaba (MAX/FLASH).** MAX ve FLASH aynı modeldir; tek fark sunucudaki
`--reasoning-effort` değeridir. Profil değiştirmek modeli yeniden yüklediği
(~15 sn) için varsayılan olarak (Profiller → **"Otomatik çaba (soruya göre)"**)
çaba **istek başına** `chat_template_kwargs.reasoning_effort` ile verilir:
kısa soru/selamlama → `low`, orta → `medium`, çok adımlı matematik/kod/analiz/
karşılaştırma → `xhigh` (`inference.auto_reasoning_effort`). Seçim **tur başında
bir kez** yapılır ve tur boyunca sabit kalır (sistem öneki değişmesin; KV
önbelleği bozulmasın). Kapatılırsa sunucunun profil değeri kullanılır
(`api.json → autoEffort=false`). LITE'ın şablonu bu anahtarı yok sayar; API
sağlayıcılarına gönderilmez.

**İndirme ve doğrulama.** `hf-hub.py` boyutu `bytes` ile doğrular, eksik dosyayı
`hf_hub_download` ile **kaldığı yerden sürer** ve indirme bitince **SHA256**
doğrular: katalogda sabit `sha256` varsa onu, yoksa Hugging Face LFS
metadata'sındaki `lfs.sha256` özetini kullanır (repo/revision başına önbellek).
Özet uyuşmazsa bozuk dosya **silinir**; doğrulama MTP enjeksiyonundan **önce**
yapılır çünkü enjeksiyon dosyayı değiştirir. `HF_HOME` kökün altındadır.

**Bellek kapısı** (`manage.ModelManager`): gereken = model dosyası + pay.
MAX/FLASH pay **750 MiB**, tolerans **0** (kullanılabilir < gereken → hata).
LITE pay **300 MiB**, tolerans **1024 MiB** (uyarı bandı
`[gereken-1024, gereken)`). Görsel projektör üç profilde de CPU'da
(`--no-mmproj-offload`), bütçeye girmez.

macOS'ta **ayrı VRAM yoktur**: `available_memory_mib()` birleşik bellekten geri
kazanılabilir miktarı döndürür (`vm_stat`: free + inactive + speculative +
purgeable; `hw.pagesize` ile çarpılır). `MAMIDLABS_FREE_MEM_MIB` ortam değişkeni
ölçümü geçersiz kılar (testler ve elle ayar için). macOS dışı ana makinelerde
(`sys.platform != "darwin"`) sırasıyla `nvidia-smi` ve `/proc/meminfo` denenir.
`macos_total_mib()` toplam birleşik belleği verir (yalnızca bilgi amaçlı).
Model yüklenmeden önce artık GPU işçileri (`stop_orphan_workers`) kapatılır.

**ComfyUI yaşam döngüsü:** varsayılan **yalnızca medya üretiminde** çalışır
(`comfyKeepAlive=false`); dil modeli yüklenmeden önce kapatılır. LITE'ta
`comfyKeepAlive=true` ile açık tutulabilir. Kaçak/mükerrer örnekler süreç
**köklerine** göre sayılır (ComfyUI bir süreç çiftidir); `:8188`'i dinleyen tek
örnek korunur.

## 6. Sohbet isteğinin akışı

1. Kullanıcı gönderir → `MainWindow._send` → `TurnWorker` (`QThread`).
2. `InferenceEngine.build_job_messages`: sabit `SYSTEM_PROMPT` + geçmiş. Eski
   turlardaki görsel verisi atılır, yerine not konur. Tura özel ipuçları sistem
   istemine değil, **son kullanıcı mesajının başına** eklenir (KV önbellek öneki
   bozulmasın).
3. `run_turn` olaylar üretir (`event` sinyali ile arayüze): `thinking`, `answer`,
   `status`, `tool`, `denied`, `error`, `done`, `cancelled`.
4. **Araçlar** (`core/tools.py`): `search_web`, `fetch_page`, `read_document`,
   `read_images_ocr`, `create_document`, `generate_image`, `generate_video`,
   `generate_chart`, `find_reference_image`, `ask_model`, `list_bound_files`,
   `read_bound_file`, `search_folder`, `write_bound_file`, `run_command`. Araçlar
   niyete ve çiplere göre sunulur; üretim araçları çağrı anında yeniden denetlenir.
5. **Onay:** yazma/çalıştırma araçları `approve` geri çağrısıyla sorulur
   (`TurnWorker._approve` → `approval_needed` sinyali → `QMessageBox`). 10 dk
   zaman aşımı → red. "Tam erişim" çipi açıksa normalde sorulmaz; **ancak o turda
   güvenilmeyen içerik** (`search_web`, `fetch_page`, `read_document`,
   `read_images_ocr`, `read_bound_file`, `search_folder`) **okunduysa
   `run_command` ve `write_bound_file` için yine sorulur** (`approval_required`);
   onay penceresi nedeni de yazar (`chat.approval_untrusted`). Güvenilmeyen
   içeriğin sonucu modele `chat.untrusted_prefix` etiketiyle verilir ve sistem
   istemi (`prompt.untrusted`) bu içeriğin **talimat değil veri** olduğunu söyler
   (istem enjeksiyonuna karşı).
6. **`done` olayı** o turda eklenen `assistant.tool_calls` ve `tool` mesajlarını
   `data` alanında taşır; arayüz bunları kalıcı geçmişe ekler. Bu yapılmazsa
   sonraki turda istemci öneki sunucununkinden farklı olur ve bağlam baştan
   işlenir.
7. **Bağlam koruması** (Windows paritesi): tur başında tahmini istem +
   `max_tokens` + pay bağlamı aşacaksa `compact_turn_messages` **iki geçişle**
   kısaltır — önce en eski araç çıktılarının yalnızca başı, yetmezse en eski araç
   çıktıları ve eski asistan metni kısa bir işaretle değiştirilir (mesaj silinmez;
   `tool_calls`/`tool` eşleşmesi korunur). **Hâlâ sığmıyorsa** araçlar
   **sunulmaz** ve modelden eldeki bulgularla görünür yanıt istenir
   (`chat.context_full`); `max_tokens` kalan odaya göre kısılır. "Sıkıştırıldı"
   durum notu yalnızca gerçekten bir şey kısaldıysa gösterilir.

### Web başarısızlığı dürüstlüğü

Karar **web denendi VE hiç başarılı çağrı olmadı** koşuluna bağlıdır
(`WebTracker.unavailable = fail_count > 0 and not success`). Kısmi başarı
(ör. 7 çağrının 4'ü başarılı) başarısızlık **sayılmaz**. ≥2 hatada web araçları
kilitlenir (`should_lock_tools = fail_count >= 2 and not success`).
`add_failure_note` başarı varsa erken döner. Güncel bilgi isteyen turda web yoksa
modelin metni kullanılmaz, dürüst mesaj gösterilir; uydurma atıflar
(`strip_fabricated_citations`) ayıklanır.

## 7. Görsel, fotoğraf düzenleme ve video

- Model `generate_image` çağırınca `MediaBridge` (arayüzün sağladığı köprü)
  ComfyUI'yi sürer. Dil modeli yalnızca istemi yazar.
- **Modlar** (`generate_image.mode`): `yeni` (metinden), `yeniden_uret` /
  `stil_referansi` (eklenen görselden), `kimlik_duzenle` (Krea 2 Identity Edit
  LoRA; **yalnızca MAX/FLASH** — LITE'ta bellek yetmediği için sunulmaz).
- Video: Wan 2.2 TI2V 5B; modlar `metin`, `gorsel`, `video`.
- Harici model dosyaları kopyalanmadan kullanılır: ComfyUI
  `--extra-model-paths-config`.
- macOS'ta ComfyUI **MPS** ile çalışır; CUDA'ya göre belirgin yavaştır ve bazı
  özel düğümler yalnızca CPU'da çalışabilir. `imagegen` ortamındaki torch PyPI
  tekerleğidir (MPS dahili); ayrı bir CUDA index'i **kullanılmaz**.
- API medya: görsel/video sağlayıcısı API ise `api-media.py`.

## 8. API sağlayıcıları

- Tek tablo: `core/providers.py`: `openai`, `claude`, `gemini`, `deepseek`,
  `custom`. Yeni sağlayıcı = tabloya bir satır (+ gerekirse dönüştürücü).
- **`custom`** ("Özel (OpenAI uyumlu)"): Ollama, LM Studio, vLLM vb. Taban adres
  ayarlardan okunur; **anahtar isteğe bağlıdır** (boşsa `Authorization` gitmez).
- **Claude:** `thinking` gönderilmez; `tool_choice` yalnızca gövdede varsa `auto`;
  `max_tokens` alt sınırı 16000; araç döngüsünde imzalı `thinking` blokları
  `ClaudeStream` ile toplanıp ilk `tool_use` kimliği üzerinden geri gönderilir.
- **DeepSeek** görsel kabul etmez; `image_url` parçaları metin notuna indirilir.
- Anahtarlar tercihen **macOS oturum anahtarlığında** (`keyring` / Keychain),
  yoksa `settings/api.json` içinde `0600` izinle. `Settings.secret_backend`
  hangisinin kullanıldığını bildirir.

## 9. Profiller, katalog ve indirme

- `core/profiles.py`: her profil için dosya listesi (`target` köke göreli, `repo`,
  `revision`, `filename`, `bytes`, isteğe bağlı `sha256`).
- İndirme boyutları: LITE ~36 GB, MAX/FLASH ~52 GB. `hf-hub.py` boyutu `bytes` ile
  doğrular, eksik dosyayı kaldığı yerden sürer (`hf_hub_download`) ve indirme
  bitince **SHA256** doğrular: katalogda sabit `sha256` varsa onu, yoksa Hugging
  Face LFS metadata'sındaki `lfs.sha256` özetini kullanır (repo/revision başına
  önbelleklenir). Uyuşmazsa bozuk dosya **silinir** ve hata verilir. `HF_HOME`
  kökün altındadır.
- Profil durumu yalnızca dosyanın **varlığına** bakar, boyut karşılaştırmaz.
- **Profil silme:** yalnızca o profile **özel** dosyalar silinir
  (`unique_targets`); paylaşılanlar korunur. MAX ve FLASH aynı küme olduğundan
  takma ad sayılır.

## 10. Kurulum, güncelleme ve kaldırma

- `install-mamidlabs.sh [--root] [--profile] [--language tr|en] [--stage a,b]
  [--skip-media] [--skip-audio] [--skip-ocr] [--skip-models] [--no-desktop]
  [--no-cuda] [--force]`. Aşamalar: `preflight`, `layout`, `llama`, `python`,
  `comfyui`, `models`, `verify`. `--language` seçimi `settings/api.json`'a yazar;
  aşama döngüsü ilerlemeyi `logs/kurulum-adim.txt` (satır 1/2/3: adım no, toplam,
  ad), sonunda özeti `logs/kurulum-ozeti.txt` yazar (sihirbaz bunları okur).
- **Sihirbaz ve DMG:** `packaging/macos/build-dmg.sh` içinde **MamidLabs
  Kurulum.app** bulunan bir `.dmg` üretir (`hdiutil`, `-format UDZO`); uygulama
  paketi `Contents/Resources/mamidlabs-src` altına gömülü Python kaynaklarını
  taşır ve `python3 -m mamidlabs.wizard` çalıştırır. Kaynaktan `./scripts/mamidlabs-setup.sh`
  de aynı sihirbazı açar.
- Betik **macOS'un bash 3.2'si** ile uyumludur (ilişkisel dizi, `mapfile`,
  `${var,,}` **kullanılmaz**); shebang `#!/bin/bash`.
- `layout` program dosyalarını, başlatıcıyı ve `~/Applications/MamidLabs.app`
  paketini kurar; `.icns` ikonu `sips`/`iconutil` ile PNG'den üretilir (yoksa
  ikonsuz kurulur).
- `llama` aşaması mimariye göre `llama-<build>-bin-macos-arm64.zip` ya da
  `-macos-x64.zip` indirir ve `llama-server` + `*.dylib` çıkarır (Metal).
- `python` aşaması torch'u **PyPI'dan** (MPS dahili) kurar: imagegen için
  `torch torchvision torchaudio`, asr için `torch torchaudio`, ocr için
  `paddlepaddle` (CPU). CUDA index'i kullanılmaz.
- Sabit sürümler: llama.cpp `b10998`, ComfyUI `b0f4b7b`, ComfyUI-GGUF `6ea2651`,
  comfyui-krea2edit `86f886d`.
- **Kaldırma:** `uninstall-mamidlabs.sh [--keep-user-data] [--dry-run] [--yes]`.
  Yalnızca köke ve `~/Applications/MamidLabs.app` paketine dokunur;
  sistem/kullanıcı klasörlerinde çalışmayı reddeder.
- **Güncelleme:** uygulamayı kapat → `git pull` → `install-mamidlabs.sh --stage layout`.
- **Sürüm ve yayım:** sürümün tek kaynağı `mamidlabs/__init__.py:__version__` ve
  `pyproject.toml:version` (eşit olmalı). Yeni sürüm: ikisini artır, `CHANGELOG.md`'ye
  bölüm ekle, `v<sürüm>` etiketini it. Etiket itilince
  `.github/workflows/kurulum-paketi.yml` `.dmg`'yi derler ve **sabit adla**
  (`MamidLabs.dmg`) GitHub Release'e yükler; `releases/latest/download/MamidLabs.dmg`
  böylece her zaman en son sürümü indirir.

## 11. Ayarlar ve kullanıcı verisi

`settings/api.json` (uygulama bellekte tutar, değişince ve çıkışta yazar;
**uygulama açıkken elle düzenleme ezilir**):

- Model seçimi: `selected`, `selectedModel`, `selectedLocalModel`, `localProfile`.
- Sağlayıcılar: `providers.<id>.{key, model, models, contextLimit, baseUrl}`.
- Kendi modellerin: `localModels`, `imageLocalModel`, `videoLocalModel`,
  `imageProvider`, `videoProvider`, `externalMediaModels`.
- Arayüz: `uiPreferences.{internet, agent, accessMode}`, `firstRunApiSettings`.
- LITE: `liteModel`, `liteContext`.
- Medya: `comfyKeepAlive` (varsayılan `false`).
- Ses: `audioEvents` (varsayılan `true`).
- Diğer: `mtp` (varsayılan `true`), `autoEffort` (varsayılan `true`), `boundFolder`.
- Gizli anahtarlar: macOS Keychain ya da bu dosyada (`0600`).

Sohbetler `chats/` altında saklanır. `logs/audit.jsonl`: araç çağrıları kaydı
(içerik değil; yol/komut kimliği).

## 12. Testler

```bash
python3 -m pip install pytest -r requirements/app.txt
python3 -m pytest -q          # 211 test; PySide6 gerektirmez (yalnızca sihirbaz penceresi testleri)
./scripts/smoke-test.sh --profile flash
```

- `conftest.py` `MAMIDLABS_ROOT`'u geçici bir köke yönlendirir; testler
  `__file__`'dan bağımsız çalışır. Aynı dosyadaki autouse fikstür, süreç-global
  dil durumunu (`i18n`) her testten önce/sonra Türkçe'ye sıfırlar.
- Yeni davranış testleri: `test_model_download_integrity.py` (`sha256_file`,
  `lookup_sha256`/`verify_sha256`, `incomplete_bytes`, `_mtp_config`, fetch
  koruması), `test_auto_effort.py` (`auto_reasoning_effort` skoru + istek gövdesine
  `chat_template_kwargs`), `test_prompt_injection.py` (güvenilmeyen içerik etiketi,
  sistem istemi, tam erişimde bile onay), `test_rag_tools.py` (`rag-tools.py` BM25
  + `search_folder` kapısı).
- `tests/test_wizard.py` saf yardımcıları Qt olmadan sınar;
  `tests/test_wizard_gui.py` sihirbaz penceresini başsız açmayı dener ve Qt
  yüklenemezse (ör. sistem kütüphanesi eksik) atlanır.
- Testler PySide6'yı **içe aktarmaz**; çekirdek mantık saf Python'dur. GUI
  yalnızca gerçek bir masaüstünde (smoke testinin arayüz adımlarında) çalışır.
- `test_paths.py` platforma duyarlıdır: macOS'ta `default_root()` Library
  yolunu döner ve XDG testi atlanır.
- `manage.FileLock` POSIX'te (`macOS`/Linux) `fcntl`, Windows'ta `msvcrt` kullanır.
- **Bellek testleri:** `MAMIDLABS_FREE_MEM_MIB` ölçümü geçersiz kılar;
  `_macos_available_mib` `vm_stat` çıktısını ayrıştırır (sahte `subprocess.run`
  ile test edilir).
- **Smoke testi adımları:** `doctor`, `sunucu_baslat`, `saglik`, `sohbet`,
  `grafik`, `cevrimdisi`, `mtp`, `ocr`, `gorsel`, `video`, `sunucu_durdur`.
  Sonuç `logs/smoke-test-son.json`'a yazılır.
- **CI:** her push/PR'da `tests.yml` (macos-latest, Python 3.12).

## 13. Donanım gerçekleri

macOS'ta hız **Metal**'e ve **birleşik bellek** miktarına bağlıdır. NVIDIA
ölçümleri (Windows/Linux) referanstır; Apple Silicon'da sohbet token hızı
benzerdir, görsel/video üretimi (MPS) ise CUDA'ya göre daha yavaştır.

| | 32 GB birleşik bellek (MAX/FLASH) | 16 GB birleşik bellek (LITE) |
|---|---|---|
| Sohbet | Metal'de akıcı (MTP açık) | Metal'de akıcı (MTP açık) |
| Görsel (`yeni`) | dakikalar mertebesi (MPS) | dakikalar mertebesi (MPS) |
| Fotoğraf düzenleme | desteklenir | **desteklenmiyor** |
| Ses dökümü | CPU (int8) | CPU (int8) |

27B model GPU/GPU-benzeri bütçede ~15 GB yer kaplar (dosya ~14,6 GB; KV cache
q4_0 + hesap tamponları + MTP draft bağlamı). Bu yüzden MAX/FLASH payı **750
MiB**'dir: model ancak tam sığacaksa yüklenir ve tüm kullanılabilir belleği
kullanır.

**`kimlik_duzenle` neden LITE'ta yok:** Krea2EditGroundedEncode metin/görsel
kodlayıcıyı (~5 GB) ve difüzyon modelini (~7,5 GB) aynı grafikte tutar; toplam
LITE bütçesini aşar. Bu yüzden LITE'ta mod hiç sunulmaz.

**Ses dökümü:** macOS'ta CTranslate2'nin Metal arka ucu yoktur; hattın tamamı
CPU'da (int8) çalışır. Bu yüzden dil-modeli swap'ı gerekmez ve `choose_plan`
macOS'ta her zaman `('cpu', False)` döner.

## 14. Kritik tuzaklar

1. **Kurulum kökünü `__file__`'dan türetme.** Paket `site-packages` içinde
   yaşar; işçiler kökü `MAMIDLABS_ROOT` → `~/Library/Application Support/mamidlabs`
   ile okur (`workers/_root.py`). İşçiye yeni yol eklerken sabit yol yazma.
2. **KV önbellek eşleşmesi.** Arayüzün sakladığı mesaj dizisi, sunucunun o turda
   işlediğiyle bayt bayt aynı olmalı. Araç çağrısı/sonucu saklanmazsa ya da sistem
   istemi tura göre değişirse bağlam her turda baştan işlenir. Tura özel metni son
   kullanıcı mesajına koy.
3. **Bellek payı profile göre** (MAX/FLASH 750 MiB tolerans 0; LITE 300 MiB tolerans
   1024 MiB). macOS'ta ölçüm `vm_stat`'tan gelir; "Pages free" **tek başına
   kullanılmaz** (macOS dosya önbelleğini bilerek büyük tutar) — geri kazanılabilir
   sayfalar (free + inactive + speculative + purgeable) toplanır. Model
   yüklenmeden önce boştaki ComfyUI **her zaman** kapatılır.
4. **ComfyUI bir süreç çiftidir** (venv başlatıcı + base python çocuğu). Kaçak
   kararı süreç **sayısıyla** değil **kökleriyle** verilir; tek sağlıklı örnek zaten
   2 süreçtir.
5. **`/proc` macOS'ta yoktur.** `manage._exe_for` Linux dışında boş döner (kök
   eşleşmesi `ps -ww` ile gelen tam komut satırından yapılır); port dinleyicisi
   Linux'ta `/proc`, macOS'ta `lsof` ile bulunur.
6. **`fcntl` POSIX'e özgüdür.** macOS'ta vardır; `manage.FileLock` yine de tembel
   içe aktarır ve Windows'ta `msvcrt`'ye düşer (testler Windows'ta da geçer).
7. **`done.data` boş olabilir.** İşçi araç çağrısı yokken boş liste koyar; arayüz
   `if data:` koruması kullanır (boş diziyi koşulsuz birleştirme).
8. **Tek görsel kuralı.** Sohbete aynı anda yalnızca bir görsel gider (çoklu görsel
   yalnızca OCR ile).
9. **`settings/api.json`'u uygulama açıkken elle değiştirme;** çıkışta bellekteki
   kopya yazılır.
10. **`run_command` `/bin/zsh -lc` ile çalışır** (macOS varsayılan kabuğu) ve
    kullanıcı onayı ister. Kabuk kaçışları Windows'taki `.cmd` tuzaklarından
    farklıdır; komutu tek satır tut.
11. **PySide6 yalnızca gerçek masaüstünde gerekir.** Çekirdek testler GUI'yi içe
    aktarmaz; CI'da PySide6 kurulmadan da geçer.
12. **Sürüm iki yerde:** `mamidlabs/__init__.py:__version__` ve
    `pyproject.toml:version`. İkisini birlikte artır.
13. **`.app` şablonları yer tutucu içerir;** `packaging/Info.plist` `@VERSION@`,
    `packaging/MacOS-MamidLabs` `@ROOT@` içerir. Kurulum `sed` ile gerçek
    değerlerle değiştirir. Doğrudan kopyalamayın.
14. **macOS bash 3.2.** Betiklerde bash 4+ özelliği (ilişkisel dizi, `mapfile`,
    `${var,,}`, `local -n`) **kullanma**; `realpath -m` de yoktur (yerine Python
    ile `os.path.abspath` kullanılır).
15. **CUDA index'i kullanma.** macOS torch tekerlekleri PyPI'da MPS dahili gelir;
    `download.pytorch.org/whl/cu130` gibi index'ler macOS'ta çalışmaz.
    `nvidia-cublas-cu12`/`nvidia-cudnn-cu12` macOS için yoktur, requirements/asr.txt'te
    **bulunmaz**.
16. **Sihirbaz Qt ve masaüstü ister.** `python3 -m mamidlabs.wizard` PySide6 yoksa
    `wizard.error.no_pyside` ile **2** koduyla çıkar (`wizard/setup.py` bu yüzden
    tembel içe aktarılır); macOS'ta `DISPLAY` denetimi yoktur. Sihirbazın saf
    yardımcıları (`wizard/__init__.py`) Qt olmadan test edilir. Öneri **birleşik
    belleğe** ve Apple Silicon'a bakar; Intel Mac'e yerel profil önerilmez.
17. **macOS bash 3.2.** Sihirbaz/paketleme betikleri dahil tüm `scripts/*.sh`
    `#!/bin/bash` kullanır ve bash 4+ özelliği içermez; `packaging/macos/build-dmg.sh`
    yalnızca macOS'ta (`hdiutil`) çalışır, CI'da yalnızca `bash -n` ile denetlenir.
18. **RAG indeksi güvenilmeyen içeriktir.** `search_folder` sonucu modele
    `[GÜVENİLMEYEN İÇERİK…]` etiketiyle gider ve o turda yazma/çalıştırma onayı
    tetikler. İndeks `tools/rag/bound-<hash>.json`'da tutulur; hash **gerçek yolun
    aynısıyla** (küçük harfe çevrilmeden) alınır (Linux sürümüyle aynı; macOS
    birimleri genelde büyük/küçük harfe duyarsızdır). `hf-hub.py` `HF_HOME`'u
    **import'tan önce** ayarlar; SHA256 uyuşmazsa indirilen dosya silinir (sessiz
    bozuk model bırakılmaz).

## 15. Değişiklik yaparken kontrol listesi

- [ ] İlgili testleri çalıştır; yeni davranışa test ekle (`python -m pytest -q`).
- [ ] Kullanıcıya görünen metin Türkçe ve doğru karakterlerle mi?
- [ ] Kurulum/kaldırma etkisi: yeni dosya ya da klasör kökün dışına yazıyor mu?
      Yazıyorsa kaldırıcıya ekle. Varsayılan olarak her şey kökün altında kalmalı
      (tek istisna: `~/Applications/MamidLabs.app`).
- [ ] `README.md`, `docs/kurulum.md`, `docs/teknik-notlar.md`, `CHANGELOG.md` ve
      **bu dosya** güncel mi?
- [ ] Sunucu argümanları ya da profil sabitleri değişti mi? (Windows sürümüyle
      hizayı koru.)
- [ ] Betik değişiklikleri bash 3.2 ile uyumlu mu (`bash -n` yeterli değil;
      bash 4+ özelliği kullanmadığından emin ol)?
- [ ] Sürüm çıkarılacaksa: `__version__` + `pyproject.toml`, CHANGELOG bölümü ve
      `v<sürüm>` etiketi aynı mı?

## 16. Değişiklik günlüğü

Her özellik/değişiklik için bir satır ekle (en yeni üstte).

| Tarih | Değişiklik | Dosyalar |
|---|---|---|
| 2026-10-18 | **Bağlam sıkıştırma: uzun sohbette taşma zarifçe karşılanır (Windows paritesi).** Sıkıştırma iki geçişli (önce araç çıktısının başı, yetmezse araç/assistant metni kısa işaretle değiştirilir; mesaj silinmez, `tool_calls`/`tool` eşleşmesi korunur). İstem hâlâ sığmıyorsa araçlar sunulmaz, modelden eldeki bulgularla görünür yanıt istenir ve `max_tokens` kalan odaya kısılır; "sıkıştırıldı" durum notu yalnızca gerçekten kısaldıysa gösterilir. | mamidlabs/core/inference.py, mamidlabs/locales/{tr,en}.json, tests/test_inference.py, AGENTS.md, CHANGELOG.md, docs/teknik-notlar.md |
| 2026-10-18 | **Bağlı klasörde yerel (çevrimdışı) RAG: `search_folder` aracı.** Yeni işçi `rag-tools.py` bağlı klasörü tarayıp BM25 (k1=1.2, b=0.75 + 1.6× tam-ifade bonusu) ile en ilgili metin parçalarını `[dosya:satır]` biçiminde döndürür; indeks `tools/rag/bound-<hash>.json`'da dosya imzasıyla (yol+mtime+boyut) önbelleklenir, bozulursa sessizce yeniden kurulur. `node_modules`/`.git`/`venv` gibi klasörler ve ikili/çok büyük dosyalar atlanır; kod çözme utf-8 → cp1254 → latin-1. Araç, bağlı-klasör dosya araçlarıyla aynı kapıdan geçer (ses turunda sunulmaz; `is_file_intent` ise sunulur) ve **güvenilmeyen** sayılır. | mamidlabs/workers/rag-tools.py, mamidlabs/core/tools.py, mamidlabs/core/paths.py, tests/test_rag_tools.py |
| 2026-10-18 | **İstem enjeksiyonuna karşı sertleştirme.** `search_web`/`fetch_page`/`read_document`/`read_images_ocr`/`read_bound_file`/`search_folder` sonuçları modele `chat.untrusted_prefix` etiketiyle sunulur; sistem istemi (`prompt.untrusted`) bu içeriğin **talimat değil veri** olduğunu söyler. O turda güvenilmeyen içerik okunduysa `run_command`/`write_bound_file` "Tam erişim" çipi açıkken bile onay ister (`inference.approval_required`); onay penceresi nedeni yazar (`chat.approval_untrusted`). | mamidlabs/core/inference.py, mamidlabs/ui/main_window.py, mamidlabs/locales/*, tests/test_prompt_injection.py |
| 2026-10-18 | **Otomatik çaba (MAX/FLASH için istek başına).** MAX ve FLASH aynı model olduğundan, `Profiller → "Otomatik çaba (soruya göre)"` açıkken (`api.json:autoEffort`, varsayılan `true`) `inference.auto_reasoning_effort` tur başına `low`/`medium`/`xhigh` seçer ve istek gövdesine `chat_template_kwargs.reasoning_effort` olarak konur (yalnızca yerel sağlayıcı; LITE şablonu yok sayar). Seçim tur boyunca sabit → model yeniden yüklenmez, KV öneki bozulmaz. | mamidlabs/core/inference.py, mamidlabs/core/settings.py, mamidlabs/ui/main_window.py, mamidlabs/locales/*, tests/test_auto_effort.py |
| 2026-10-18 | **Model indirmede SHA256 doğrulama + kaldığı yerden sürme.** `hf-hub.py` eksik dosyayı `hf_hub_download` ile sürdürür, indirme bitince SHA256 doğrular (katalogdaki sabit `sha256` ya da Hugging Face LFS metadata özeti; repo/revision başına önbellek) ve uyuşmazsa bozuk dosyayı siler. `CatalogFile`'a isteğe bağlı `sha256`, kurulum payload'ına `sha256` + `mtp` sözlüğü eklendi (worker `mtpRepo` dizesini de kabul eder). | mamidlabs/workers/hf-hub.py, mamidlabs/core/profiles.py, scripts/install-mamidlabs.sh, tests/test_model_download_integrity.py |
| 2026-10-16 | **Yayın iş akışı eklendi (`.dmg`).** `v*` etiketi itilince `packaging/macos/build-dmg.sh` ile `.dmg` derlenir ve **sabit adla** (`MamidLabs.dmg`) GitHub Release'e yüklenir; README'ye "Hazır paket (.dmg)" bölümü ve `releases/latest/download/MamidLabs.dmg` bağlantısı eklendi. Dal/PR koşuları yalnızca artifact üretir; etiket `__version__` ile eşleşmezse iş durur. | .github/workflows/kurulum-paketi.yml, README.md, CHANGELOG.md, AGENTS.md |
| 2026-10-16 | **Kurulum sihirbazı + donanım ölçümü + `.dmg` paketi eklendi; çalışma anı TR/ENG yerelleştirme bağlandı.** Qt6 `QWizard` (13 sayfa) ilk adımda **Türkçe mi English mi** diye sorar; seçim canlı çevirir ve `settings/api.json:language`'a yazılır. `hwinfo` **birleşik belleğe** bakar (Apple Silicon ≥ 32 GB → PRO, ≥ 16 GB → LITE, Intel/az bellek → API). `packaging/macos/build-dmg.sh` sihirbazı gömen bir `.dmg` üretir (`MamidLabs Kurulum.app` + gömülü kaynaklar). `install-mamidlabs.sh` artık `--language` alıp ilerleme/özet dosyaları yazıyor. i18n kablolaması tüm arayüze, çekirdeğe (`inference`, `tools`, `settings`) ve CLI'a uygulandı; `conftest.py` dil durumunu sıfırlar. Testler: `test_hwinfo.py`, `test_wizard.py` (saf), `test_wizard_gui.py` (başsız Qt), `test_i18n.py`, `test_packaging_contract.py` (toplam 158). | `mamidlabs/core/{i18n,hwinfo}.py`, `mamidlabs/locales/*`, `mamidlabs/wizard/*`, `mamidlabs/ui/*`, `mamidlabs/__main__.py`, `scripts/*`, `packaging/macos/*`, `pyproject.toml`, `conftest.py`, `tests/*`, `README.md`, `CHANGELOG.md` |
| 2026-10-16 | **macOS sürümü ilk kez yazıldı (1.0.0).** Linux portu (Python 3.12 + PySide6/Qt6) temel alınarak macOS'a uyarlandı; sabitler, davranışlar ve araç kümesi Windows sürümüyle birebir korundu. Kurulum kökü `~/Library/Application Support/mamidlabs`; bellek kapısı `nvidia-smi` yerine birleşik bellek (`vm_stat` + `hw.pagesize`, `MAMIDLABS_FREE_MEM_MIB` ile geçersiz kılınabilir); llama.cpp Metal (macos-arm64/x64); torch PyPI'dan (MPS), CUDA index'i ve `nvidia-*` paketleri kaldırıldı; transcriber macOS'ta CPU'ya sabitlendi; `run_command` `/bin/zsh`; web User-Agent macOS; PDF yazı tipleri macOS + matplotlib DejaVu; 7-Zip Homebrew yolları; `.desktop` yerine `.app` paketi (`Info.plist` + `MacOS-MamidLabs` + PNG→ICNS); kurulum/yönetim/kaldırma/smoke betikleri bash 3.2 uyumlu; CI `macos-latest`; testler platforma duyarlı ve yeni bellek testleri eklendi. | tümü |
