<div align="center" style="text-align: center;">
<h1><img src="icon.ico" height="30px">  maxstellar's Biome Macro</h1>
<p> A small macro that detects biomes in the Roblox game Sol's RNG.<br>This macro started as a small project to detect biomes even when I was using my PC for other things.</p>

![GitHub Downloads (all assets, all releases)](https://img.shields.io/github/downloads/purestellenium/maxstellar-Biome-Macro/total)
![GitHub Release](https://img.shields.io/github/v/release/purestellenium/maxstellar-Biome-Macro)
![GitHub License](https://img.shields.io/github/license/purestellenium/maxstellar-Biome-Macro)
</div>

## Features
- Biome detection without OCR — reads Roblox's own log, never touches the game
- Per-biome Discord webhook messages, pings, or silence
- Multi-webhook support
- Desktop notifications
- Biome duration reported when a biome ends
- Survives Roblox restarts and log rotation without needing a macro restart
- Unknown biomes are still reported, so a game update can't silence it

## Installation
Download the [latest release](https://github.com/purestellenium/maxstellar-Biome-Macro/releases/latest) and put it in an empty folder. Run the .exe file and configure to your liking.<br><br>
Alternatively, if you already have Python installed, download the Python file along with the required libraries and images, and run it from command line or with your preferred method.

```
pip install -r requirements.txt
python BiomeMacro.py
```

## Adding a new biome
When Sol's RNG adds a biome you don't need to touch the code — edit **`biomes.json`** and add one entry:

```json
{ "name": "EXAMPLE BIOME", "label": "Example Biome", "color": "AABBCC", "default": "Ping", "everyone": false }
```

- `name` **must match the rich-presence hover text exactly**, in uppercase, as Roblox writes it to the log.
- `color` is the embed colour, hex, no `#`.
- `default` is the starting notification setting (`Message`, `Ping`, or `Nothing`); after that it's remembered in `config.ini`.
- `everyone` sends `@everyone` regardless of the per-biome setting.

The biome then shows up automatically in **Configure Pings**. If a biome appears that isn't in the file yet, the macro still reports it with a fallback colour and notes it in `crash.log`, so you'll never silently miss one.

To find the exact name a new biome uses, trigger it once and search your latest Roblox log for `SetRichPresence` — the `largeImage.hoverText` value is the name. Note it must come from `largeImage`; `smallImage` always reads `Sol's RNG` and is not a biome.

When running the .exe, edit the `biomes.json` that appears next to it — no rebuild needed.

## Common Issues
### Macro doesn't detect biomes
- Make sure your PC time is not offset (early or late)
- Check `crash.log` (Settings → View crash.log) — webhook and parsing failures are recorded there now

### Macro won't launch (shows error message)
- Make sure the zip file downloaded was extracted fully (into a folder)
- Make sure you are running the macro from the extracted folder (and not from the Home page of File Explorer)
- Make sure `biomes.json` is in the same folder as the macro
- Delete and reinstall macro

## Changelog

### v2.5
- Added **Blazing Sun** (confirmed against real Roblox logs)
- Removed Pumpkin Moon and Graveyard

**Critical fix — the webhook spam**
- **The macro could replay the whole log and fire hundreds of webhooks.** It tailed the log in text mode, where `tell()` returns an opaque decoder cookie rather than a byte offset — on a real Roblox log it comes back as ~1.8×10¹⁹. The truncation check read that as "the file shrank", rewound to the top and re-announced every biome in the file's history as if it were live. On a real 8.7 MB log this fires 54 times. The log is now read in binary, where `tell()` is a true byte offset. A second guard suppresses any repeat of the same biome within 5 seconds, so nothing can spam like that again.

**Plugins**
- A `plugins/` folder is created next to the .exe on first run, with `_template.py` to copy and a `README.txt` documenting the API. Drop a `.py` file in and it loads on the next start.
- Plugins can react to `biome_start`, `biome_end`, `macro_start` and `macro_stop`, add their own tab, send webhooks, and reach the rest of the macro.
- A plugin that crashes is disabled for the session and logged. It can never stop biome detection.
- **Plugins are ordinary Python with full access to your PC — only use ones from people you trust.**

**Overhauls**
- **Webhook sending moved off the detection thread.** It used to send inline — a slow Discord, or three retries with backoff, stalled biome detection for seconds while the log kept moving. Messages now go to a queue drained by a dedicated sender, order preserved, and detection never waits on the network.
- Multi-webhook URLs are re-read when you press Start instead of only at launch, so editing `config.ini` no longer needs a restart.
- `biome_history.csv` rolls over at 5 MB instead of growing forever, the same as `crash.log`.
- Stopping the macro no longer leaves Tk callbacks firing after the window is destroyed.
- Stopping and restarting within 5 seconds no longer suppresses the first biome.

**Detection accuracy**
- **It now reads the biome you are in the moment it attaches**, from the last rich-presence line in the log, instead of waiting for the next change. Starting the macro during a rare biome used to report nothing at all.
- **Only fully capitalised hover text counts as a biome.** The presence payload also carries `Sol's RNG`, and anything mixed-case is a title, not a biome — so a payload change can never turn the game's name into a fake biome alert.

**Critical fixes**
- **The macro attached to the Roblox Studio log instead of the game log.** It picked the newest log file by creation time, and a Studio log is still a `.log` in the same folder — so if you had opened Studio more recently than the game, the macro sat watching a file that contains no biomes at all and detected nothing, forever. It now only ever attaches to a Player log, chosen by *modification* time so it follows the one actually being written. **This affected anyone with Roblox Studio installed and has been present since long before this release.**
- Removed Blood Rain.

- **The macro refused to detect anything if the Discord User ID field was empty.** That field is only needed for pings, but the check ran before detection started, so a default config (which ships with it blank) meant hitting Start did nothing at all. Leaving it empty is now fine — you just don't get pinged.

**Lighter and quieter**
- The .exe is **half the size**: 30 MB → 15 MB. Desktop notifications no longer need `win11toast`, which was pulling in 11 MB of Windows SDK binaries for one popup; they now use a native tray notification with no dependency at all
- Idle CPU cut by ~95%. The macro was scanning every process on your PC ten times a second just to ask whether Roblox was open — now it asks every two seconds
- Biome parsing is ~4x faster and no longer depends on the log line being perfectly formed JSON

**Quality of life**
- Biome history saved to `biome_history.csv` (biome, start/end, duration)
- Session summary posted when you stop: what you caught and how long you ran
- Current biome shown in the window title
- Ping ID can be treated as a **role** instead of a user
- Roblox username is attached to biome embeds
- Test Webhook button
- Failed webhooks now retry, including proper handling of Discord rate limits
- `crash.log` rotates at 2 MB instead of growing forever
- **Fixed:** when built as an .exe, `config.ini` and `crash.log` were written into PyInstaller's temporary extraction folder, so settings reset on every launch. They now sit next to the .exe, and `biomes.json` is seeded beside it so biomes can be added without a rebuild
- Biomes moved to `biomes.json`; adding one no longer needs a code change
- Unknown/new biomes are reported instead of being silently dropped
- **Fixed:** Heaven and Singularity never sent anything (a variable was assigned twice, so Singularity's setting was never created)
- **Fixed:** biomes set to "Nothing" still fired an empty webhook, which Discord rejects
- **Fixed:** Heaven and Singularity had settings but no UI to change them
- **Fixed:** the macro kept tailing a dead log after a Roblox rejoin — this was the real cause of "macro doesn't detect biomes", so closing all Roblox instances is no longer needed
- **Fixed:** the detection loop re-entered itself on every Roblox restart, leaking file handles and eventually overflowing the stack
- **Fixed:** closing any child window could stop the macro (`<Destroy>` fires for child widgets too)
- Detection moved to a background thread — the window no longer freezes
- Errors are logged instead of silently swallowed by bare `except: pass`
- **Fixed:** pausing discarded log lines outright, so resuming could miss the biome you were already in
- Glitched, Dreamspace, Cyberspace and Singularity stay hard-coded and out of Configure Pings, as before — they are still detected and still ping
- **Fixed:** if the detection thread died, the window still said "Running" while nothing was being watched. It now says so and tells you to check the log
- **Fixed:** a slow Discord response could freeze the window when closing the macro
- **Fixed:** webhook validation accepted any URL containing the word "discord", so a channel link passed and then failed silently at send time
- New **Settings** tab: Appearance, desktop notifications and start-on-launch, plus Test Webhook / Open Folder / View Log / Reset. Everything else lives in `config.ini`. The Webhook and Credits tabs are pixel-identical to before, and the window is still 505x285
- Removed the dead "Aura Detection [Not Working]" controls, which had no code behind them

Enjoy!
