# Teknik notlar (macOS)

Bu dosya MamidLabs'ın macOS sürümünün tasarım kararlarını ve ölçülmüş
davranışlarını özetler. Geliştirici rehberi için [AGENTS.md](../AGENTS.md).

## 1. Neden baştan yazıldı?

Windows sürümü **PowerShell 7 + WinForms** ile yazılmıştır; ikisi de macOS'ta
yoktur. Bu yüzden macOS sürümü **tek dilde** (Python 3.12 + PySide6/Qt6) yazıldı.
Ancak mimari, sabitler ve davranış Windows sürümüyle **birebir** tutuldu; böylece
üç sürüm aynı şekilde davranır ve aynı modelleri kullanır.

**Yeniden kullanılanlar:** platformdan bağımsız Python işçileri (web arama,
belge G/Ç, OCR, medya, ses dökümü, `mtp_inject`, `hf-hub`, `api-media`). Bunlar
tek-atımlık JSON stdin/stdout sözleşmesini korur ve her biri kendi sanal
ortamında çalışır.

## 2. Kurulum kökü ve yol bağımsızlığı

Kurulum kökü macOS düzenine uyar:
`~/Library/Application Support/mamidlabs`; `MAMIDLABS_ROOT` her şeyi geçersiz
kılar. (macOS dışı ana makinelerde/testlerde XDG'ye düşer.)

İşçiler kökü **kendi konumlarından türetmez** (paket `site-packages` içinde
yaşar). `mamidlabs/workers/_root.py` kökü önce `MAMIDLABS_ROOT`'tan, yoksa
Library varsayılanından okur. `WorkerRunner` her alt sürece `MAMIDLABS_ROOT` ve
`HF_HOME` geçirir; böylece ses modelleri çevrimdışı olarak kurulum kökünün HF
önbelleğinden bulunur.

## 3. Süreçler ve portlar

| Süreç | Port | Sahibi |
|---|---|---|
| `llama-server` | 8080 | `mamidlabs/core/manage.py` (`ModelManager`) |
| ComfyUI (`venv/imagegen`) | 8188 | medya köprüsü / `manage-mamidlabs.sh comfy` |
| Ses döküm işçisi (`venv/asr`) | rastgele, yalnız 127.0.0.1 | `mamidlabs/core/inference.py` |

Model başlatma/durdurma `manage.FileLock` ile serileştirilir (POSIX'te `fcntl`,
Windows'ta `msvcrt` — testler Windows'ta da içe aktarılabilir).

Süreç keşfi taşınabilirdir: `ps -ww -eo pid=,ppid=,args=` (macOS/Linux). Yürütücü
yolu yalnızca Linux'ta `/proc/<pid>/exe`'den okunur; macOS'ta kök eşleşmesi tam
komut satırından yapılır. Port dinleyicisi Linux'ta `/proc`, macOS'ta `lsof` ile
bulunur.

## 4. Profiller ve sunucu argümanları

Profil kataloğu `mamidlabs/core/profiles.py` içindedir; takma adlar
(`PROFILE_ALIASES`) Windows sürümüyle aynıdır:

| Profil | Alias | Önemli bayraklar |
|---|---|---|
| MAX | `qwen3.8-27b-max` | ctx 32768, predict 8192, gpu-layers 99, q4_0 KV, cache-reuse 256, batch 512/256, threads 6/12, `--mmproj --no-mmproj-offload --image-min-tokens 1024`, `--reasoning-effort xhigh`, MTP varsa `--spec-type draft-mtp` |
| FLASH | `qwen3.8-27b-flash` | aynı dosyalar; `--reasoning-effort low` |
| LITE | `qwen3.5-9b-lite` | ctx `liteContext` (32768), predict 8192, batch 256/128, threads 4/8, `--image-min-tokens 512`, `--reasoning-effort low`, MTP varsa `--spec-type draft-mtp` |

Sunucu argümanları Windows sürümüyle **birebir aynıdır**; macOS'ta Metal
varsayılan arka uçtur (`--gpu-layers 99` Metal'e de uygulanır), ek bayrak
gerekmez. MAX ve FLASH aynı dosyaları kullandığından arayüzde tek "Qwen3.8 MAX"
girdisi olarak görünür (`catalog_for_display`); geçiş alt çubuktan yapılır.
Kimliğe göre arama tam kataloğu (`get_profile`) kullanır.

**MTP (Multi-Token Prediction).** `--spec-type draft-mtp` yalnızca GGUF gerçekten
MTP/`nextn` katmanı taşıyorsa eklenir (`manage.gguf_has_mtp`). LITE'ın 9B GGUF'u
bu başlığı dönüşümde kaybeder; indirme sırasında `mtp_inject.py` ile geri eklenir.
Ayrı draft model gerekmez ve çıktı kayıpsızdır. `settings/api.json → mtp=false`
ile kapatılır.

**Bellek kapısı.** Gereken = model dosyası + pay. MAX/FLASH pay **750 MiB**
(tolerans 0: kullanılabilir < gereken ise hata verilir), LITE pay **300 MiB**
(tolerans 1024 MiB: `[gereken-1024, gereken)` aralığında uyarı). Görsel projektör
üç profilde de CPU'dadır (`--no-mmproj-offload`) ve bütçeye girmez. Model
yüklenmeden önce uygulamaya ait artık GPU işçileri (boşta ses/OCR işçisi)
kapatılır (`stop_orphan_workers`).

**macOS'ta ölçüm.** Ayrı VRAM yoktur. `manage.available_memory_mib()` geri
kazanılabilir birleşik belleği döndürür: `vm_stat` çıktısındaki **free +
inactive + speculative + purgeable** sayfalar toplanır ve `hw.pagesize` ile
çarpılır. Yalnızca "Pages free" **kullanılmaz** (macOS dosya önbelleğini bilerek
büyük tutar; tek başına kullanılırsa model asla yüklenemez). `macos_total_mib()`
bilgi amaçlı toplam belleği verir. `MAMIDLABS_FREE_MEM_MIB` ölçümü geçersiz kılar
(testler ve elle ayar). macOS dışı ana makinelerde sırasıyla `nvidia-smi` ve
`/proc/meminfo` denenir.

## 5. ComfyUI yaşam döngüsü

ComfyUI **yalnızca medya üretiminde** çalışır; iş bitince ve dil modeli
yüklenmeden önce kapatılır (boşta ne bellek ne GPU tutar). `comfyKeepAlive=true`
ile LITE'ta medya işleri arasında açık tutulabilir. Kaçak/mükerrer örnekler süreç
**köklerine** göre sayılır (ComfyUI bir süreç çiftidir), `:8188`'i dinleyen tek
örnek korunur.

macOS'ta ComfyUI **MPS** ile çalışır; `venv/imagegen` içindeki torch PyPI
tekerleğidir (MPS dahili), CUDA index'i kullanılmaz.

## 6. API sağlayıcıları

Tek tablo `providers.py` içindedir: `openai`, `claude`, `gemini`, `deepseek`,
`custom`. `custom`, OpenAI uyumlu kullanıcı ucudur; anahtar isteğe bağlıdır
(boşsa `Authorization` başlığı gönderilmez).

- **Claude dönüştürücüsü:** OpenAI chat biçimini Claude Messages API'sine ve geri
  çevirir. `thinking` alanı gönderilmez; `tool_choice` yalnızca gövdede varsa
  `auto` olarak gider; `max_tokens` alt sınırı 16000'dir. Araç döngüsünde imzalı
  `thinking` blokları `ClaudeStream` ile toplanır ve ilk `tool_use` kimliği
  üzerinden sırası bozulmadan geri gönderilir (yalnızca bellekte).
- **DeepSeek** görsel kabul etmez; `image_url` parçaları metin notuna indirilir.
- Anahtarlar tercihen macOS oturum anahtarlığında (Keychain / `keyring`), yoksa
  `settings/api.json` içinde `0600` izinle saklanır (`Settings.secret_backend`
  hangisinin kullanıldığını bildirir).

## 7. Sohbet akışı ve bağlam

- Sistem istemi sabittir (`SYSTEM_PROMPT`); tura özel ipuçları sistem istemine
  değil, **son kullanıcı mesajının başına** eklenir — böylece sunucunun KV
  önbellek öneki bozulmaz.
- `done` olayı o turda eklenen `assistant.tool_calls` ve `tool` mesajlarını da
  taşır; arayüz bunları kalıcı geçmişe ekler (eklenmezse sonraki turda istemci
  öneki sunucununkinden farklı olur ve bağlam baştan işlenir).
- Bağlam eşiğine yaklaşılınca en eski araç çıktıları kısaltılır
  (`compact_turn_messages`); mesaj silinmez, `assistant.tool_calls`/`tool`
  eşleşmesi bozulmaz.

### Web başarısızlığı dürüstlüğü

Bir turda yapılan web çağrılarının **hiçbiri** başarılı olmadıysa
(`WebTracker.unavailable = fail_count > 0 and not success`) modele "internet yok"
notu verilir ve güncel bilgi isteyen turda uydurma engellenir. **Kısmi başarı**
(örneğin 7 çağrının 4'ü başarılı) başarısızlık **sayılmaz**; yanıt gerçek kaynağa
dayanır ve uydurma "Kaynak:"/URL satırları ayıklanır (`strip_fabricated_citations`).

## 8. Araç kapıları

Üretim araçları (görsel/video/belge/grafik) yalnızca niyet varsa **sunulur** ve
**çağrı anında** yeniden denetlenir. `run_command` yalnızca kullanıcı açıkça
komut istediğinde (`/bin/zsh -lc`); bağlı klasör araçları yalnızca "Ajan" çipi
açıkken; `read_document` yalnızca belge bağlamı varken sunulur. Web araçları, hiç
başarılı çağrı olmadan ≥2 hata sonrası kilitlenir. Ses eki olan turda modele
bağlı-klasör **dosya** araçları sunulmaz (ses zaten yazıya çevrilir).

## 9. Grafik çizimi

`chart.py` matplotlib kullanır (Windows'taki `System.Drawing` karşılığı).
`function` türü için ifade, `eval` yerine **güvenli AST çözümleyicisi** ile
değerlendirilir (yalnızca sayılar, `x`, izinli fonksiyonlar ve operatörler).
Sonuç sohbette gösterilir ve `outputs/charts` altına kaydedilir.

## 10. Ses dökümü

Motor `faster-whisper large-v3-tr` + AST ses olayları + opsiyonel pyannote
konuşmacı ayrımıdır. Çıktı **kronolojik ve zaman damgasızdır**:
`(ayak sesleri)` / `Konuşmacı: ...` satırları. Ses olayları varsayılan **açık**
(`settings/api.json → audioEvents`).

macOS'ta CTranslate2'nin Metal arka ucu yoktur; hat **CPU'da (int8)** çalışır.
Bu yüzden cihaz seçimi kısa devre yapar: `config.choose_plan` macOS'ta her zaman
`('cpu', False)` döner (dil-modeli swap'ı gerekmez). `available_ram_mib` ve
`total_vram_mib` macOS'ta birleşik bellek ölçümünü kullanır.

## 11. Donanım gerçekleri

macOS'ta hız Metal'e ve birleşik bellek miktarına bağlıdır. NVIDIA ölçümleri
(Windows/Linux) referanstır.

| | 32 GB birleşik bellek (MAX/FLASH) | 16 GB birleşik bellek (LITE) |
|---|---|---|
| Sohbet | Metal'de akıcı (MTP açık) | Metal'de akıcı (MTP açık) |
| Görsel (`yeni`) | dakikalar mertebesi (MPS) | dakikalar mertebesi (MPS) |
| Fotoğraf düzenleme | desteklenir | **desteklenmiyor** |
| Ses dökümü | CPU (int8) | CPU (int8) |

27B model GPU/GPU-benzeri bütçede ~15 GB yer kaplar (dosya ~14,6 GB iken KV cache
q4_0 + hesap tamponları + MTP draft bağlamı ile); MAX/FLASH payı bu yüzden 750
MiB'dir: model ancak **tam sığacaksa** yüklenir ve **tüm kullanılabilir belleği
kullanır**.
