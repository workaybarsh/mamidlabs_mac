# MamidLabs macOS paketleme (.dmg)

Bu klasör, MamidLabs macOS sürümünün **`.dmg` disk görüntüsünü** üretir. DMG'nin
içinde **“MamidLabs Kurulum.app”** vardır: kullanıcı uygulamayı `Applications`
klasörüne sürükler ve çalıştırır, sihirbaz donanımı ölçüp uygun profili önerir,
sonra gerçek kurulumu (llama.cpp, ComfyUI, modeller) yapar.

## Neden `.dmg`

Kurulumun kendisi (llama.cpp, ComfyUI, ~36–52 GB model) kullanıcıya sorularak
yapılmalıdır. Bu yüzden DMG *hazır bir kurulum* değil, **kurulum aracını** dağıtır:

1. `MamidLabs-Kurulum-1.0.0.dmg`'yi aç.
2. **MamidLabs Kurulum** uygulamasını `Applications` klasörüne sürükle.
3. Çalıştır → sihirbaz: dil (TR/EN) → karşılama → lisans → klasör → donanım
   raporu → profil (LITE/PRO/indirme yok/kendi modelin) → (kendi modellerin) →
   (API) → (bileşenler) → hazır → kurulum → özet → bitiş.

## Derleme

```bash
packaging/macos/build-dmg.sh
# çıktı: packaging/macos/Output/MamidLabs-Kurulum-1.0.0.dmg
```

Seçenekler: `--output <dizin>`, `--no-icon`.

Gereksinim: **macOS** (`hdiutil`). Simge `.icns` için `sips`/`iconutil` kullanılır
(yoksa ikonsuz derlenir). Derleme makinesinde Python gerekmez; sürüm
`mamidlabs/__init__.py` dosyasından okunur.

## Paketin içeriği

```
MamidLabs Kurulum.app/
  Contents/
    Info.plist                          @VERSION@ ile doldurulur
    MacOS/MamidLabsSetup                yürütücü (PYTHONPATH = gömülü kaynaklar)
    Resources/mamidlabs-src/            mamidlabs/, scripts/, requirements/, EULA.txt, ...
    Resources/mamidlabs.icns            simge (üretilebilirse)
```

Yürütücü sistem Python'unu (ya da Homebrew `python3.12`'yi) bulup
`python3 -m mamidlabs.wizard` çalıştırır. Sihirbaz, `install-mamidlabs.sh`'i DMG
içindeki **gömülü** kopyadan çalıştırır; kurulum kökü varsayılan
`~/Library/Application Support/mamidlabs` (`MAMIDLABS_ROOT` ile değişir), uygulama
paketi de `~/Applications/MamidLabs.app` olarak kurulur.

## Bağımlılıklar

- **Python 3.11–3.13** (`brew install python@3.12`)
- **PySide6** — sihirbaz için: `python3 -m pip install PySide6`

PySide6 yoksa sihirbaz `wizard.error.no_pyside` mesajını yazıp **2** koduyla
çıkar; kurulum terminalden de yapılabilir:

```bash
./scripts/install-mamidlabs.sh --profile flash --language tr
```

## İmzalama (not)

Üretilen `.app`/`.dmg` **imzasızdır**; dağıtım için `codesign` + `notarytool` ile
imzalanıp noterlenmesi gerekir (Apple Developer kimliği). Yerel kullanımda
Gatekeeper "geliştirici doğrulanamadı" uyarısı verirse: sağ tık → **Aç**.
