# FreeRazer

A small Windows app for remapping the buttons of Razer mice without Razer Synapse. Make profiles, link them to games, and the right one goes onto the mouse when a game is in focus. The mouse keeps the last profile in its own memory, so nothing has to run for it to work.

**Unofficial.** This project is not made, endorsed or supported by Razer Inc. "Razer" and mouse model names are trademarks of their owners and are used here only to say which hardware this works with. No Razer code, artwork or logo is included.

## Supported mice

| Mouse | USB product ID | Status |
|---|---|---|
| Viper V4 Pro (dongle and cable) | 0x00E6 | Verified: read and write |
| Any other Razer mouse | | Read-only: the app shows its bindings but won't change them |

Writes are refused for any mouse or button that is not in a verified entry of the device table (`DEVICES` in `razer_switch.py`). The app only ever reads and sets button bindings; it never touches firmware, lighting or DPI tables.

Want your mouse supported? See [Adding a mouse](#adding-a-mouse).

## Features

- Remap any button except left click (so you can't lock yourself out): other mouse buttons, keys, key combos such as Ctrl + S, or DPI cycle.
- Record a key or combo by pressing it.
- Profiles per game: link a game's .exe and turn on auto-switch.
- Lives in the system tray; can start with Windows.
- Profiles are stored in `%APPDATA%\FreeRazer\profiles.json`. A `profiles.json` from an older version next to the app is copied there on first start (the old file is left as a backup).

Close Razer Synapse while using this; both talk to the mouse.

## Running from source

Needs Windows and Python 3.13.

```bash
py -3.13 -m pip install hidapi pystray pillow
```

```bash
pyw -3.13 freerazer.pyw
```

Command line (`py -3.13 razer_switch.py ...`):

| Command | What it does |
|---|---|
| (none) / `list` | list profiles |
| `apply NAME` | put a profile on the mouse |
| `show` | print what the mouse has on each button |
| `auto` | switch profiles by focused program |
| `probe` | read-only report for adding a new mouse |
| `test` | offline self-check (no mouse needed) |

## Building, installing and releasing

You need Python 3.13 with `hidapi pystray pillow pyinstaller`, and Inno Setup 6:

```bash
py -3.13 -m pip install hidapi pystray pillow pyinstaller
```

```bash
winget install JRSoftware.InnoSetup
```

Build the app, its installer and the installer's checksum (all land in `dist\`):

```bash
powershell -ExecutionPolicy Bypass -File build.ps1
```

`build.ps1` reads the version from `APP_VERSION` in `freerazer.pyw`, runs the self-check, builds `FreeRazer.exe` with PyInstaller and then `FreeRazerSetup.exe` with Inno Setup. The exe leaves out modules the app never loads, which keeps it around 12 MB instead of 31 MB. Each excluded module was checked against a run that used every feature. Do not exclude `bz2`, `lzma`, `decimal`, `PIL.ImageFont` or `PIL._imagingft`: the tray icon and the drawing code need them.

**Installing:** run `FreeRazerSetup.exe`. It installs for the current user only (no admin) into `%LOCALAPPDATA%\Programs\FreeRazer`, adds a Start menu entry so Windows search finds it, and lists it under Settings > Apps > Installed apps, where Uninstall removes it again. Running a newer Setup upgrades in place.

**Releasing an update:** bump `APP_VERSION`, run `build.ps1`, then:

```bash
powershell -ExecutionPolicy Bypass -File release.ps1 -Notes "What changed"
```

Installed copies check GitHub Releases at most once a day (or when you click Check for updates in Settings or the tray menu) and ask before updating; the pop-up never appears while a linked game is in focus. On Update now they download `FreeRazerSetup.exe`, check it against the published `.sha256`, and install it silently. While the repo is private, each PC needs a read-only token in Settings > Updates; remove it once the repo is public.

## Adding a mouse

You need the mouse, and only a few minutes. Nothing is written to the mouse.

1. Close Razer Synapse.
2. Run `py -3.13 razer_switch.py probe` and wait for it to finish (it reads about 130 values).
3. Open an issue titled "Add <your mouse name>" and paste the whole report. Also list the physical buttons your mouse has (for example: 2 side buttons, DPI button on top) and, if you know them, what each does at factory settings.

What the report contains: the USB product IDs of your Razer devices, which transaction ID the mouse answers to, and what the mouse returns for button IDs 1 to 127. Some IDs that aren't real buttons return leftover memory, which is why a report alone isn't enough and an owner has to confirm.

From that, a new entry goes into `DEVICES` with `'verified': False`. The owner then tries one change on a test build (set a side button to a key, check it, reset it), and the entry is marked verified.

A device entry looks like this:

```python
{'name': 'Viper V4 Pro', 'pids': (0x00E6,), 'txn': 0x1F, 'verified': True, 'drawing': 'viper-v4-pro',
 'buttons': {1: ('Left Click', 'mouse:left'), 2: ('Right Click', 'mouse:right'), ...}}
```

Mice without their own drawing get a generic one (`'drawing': 'generic'`).

## Protocol notes

Captured from Razer's web configurator via WebHID on the owner's own mouse. Feature report 0, 90 bytes: byte 0 status (02 ok, 01 busy), byte 1 transaction ID, byte 5 data size, bytes 6-7 command class and ID, arguments from byte 8, byte 88 the XOR of bytes 2-87. Set a button: class 02 ID 0C, arguments `[profile 01, button, hypershift 00, action type, payload length, payload]`; read: ID 8C. Action types: 01 mouse button, 02 key `[modifiers, HID usage]` (Ctrl 01, Shift 02, Alt 04), 06 DPI.

## Licence

MIT, see [LICENSE](LICENSE).
