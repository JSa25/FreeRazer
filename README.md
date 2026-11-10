# FreeRazer

A small Windows app for remapping the buttons of Razer mice without Razer Synapse. Make profiles, link them to games, and the right one goes onto the mouse when a game is in focus. The mouse keeps the last profile in its own memory, so nothing has to run for it to work.

**Unofficial.** This project is not made, endorsed or supported by Razer Inc. "Razer" and mouse model names are trademarks of their owners and are used here only to say which hardware this works with. No Razer code, artwork or logo is included.

## Supported mice

<details>
<summary>Supported mice (118)</summary>

Names and USB product IDs from [OpenRazer](https://github.com/openrazer/openrazer).

| Mouse | USB product ID |
|---|---|
| Abyssus 1800 | 0x0020 |
| Abyssus 2000 | 0x005E |
| Abyssus Elite (D.Va Edition) | 0x006A |
| Abyssus Essential | 0x006B |
| Abyssus V2 | 0x005B |
| Abyssus | 0x0042 |
| Atheris (Receiver) | 0x0062 |
| Basilisk Essential | 0x0065 |
| Basilisk Mobile (Receiver) | 0x00D4 |
| Basilisk Mobile (Wired) | 0x00D3 |
| Basilisk Ultimate (Receiver) | 0x0088 |
| Basilisk Ultimate | 0x0086 |
| Basilisk V2 | 0x0085 |
| Basilisk V3 35K | 0x00CB |
| Basilisk V3 Pro (Wired) | 0x00AA |
| Basilisk V3 Pro (Wireless) | 0x00AB |
| Basilisk V3 Pro 35K (Wired) | 0x00CC |
| Basilisk V3 Pro 35K (Wireless) | 0x00CD |
| Basilisk V3 Pro 35K Phantom Green Edition (Wired) | 0x00D6 |
| Basilisk V3 Pro 35K Phantom Green Edition (Wireless) | 0x00D7 |
| Basilisk V3 X HyperSpeed | 0x00B9 |
| Basilisk V3 | 0x0099 |
| Basilisk X HyperSpeed | 0x0083 |
| Basilisk | 0x0064 |
| Cobra HyperSpeed Receiver | 0x00DB |
| Cobra HyperSpeed | 0x00DA |
| Cobra Pro (Wired) | 0x00AF |
| Cobra Pro (Wireless) | 0x00B0 |
| Cobra | 0x00A3 |
| DeathAdder 1800 | 0x0038 |
| DeathAdder 2000 | 0x004F |
| DeathAdder 2013 | 0x0037 |
| DeathAdder 3.5G Black | 0x0029 |
| DeathAdder 3.5G | 0x0016 |
| DeathAdder 3500 | 0x0054 |
| DeathAdder Chroma | 0x0043 |
| DeathAdder Elite | 0x005C |
| DeathAdder Essential (2021) | 0x0098 |
| DeathAdder Essential (White Edition) | 0x0071 |
| DeathAdder Essential | 0x006E |
| DeathAdder V2 Lite | 0x00A1 |
| DeathAdder V2 Mini | 0x008C |
| DeathAdder V2 Pro (Wired) | 0x007C |
| DeathAdder V2 Pro (Wireless) | 0x007D |
| DeathAdder V2 X HyperSpeed | 0x009C |
| DeathAdder V2 | 0x0084 |
| DeathAdder V3 HyperSpeed (Wired) | 0x00C4 |
| DeathAdder V3 HyperSpeed (Wireless) | 0x00C5 |
| DeathAdder V3 Pro (Wired) | 0x00B6 |
| DeathAdder V3 Pro (Wired) | 0x00C2 |
| DeathAdder V3 Pro (Wireless) | 0x00B7 |
| DeathAdder V3 Pro (Wireless) | 0x00C3 |
| DeathAdder V3 | 0x00B2 |
| DeathAdder V4 Pro (Wired) | 0x00BE |
| DeathAdder V4 Pro (Wireless) | 0x00BF |
| Diamondback Chroma | 0x004C |
| HyperPolling Wireless Dongle | 0x00B3 |
| Imperator 2012 | 0x002F |
| Lancehead (Wired) | 0x0059 |
| Lancehead (Wireless) | 0x005A |
| Lancehead Tournament Edition | 0x0060 |
| Lancehead Wireless (Receiver) | 0x006F |
| Lancehead Wireless (Wired) | 0x0070 |
| Mamba 2012 (Wired) | 0x0024 |
| Mamba 2012 (Wireless) | 0x0025 |
| Mamba Chroma (Wired) | 0x0044 |
| Mamba Chroma (Wireless) | 0x0045 |
| Mamba Elite | 0x006C |
| Mamba Tournament Edition | 0x0046 |
| Mamba Wireless (Receiver) | 0x0072 |
| Mamba Wireless (Wired) | 0x0073 |
| Naga 2012 | 0x002E |
| Naga 2014 | 0x0040 |
| Naga Chroma | 0x0053 |
| Naga Epic Chroma (Wired) | 0x003E |
| Naga Epic Chroma (Wireless) | 0x003F |
| Naga Epic | 0x001F |
| Naga Hex (Red) | 0x0036 |
| Naga Hex V2 | 0x0050 |
| Naga Hex | 0x0041 |
| Naga Left Handed Edition 2020 | 0x008D |
| Naga Pro (Wired) | 0x008F |
| Naga Pro (Wireless) | 0x0090 |
| Naga Trinity | 0x0067 |
| Naga V2 HyperSpeed (Receiver) | 0x00B4 |
| Naga V2 Pro (Wired) | 0x00A7 |
| Naga V2 Pro (Wireless) | 0x00A8 |
| Naga X | 0x0096 |
| Naga | 0x0015 |
| Orochi (Wired) | 0x0048 |
| Orochi 2011 | 0x0013 |
| Orochi 2013 | 0x0039 |
| Orochi V2 (Bluetooth) | 0x0095 |
| Orochi V2 (Receiver) | 0x0094 |
| Ouroboros | 0x0032 |
| Pro Click (Receiver) | 0x0077 |
| Pro Click (Wired) | 0x0080 |
| Pro Click Mini (Receiver) | 0x009A |
| Pro Click V2 (Wired) | 0x00D0 |
| Pro Click V2 (Wireless) | 0x00D1 |
| Pro Click V2 Vertical Edition (Wired) | 0x00C7 |
| Pro Click V2 Vertical Edition (Wireless) | 0x00C8 |
| Taipan | 0x0034 |
| Viper 8KHz | 0x0091 |
| Viper Mini SE (Wired) | 0x009E |
| Viper Mini SE (Wireless) | 0x009F |
| Viper Mini | 0x008A |
| Viper Ultimate (Wired) | 0x007A |
| Viper Ultimate (Wireless) | 0x007B |
| Viper V2 Pro (Wired) | 0x00A5 |
| Viper V2 Pro (Wireless) | 0x00A6 |
| Viper V3 HyperSpeed | 0x00B8 |
| Viper V3 Pro (Wired) | 0x00C0 |
| Viper V3 Pro (Wireless) | 0x00C1 |
| Viper V3 Pro SE (Wired) | 0x00DE |
| Viper V3 Pro SE (Wireless) | 0x00DF |
| Viper V4 Pro | 0x00E6 |
| Viper | 0x0078 |

</details>

## Supported keyboards

<details>
<summary>Supported keyboards (73)</summary>

Names and USB product IDs from [OpenRazer](https://github.com/openrazer/openrazer).

| Keyboard | USB product ID |
|---|---|
| Anansi | 0x010F |
| BlackWidow (Classic) | 0x011B |
| BlackWidow 2019 | 0x0241 |
| BlackWidow Chroma (Overwatch) | 0x0211 |
| BlackWidow Chroma V2 | 0x0221 |
| BlackWidow Chroma | 0x0203 |
| BlackWidow Elite | 0x0228 |
| BlackWidow Essential | 0x0237 |
| BlackWidow Lite | 0x0235 |
| BlackWidow Stealth Edition | 0x010E |
| BlackWidow Tournament Edition 2014 | 0x011C |
| BlackWidow Tournament Edition Chroma | 0x0209 |
| BlackWidow Ultimate 2012 | 0x010D |
| BlackWidow Ultimate 2013 | 0x011A |
| BlackWidow Ultimate 2016 | 0x0214 |
| BlackWidow V3 Mini HyperSpeed (Wired) | 0x0258 |
| BlackWidow V3 Mini HyperSpeed (Wireless) | 0x0271 |
| BlackWidow V3 Pro 2.4 Ghz Wireless | 0x025C |
| BlackWidow V3 Pro Wired | 0x025A |
| BlackWidow V3 TK | 0x0A24 |
| BlackWidow V3 | 0x024E |
| BlackWidow V4 75% | 0x02A5 |
| BlackWidow V4 Mini HyperSpeed (Wired) | 0x02B9 |
| BlackWidow V4 Mini HyperSpeed (Wireless) | 0x02BA |
| BlackWidow V4 Pro | 0x028D |
| BlackWidow V4 Tenkeyless HyperSpeed (Wired) | 0x02D7 |
| BlackWidow V4 Tenkeyless HyperSpeed (Wireless) | 0x02D5 |
| BlackWidow V4 X | 0x0293 |
| BlackWidow V4 | 0x0287 |
| BlackWidow X Chroma | 0x0216 |
| BlackWidow X Tournament Edition Chroma | 0x021A |
| BlackWidow X Ultimate | 0x0217 |
| Cynosa Chroma Pro | 0x022C |
| Cynosa Chroma | 0x022A |
| Cynosa Lite | 0x023F |
| Cynosa V2 | 0x025E |
| DeathStalker Chroma | 0x0204 |
| DeathStalker Expert | 0x0202 |
| DeathStalker V2 Pro (Wired) | 0x0292 |
| DeathStalker V2 Pro (Wireless) | 0x0290 |
| DeathStalker V2 Pro TKL (Wired) | 0x0298 |
| DeathStalker V2 Pro TKL (Wireless) | 0x0296 |
| DeathStalker V2 | 0x0295 |
| DeathStalker/DeathStalker Essential | 0x0118 |
| Huntsman Elite | 0x0226 |
| Huntsman Mini Analog | 0x0282 |
| Huntsman Mini JP | 0x0269 |
| Huntsman Mini | 0x0257 |
| Huntsman Tournament Edition | 0x0243 |
| Huntsman V2 Analog | 0x0266 |
| Huntsman V2 Tenkeyless | 0x026B |
| Huntsman V2 | 0x026C |
| Huntsman V3 Pro 8KHz | 0x02CF |
| Huntsman V3 Pro Mini | 0x02B0 |
| Huntsman V3 Pro TKL | 0x02A7 |
| Huntsman V3 Pro | 0x02A6 |
| Huntsman | 0x0227 |
| Joro | 0x02CD |
| Nostromo | 0x0111 |
| Orbweaver Chroma | 0x0207 |
| Orbweaver | 0x0113 |
| Ornata Chroma | 0x021E |
| Ornata V2 | 0x025D |
| Ornata V3 (Alternate) | 0x028F |
| Ornata V3 Tenkeyless | 0x02A3 |
| Ornata V3 X (Alternate) | 0x02A2 |
| Ornata V3 X | 0x0294 |
| Ornata V3 | 0x02A1 |
| Ornata | 0x021F |
| Tartarus Chroma | 0x0208 |
| Tartarus Pro | 0x0244 |
| Tartarus V2 | 0x022B |
| Tartarus | 0x0201 |

</details>

The app only reads and sets button bindings, DPI and polling rate; it never touches firmware or lighting.

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
