# MamidLabs macOS packaging (.dmg)

This folder produces the **`.dmg` disk image** of the MamidLabs macOS edition. The DMG
contains **“MamidLabs Setup.app”**: the user drags the app into `Applications` and runs
it, the wizard measures the hardware and suggests a suitable profile, then performs the
real installation (llama.cpp, ComfyUI, models).

## Why `.dmg`

The installation itself (llama.cpp, ComfyUI, ~36–52 GB of models) has to happen with the
user's consent. That is why the DMG does not ship a *ready installation* but the
**installer tool**:

1. Open `MamidLabs-Setup-1.0.0.dmg`.
2. Drag the **MamidLabs Setup** app into the `Applications` folder.
3. Run it → wizard: language (EN/TR) → welcome → licence → folder → hardware
   report → profile (LITE/PRO/no download/own model) → (your own models) →
   (API) → (components) → ready → install → summary → finish.

## Building

```bash
packaging/macos/build-dmg.sh
# output: packaging/macos/Output/MamidLabs-Setup-1.0.0.dmg
```

Options: `--output <dir>`, `--no-icon`.

Requirement: **macOS** (`hdiutil`). `sips`/`iconutil` are used for the `.icns` icon
(without them it is built without an icon). Python is not needed on the build machine;
the version is read from `mamidlabs/__init__.py`.

## Package contents

```
MamidLabs Setup.app/
  Contents/
    Info.plist                          filled in with @VERSION@
    MacOS/MamidLabsSetup                launcher (PYTHONPATH = embedded sources)
    Resources/mamidlabs-src/            mamidlabs/, scripts/, requirements/, EULA.txt, ...
    Resources/mamidlabs.icns            icon (when it can be generated)
```

The launcher finds the system Python (or Homebrew `python3.12`) and runs
`python3 -m mamidlabs.wizard`. The wizard runs `install-mamidlabs.sh` from the
**embedded** copy inside the DMG; the install root defaults to
`~/Library/Application Support/mamidlabs` (changed with `MAMIDLABS_ROOT`), and the
application bundle is installed as `~/Applications/MamidLabs.app`.

## Dependencies

- **Python 3.11–3.13** (`brew install python@3.12`)
- **PySide6** — for the wizard: `python3 -m pip install PySide6`

Without PySide6 the wizard prints the `wizard.error.no_pyside` message and exits with
code **2**; the installation can also be done from the terminal:

```bash
./scripts/install-mamidlabs.sh --profile flash --language en
```

## Signing (note)

The generated `.app`/`.dmg` is **unsigned**; distribution requires signing with
`codesign` and notarising with `notarytool` (an Apple Developer identity). For local use,
if Gatekeeper warns that the developer cannot be verified: right-click → **Open**.
