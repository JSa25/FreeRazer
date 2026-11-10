# Plan: from one-mouse tool to an open-source project

## What is per-model

| Item | V4 Pro value | Varies by model? | Can be read without writing? |
|---|---|---|---|
| USB vendor ID | 0x1532 | No (all Razer) | Yes, from USB enumeration |
| USB product ID | 0x00E6 (dongle and cable both) | Yes; some mice have separate wired / dongle / Bluetooth PIDs | Yes |
| Transaction ID (byte 1) | 0x1F | Yes; older Razer generations use other values | Yes: try a few on a read and see which one answers `02` |
| Profile slot | 0x01 | Maybe (mice with on-board profile slots) | Partly |
| Button IDs | 1,2,3,4,5,9,10,0x60 | Yes (extra side buttons, sniper, tilt wheel, DPI up/down) | Partly: unused IDs answer with leftover memory, so a read alone does not prove an ID is real |
| Factory action per button | see `BUTTONS` | Yes | Yes, if read on a mouse still on factory settings |
| Drawing + label layout | traced from the owner's photo | Yes | No; generic drawing otherwise |
| Packet layout, checksum, action encoding (mouse / key / DPI) | 90-byte report, XOR 2..87 | Probably shared within a generation | Encoding of writes can't be proven without writing |

## Where model data comes from

1. **Contributors' `probe` reports** (preferred). `probe` is read-only: it lists Razer HID devices, finds the transaction ID that answers, and reads button IDs 1..0x7F with command class 0x02 / id 0x8C. A maintainer turns the report into a device entry.
2. **Verification by the owner of that mouse**: the new entry starts as `verified: False` (read-only in the app). The owner sets one button, checks it works, resets it, then the entry is marked verified.
3. **OpenRazer** (GPL-2.0) lists PIDs and transaction IDs for many mice, but not button remapping. Bare USB IDs are facts, also public in `usb.ids`. Copying OpenRazer's tables or code would make this project a GPL-2.0 derivative. Plan: don't copy it; build entries only from probe reports.

## Licence implications

- **MIT** (or Apache-2.0): simplest for users and forks. Requires not importing OpenRazer code/tables.
- **GPL-2.0-or-later**: would allow pulling in OpenRazer data later; derived work must stay GPL.
- Either way: no Razer code, artwork or logo is used (the icon and drawing are original), and the README says "unofficial, not affiliated with Razer".

## What can and can't be supported without owning each mouse

- **Can**: detect any Razer mouse by PID; read and show bindings; produce probe reports; ship entries contributed by owners.
- **Can't (safely)**: write to a model nobody has verified. A wrong transaction ID just fails, but a wrong button ID could write into memory that isn't a button. So unknown or unverified models are **read-only**, and writes are refused for any button ID not in a verified entry.
- **Never**: firmware updates, DPI stage tables, lighting, or any command other than button read (0x02/0x8C) and button set (0x02/0x0C).

## Steps

1. Device table `DEVICES` in `razer_switch.py`: one entry per model (name, PIDs, transaction ID, buttons with factory action, drawing key, verified flag). V4 Pro is the only verified entry.
2. `Mouse.connect()` detects the model by PID; unknown PIDs connect read-only.
3. `probe` command (read-only, prints a report to paste into an issue).
4. Profiles move to `%APPDATA%\FreeRazer\profiles.json`; an existing `profiles.json` next to the exe/script is copied there once (the original is left in place).
5. Generic mouse drawing for models without their own.
6. Rename the app to "FreeRazer" (MIT licence), README, LICENSE, `.gitignore`, `git init` + first commit. Nothing pushed.
7. Extend `test` for the device table and the write guards; test on the connected V4 Pro (read, write, restore).

Shortcut kept on purpose: profiles store buttons by ID, shared across models (on the V4 Pro, IDs 1-5, 9, 10 match the standard mouse button numbers; assumed the same on other models until probe reports show otherwise). A profile for one model applies only the buttons the connected model has.
