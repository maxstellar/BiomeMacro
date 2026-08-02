import os
import time
import json
import re
import csv
import queue
import shutil
import threading
import webbrowser
import psutil
import discord_webhook
import configparser
import customtkinter
import logging
import sys
import ctypes
import ctypes.wintypes as wintypes
from collections import Counter
from PIL import Image

APP_VERSION = "2.5"
APP_NAME = "maxstellar's Biome Macro"
THUMB_BASE_URL = "https://maxstellar.github.io/biome_thumb/"
FOOTER_ICON_URL = "https://maxstellar.github.io/maxstellar.png"
UNKNOWN_BIOME_COLOR = "ff69b4"

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# When frozen by PyInstaller, __file__ points inside the temporary extraction folder.
# Bundled assets live there, but anything the user owns or edits -- config.ini,
# crash.log, biomes.json -- has to sit next to the .exe or it silently resets every
# launch. Keep the two apart.
if getattr(sys, 'frozen', False):
    BUNDLE_DIR = getattr(sys, '_MEIPASS', _SCRIPT_DIR)
    DATA_DIR = os.path.dirname(sys.executable)
else:
    BUNDLE_DIR = DATA_DIR = _SCRIPT_DIR

_LOG_PATH = os.path.join(DATA_DIR, 'crash.log')
# The old build appended to crash.log forever. Long-running grinders ended up with
# multi-megabyte logs that were useless for support.
try:
    if os.path.exists(_LOG_PATH) and os.path.getsize(_LOG_PATH) > 2 * 1024 * 1024:
        os.replace(_LOG_PATH, _LOG_PATH + '.old')
except OSError:
    pass

logging.basicConfig(
    filename=_LOG_PATH,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('mylogger')


def message_box(text, title):
    ctypes.windll.user32.MessageBoxW(0, text, title, 0)


def my_handler(types, value, tb):
    logger.exception("Uncaught exception: {0}".format(str(value)))
    message_box("Check crash.log for information on this crash.", "Crashed!")
    sys.exit()


# exception handler / logger
sys.excepthook = my_handler


# ---------------------------------------------------------------- biome registry

def biome_slug(name):
    return name.replace(" ", "_").lower()


# Fallback registry, used only if biomes.json is missing or unreadable so the macro
# still runs instead of refusing to start.
FALLBACK_BIOMES = [
    {"name": "WINDY", "label": "Windy", "color": "91F7FF", "default": "Message", "everyone": False},
    {"name": "SNOWY", "label": "Snowy", "color": "C4F5F6", "default": "Message", "everyone": False},
    {"name": "RAINY", "label": "Rainy", "color": "4385FF", "default": "Message", "everyone": False},
    {"name": "SAND STORM", "label": "Sand Storm", "color": "F4C27C", "default": "Message", "everyone": False},
    {"name": "HELL", "label": "Hell", "color": "5C1219", "default": "Message", "everyone": False},
    {"name": "STARFALL", "label": "Starfall", "color": "6784E0", "default": "Message", "everyone": False},
    {"name": "CORRUPTION", "label": "Corruption", "color": "9042FF", "default": "Message", "everyone": False},
    {"name": "NULL", "label": "Null", "color": "000000", "default": "Message", "everyone": False},
    {"name": "GLITCHED", "label": "Glitched", "color": "65FF65", "default": "Ping", "everyone": True},
]


def load_biomes():
    """Prefer the biomes.json sitting next to the exe so users can add a biome without
    a rebuild; fall back to the bundled copy, and seed one on first run."""
    path = os.path.join(DATA_DIR, 'biomes.json')
    if not os.path.exists(path):
        bundled = os.path.join(BUNDLE_DIR, 'biomes.json')
        if os.path.exists(bundled) and bundled != path:
            try:
                shutil.copyfile(bundled, path)
            except OSError:
                path = bundled
        else:
            path = bundled
    try:
        with open(path, 'r', encoding='utf-8') as f:
            entries = json.load(f)['biomes']
    except Exception as exc:
        logger.error("Could not read biomes.json (%s), using built-in list.", exc)
        entries = FALLBACK_BIOMES
    registry = {}
    for entry in entries:
        name = entry['name'].upper()
        registry[name] = {
            'name': name,
            'label': entry.get('label', name.title()),
            'color': entry.get('color', UNKNOWN_BIOME_COLOR),
            'thumbnail': entry.get('thumbnail', name.replace(' ', '_') + '.png'),
            'default': entry.get('default', 'Message'),
            'everyone': bool(entry.get('everyone', False)),
            'configurable': bool(entry.get('configurable', True)),
            'slug': biome_slug(name),
        }
    return registry


BIOMES = load_biomes()


def thumb_url(info):
    """Empty thumbnail in biomes.json means 'no art for this one yet' -- better than
    pointing Discord at a URL that 404s."""
    return THUMB_BASE_URL + info['thumbnail'] if info['thumbnail'] else None


def biome_info(name):
    """Registry entry for a biome, or a synthetic one if the game added a biome we
    don't know about yet. Unknown biomes still notify -- they just use a fallback colour."""
    if name in BIOMES:
        return BIOMES[name]
    return {
        'name': name,
        'label': name.title(),
        'color': UNKNOWN_BIOME_COLOR,
        'thumbnail': name.replace(' ', '_') + '.png',
        'default': 'Message',
        'everyone': False,
        'configurable': False,
        'slug': biome_slug(name),
        'unknown': True,
    }


# ---------------------------------------------------------------- config

config_name = os.path.join(DATA_DIR, 'config.ini')
config = configparser.ConfigParser()

DEFAULTS = {
    'Webhook': {'webhook_url': "", 'private_server': "", 'discord_user_id': "", 'multi_webhook': "0",
                'multi_webhook_urls': ""},
    # aura_* and min_rarity_to_ping are dead keys kept only so a v2.3/v2.4 config.ini
    # still loads without complaint. Nothing reads them.
    'Macro': {'aura_detection': "0", 'aura_ping': "0", 'min_rarity_to_ping': "",
              'roblox_username': "", 'seen_notice': "0"},
    'Settings': {'appearance': "Dark", 'desktop_notifications': "1", 'status_messages': "1",
                 'show_duration': "1", 'autostart': "0", 'poll_interval': "0.1",
                 'history_csv': "1", 'title_biome': "1", 'ping_role': "0",
                 'session_summary': "1"},
    'Biomes': {},
    # per-biome ping target: <slug> = the id, <slug>_type = user|role.
    # Empty means "fall back to the global Discord User ID".
    'BiomePings': {},
}

if os.path.exists(config_name):
    config.read(config_name)


def save_config():
    with open(config_name, 'w') as configfile:
        config.write(configfile)


def ensure_config():
    """Create any missing section/key without clobbering what the user already set.
    This replaces the old try/except-on-missing-key pattern, which left globals undefined."""
    changed = False
    for section, values in DEFAULTS.items():
        if not config.has_section(section):
            config.add_section(section)
            changed = True
        for key, value in values.items():
            if not config.has_option(section, key):
                config.set(section, key, value)
                changed = True
    for info in BIOMES.values():
        # hard-coded biomes keep their fixed behaviour and stay out of config.ini,
        # exactly as they did before biomes.json existed
        if info['configurable'] and not config.has_option('Biomes', info['slug']):
            config.set('Biomes', info['slug'], info['default'])
            changed = True
    if changed:
        save_config()


ensure_config()


def cfg(section, key, fallback=""):
    return config.get(section, key, fallback=fallback)


def set_cfg(section, key, value):
    if not config.has_section(section):
        config.add_section(section)
    config.set(section, key, str(value))
    save_config()


# ---------------------------------------------------------------- UI window

customtkinter.set_default_color_theme("dark-blue")
customtkinter.set_appearance_mode(cfg('Settings', 'appearance', 'Dark'))
root = customtkinter.CTk()
root.title(APP_NAME)
root.geometry('505x285')
root.resizable(False, False)
root.iconbitmap(os.path.join(BUNDLE_DIR, 'icon.ico'))
tabview = customtkinter.CTkTabview(root, width=505, height=230)
tabview.grid(row=0, column=0, sticky='nsew', columnspan=75)
tabview.add("Webhook")
tabview.add("Macro")
tabview.add("Settings")
tabview.add("Credits")
tabview._segmented_button.configure(font=customtkinter.CTkFont(family="Segoe UI", size=16))
tabview._segmented_button.grid(sticky="w", padx=15)

webhookURL = customtkinter.StringVar(root, cfg('Webhook', 'webhook_url'))
psURL = customtkinter.StringVar(root, cfg('Webhook', 'private_server'))
discID = customtkinter.StringVar(root, cfg('Webhook', 'discord_user_id'))
multi_webhook = customtkinter.StringVar(root, cfg('Webhook', 'multi_webhook', '0'))
if multi_webhook.get() != "1" and webhookURL.get() == "Multi-Webhook On":
    webhookURL.set("")
webhook_urls_string = customtkinter.StringVar(root, cfg('Webhook', 'multi_webhook_urls'))
webhook_urls = webhook_urls_string.get().split()
roblox_username = customtkinter.StringVar(root, cfg('Macro', 'roblox_username'))

appearance = customtkinter.StringVar(root, cfg('Settings', 'appearance', 'Dark'))
desktop_notifications = customtkinter.IntVar(root, int(cfg('Settings', 'desktop_notifications', '1')))
status_messages = customtkinter.IntVar(root, int(cfg('Settings', 'status_messages', '1')))
show_duration = customtkinter.IntVar(root, int(cfg('Settings', 'show_duration', '1')))
autostart = customtkinter.IntVar(root, int(cfg('Settings', 'autostart', '0')))
history_csv = customtkinter.IntVar(root, int(cfg('Settings', 'history_csv', '1')))
title_biome = customtkinter.IntVar(root, int(cfg('Settings', 'title_biome', '1')))
ping_role = customtkinter.IntVar(root, int(cfg('Settings', 'ping_role', '0')))
session_summary = customtkinter.IntVar(root, int(cfg('Settings', 'session_summary', '1')))

SETTINGS_TK_VARS = {
    'appearance': appearance, 'desktop_notifications': desktop_notifications,
    'status_messages': status_messages, 'show_duration': show_duration, 'autostart': autostart,
    'history_csv': history_csv, 'title_biome': title_biome,
    'ping_role': ping_role, 'session_summary': session_summary,
}

# per-biome action vars, built from the registry instead of one hand-written global each
biome_vars = {}
for _name, _info in BIOMES.items():
    biome_vars[_name] = customtkinter.StringVar(root, cfg('Biomes', _info['slug'], _info['default']))

seen_notice = cfg('Macro', 'seen_notice', '0')
if seen_notice == "0":
    set_cfg('Macro', 'seen_notice', "1")

# Tk variables are not safe to touch from another thread, so the detection worker reads
# this plain snapshot instead. The UI writes it; the worker only ever reads it.
RT = {
    'targets': [],
    'ps_url': "",
    'disc_id': "",
    'username': "",
    'notifications': True,
    'status_messages': True,
    'show_duration': True,
    'history': True,
    'title_biome': True,
    'ping_role': False,
    'session_summary': True,
    'ping_targets': {},
    'actions': {name: info['default'] for name, info in BIOMES.items()},
}


WEBHOOK_RE = re.compile(r'^https://(?:\w+\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+', re.I)


def valid_webhook(url):
    """'discord' appearing anywhere in the string used to be enough, so a channel link
    or a half-copied URL passed validation and then failed silently at send time."""
    return bool(WEBHOOK_RE.match((url or "").strip()))


def refresh_runtime():
    """Copy everything the worker needs out of the Tk vars. Call from the main thread only."""
    global webhook_urls
    # re-read from config each time: editing multi_webhook_urls used to need a restart
    webhook_urls = cfg('Webhook', 'multi_webhook_urls').split()
    if multi_webhook.get() == "1":
        targets = [u for u in webhook_urls if valid_webhook(u)]
    else:
        url = webhookURL.get().strip()
        targets = [url] if valid_webhook(url) else []
    RT['targets'] = targets
    RT['ps_url'] = psURL.get().strip()
    RT['disc_id'] = discID.get().strip()
    RT['username'] = roblox_username.get().strip()
    RT['notifications'] = desktop_notifications.get() == 1
    RT['status_messages'] = status_messages.get() == 1
    RT['show_duration'] = show_duration.get() == 1
    RT['history'] = history_csv.get() == 1
    RT['title_biome'] = title_biome.get() == 1
    RT['ping_role'] = ping_role.get() == 1
    RT['session_summary'] = session_summary.get() == 1
    for name, var in biome_vars.items():
        # hard-coded biomes ignore config entirely and always use their fixed action
        RT['actions'][name] = var.get() if BIOMES[name]['configurable'] else BIOMES[name]['default']
    RT['ping_targets'] = {
        name: (cfg('BiomePings', info['slug']).strip(),
               cfg('BiomePings', info['slug'] + '_type', 'user').strip().lower())
        for name, info in BIOMES.items()
    }

# ---------------------------------------------------------------- state

log_directory = os.path.expandvars(r"%localappdata%\Roblox\logs")
packages_path = os.path.expandvars(r"%localappdata%\Packages")
roblox_folder = None
roblox_log_path = None
roblox_version = None

started = False
paused = False
stop_event = threading.Event()
ui_queue = queue.Queue()
worker = None

# Desktop notifications via Shell_NotifyIconW. This used to be win11toast, which
# drags in winsdk -- 11 MB of the 31 MB executable for one balloon popup. Same
# notification, no dependency, and it degrades to silence if Windows says no.
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_ICON, NIF_TIP, NIF_INFO = 0x02, 0x04, 0x10
IMAGE_ICON, LR_LOADFROMFILE, LR_DEFAULTSIZE = 1, 0x10, 0x40


class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT),
                ("hIcon", wintypes.HICON), ("szTip", wintypes.WCHAR * 128),
                ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256), ("uVersion", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", wintypes.HICON)]


_tray = {"nid": None, "shown": False, "timer": None}


def _tray_data():
    if _tray["nid"] is not None:
        return _tray["nid"]
    hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
    nid = NOTIFYICONDATA()
    nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
    nid.hWnd = hwnd
    nid.uID = 1
    nid.hIcon = ctypes.windll.user32.LoadImageW(
        None, os.path.join(BUNDLE_DIR, 'icon.ico'), IMAGE_ICON, 0, 0,
        LR_LOADFROMFILE | LR_DEFAULTSIZE)
    nid.szTip = APP_NAME
    _tray["nid"] = nid
    return nid


def _hide_tray():
    _tray["timer"] = None
    if not _tray["shown"]:
        return
    nid = _tray["nid"]
    nid.uFlags = 0
    ctypes.windll.shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
    _tray["shown"] = False


def show_balloon(title, body):
    """Main thread only -- the tray icon belongs to the root window."""
    try:
        nid = _tray_data()
        if not _tray["shown"]:
            nid.uFlags = NIF_ICON | NIF_TIP
            if not ctypes.windll.shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
                return
            _tray["shown"] = True
        nid.uFlags = NIF_INFO
        nid.szInfoTitle = title[:63]
        nid.szInfo = body[:255]
        nid.dwInfoFlags = 0
        ctypes.windll.shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
        # drop the tray icon once the balloon has had its moment, so the macro
        # doesn't leave a permanent icon the old build never had
        if _tray["timer"] is not None:
            root.after_cancel(_tray["timer"])
        _tray["timer"] = root.after(8000, _hide_tray)
    except Exception as exc:
        logger.warning("Desktop notification failed: %s", exc)


def notify_desktop(title, body):
    if RT['notifications']:
        ui_queue.put(("notify", (title, body)))


def set_title(suffix=None):
    ui_queue.put(("title", APP_NAME + (" - " + suffix if suffix else "")))


def get_action(biome_name):
    return RT['actions'].get(biome_name, biome_info(biome_name)['default'])


# ---------------------------------------------------------------- webhooks

def have_valid_webhook():
    refresh_runtime()
    return len(RT['targets']) > 0


webhook_queue = queue.Queue()


def send(embed=None, content=None):
    """Queue a message. Returns immediately.

    Sending used to happen inline on the detection thread, so a slow Discord --
    or three retries with backoff -- stalled biome detection for seconds. The
    log kept moving while we waited. Now a dedicated sender drains this queue,
    order preserved, and detection never blocks on the network.
    """
    if embed is None and not content:
        return
    webhook_queue.put((embed, content))


def flush_webhooks(timeout=3.0):
    """Wait for queued messages to go out, but never hang the UI on shutdown."""
    deadline = time.time() + timeout
    while not webhook_queue.empty() and time.time() < deadline:
        time.sleep(0.05)


def _webhook_worker():
    while True:
        item = webhook_queue.get()
        try:
            if item is not None:
                _send_now(*item)
        except Exception as exc:
            logger.exception("Webhook sender crashed on one message: %s", exc)
        finally:
            webhook_queue.task_done()


def _send_now(embed=None, content=None):
    """The actual HTTP. Runs only on the sender thread."""
    if embed is None and not content:
        return
    targets = RT['targets']
    if not targets:
        logger.warning("Nothing sent: no valid webhook URL configured.")
        return
    for url in targets:
        for attempt in range(3):
            try:
                # timeout matters: without it a slow Discord response hangs the closing
                # of the window, and stalls the detection thread behind it
                hook = discord_webhook.DiscordWebhook(url=url, timeout=10)
                if embed is not None:
                    hook.add_embed(embed)
                if content:
                    hook.set_content(content)
                response = hook.execute()
                status = getattr(response, 'status_code', 200) if response is not None else 200
                if status == 429:
                    # rate limited -- Discord tells us how long to wait. Losing a
                    # Glitched alert to a rate limit is the worst possible failure.
                    try:
                        wait = float(response.json().get('retry_after', 2))
                    except Exception:
                        wait = 2.0
                    logger.warning("Rate limited, retrying in %.1fs", min(wait, 10))
                    time.sleep(min(wait, 10))
                    continue
                if status >= 500:
                    logger.warning("Discord %s, retrying (attempt %d)", status, attempt + 1)
                    time.sleep(1 + attempt)
                    continue
                if status >= 400:
                    logger.error("Webhook rejected (%s): %s", status, response.text[:300])
                break
            except Exception as exc:
                logger.error("Webhook send failed (attempt %d): %s", attempt + 1, exc)
                time.sleep(1 + attempt)
        else:
            logger.error("Gave up sending to a webhook after 3 attempts.")


threading.Thread(target=_webhook_worker, daemon=True, name="webhook-sender").start()


def make_embed(description, color=None, thumbnail=None, include_ps=False):
    embed = discord_webhook.DiscordEmbed(title="[" + time.strftime('%H:%M:%S') + "]", description=description)
    if color:
        embed.set_color(color)
    embed.set_footer(text=f"{APP_NAME} | v{APP_VERSION}", icon_url=FOOTER_ICON_URL)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if include_ps and RT['ps_url']:
        embed.add_embed_field(name="Private Server Link", value=RT['ps_url'])
    if include_ps and RT['username']:
        embed.add_embed_field(name="Player", value=RT['username'])
    return embed



history_lock = threading.Lock()


def write_history(biome, event, duration=""):
    if not RT['history']:
        return
    path = os.path.join(DATA_DIR, 'biome_history.csv')
    try:
        with history_lock:
            # same treatment crash.log gets: roll over instead of growing forever
            if os.path.exists(path) and os.path.getsize(path) > 5 * 1024 * 1024:
                os.replace(path, path + '.old')
            new = not os.path.exists(path)
            with open(path, 'a', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                if new:
                    writer.writerow(["date", "time", "biome", "event", "seconds"])
                writer.writerow([time.strftime('%Y-%m-%d'), time.strftime('%H:%M:%S'),
                                 biome, event, duration])
    except OSError as exc:
        logger.warning("Could not write biome history: %s", exc)


session_counts = Counter()
session_started_at = None


def send_status(text):
    if not RT['status_messages']:
        return
    send(make_embed("[" + time.strftime('%H:%M:%S') + "]: " + text))


def format_duration(seconds):
    seconds = int(seconds)
    if seconds >= 3600:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m {seconds % 60}s"
    if seconds >= 60:
        return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds}s"


_recent_announce = {}
REANNOUNCE_GUARD_SECONDS = 5


def announce_biome_start(biome):
    # Safety net independent of any single bug: if the same biome is announced twice
    # in a few seconds, something is replaying and the user should get one message,
    # not two hundred. Logged loudly so the real fault stays visible.
    now = time.time()
    previous = _recent_announce.get(biome)
    if previous is not None and now - previous < REANNOUNCE_GUARD_SECONDS:
        logger.warning("Suppressed duplicate '%s' announcement %.2fs after the last one.",
                       biome, now - previous)
        return
    _recent_announce[biome] = now

    info = biome_info(biome)
    action = get_action(biome)
    ui_queue.put(("log", time.strftime('%H:%M:%S') + f": Biome Started - {biome}"))
    if info.get('unknown'):
        logger.warning("Unknown biome '%s' -- add it to biomes.json to give it a colour and thumbnail.", biome)
    session_counts[biome] += 1
    write_history(biome, "started")
    fire_event("biome_start", biome)
    if RT['title_biome'] and not paused:
        set_title(biome)
    notify_desktop("Biome Started", biome)
    if action == "Nothing":
        return
    description = "> ## Biome Started - " + biome
    if info.get('unknown'):
        description += "\n> *(new biome -- not in biomes.json yet)*"
    embed = make_embed(description, color=info['color'],
                       thumbnail=thumb_url(info), include_ps=True)
    content = None
    if info['everyone']:
        content = "@everyone"
    elif action == "Ping":
        # a per-biome target wins; otherwise fall back to the global Discord User ID
        target, kind = RT['ping_targets'].get(biome, ("", "user"))
        if not target.isnumeric():
            target, kind = RT['disc_id'], ("role" if RT['ping_role'] else "user")
        if target.isnumeric():
            content = f"<@&{target}>" if kind == "role" else f"<@{target}>"
    send(embed, content)


def announce_biome_end(biome, started_at):
    info = biome_info(biome)
    ui_queue.put(("log", time.strftime('%H:%M:%S') + f": Biome Ended - {biome}"))
    elapsed = int(time.time() - started_at) if started_at else ""
    write_history(biome, "ended", elapsed)
    fire_event("biome_end", biome, elapsed)
    if RT['title_biome'] and not paused:
        set_title("Running")
    if get_action(biome) == "Nothing":
        return
    description = "> ## Biome Ended - " + biome
    if RT['show_duration'] and started_at:
        description += "\n> Lasted " + format_duration(time.time() - started_at)
    send(make_embed(description, color=info['color'], thumbnail=thumb_url(info)))


# ---------------------------------------------------------------- roblox / log discovery

def detect_roblox_version():
    global roblox_log_path, roblox_version, roblox_folder
    for proc in psutil.process_iter(['name']):
        try:
            name = proc.info['name'] or ""
        except Exception:
            continue
        if 'RobloxPlayerBeta.exe' in name:
            if roblox_version != 'player':
                roblox_version = 'player'
                roblox_log_path = log_directory
            return 'player'
        elif 'Windows10Universal.exe' in name:
            if roblox_version != 'store':
                roblox_version = 'store'
                for folder in os.listdir(packages_path):
                    if folder.startswith("ROBLOXCORPORATION.ROBLOX"):
                        roblox_folder = folder
                        roblox_log_path = os.path.join(packages_path, roblox_folder, "LocalState", "logs")
            return 'store'
    return None


_proc_cache = {"at": 0.0, "running": False}


def is_roblox_running():
    """Scanning every process 10x a second to ask one yes/no question costs about
    1% of a core permanently. Roblox does not open and close that fast."""
    now = time.time()
    if now - _proc_cache["at"] < 2.0:
        return _proc_cache["running"]
    _proc_cache["at"] = now
    _proc_cache["running"] = detect_roblox_version() is not None
    return _proc_cache["running"]


def get_latest_log_file():
    if not roblox_log_path or not os.path.isdir(roblox_log_path):
        return None
    try:
        files = [f for f in os.listdir(roblox_log_path)
                 if f.endswith(".log") and "Installer" not in f and "Studio" not in f]
    except OSError as exc:
        logger.error("Could not list log directory: %s", exc)
        return None
    # Only the Player client writes Sol's RNG rich presence. If Roblox Studio has been
    # opened more recently than the game, the old "newest file by creation time" rule
    # picked the Studio log and the macro sat there watching a file that will never
    # contain a biome -- detection silently dead for anyone who has Studio installed.
    candidates = [f for f in files if "_Player_" in f] or files
    if not candidates:
        return None
    # Modified time, not creation time: the live log is the one being written to now.
    latest = max(candidates, key=lambda f: os.path.getmtime(os.path.join(roblox_log_path, f)))
    return os.path.join(roblox_log_path, latest)


def wait_for_log_file(timeout=30):
    """Roblox writes its log a moment after the process appears, so poll instead of
    the old fixed sleep, which sometimes returned 'No log files found'."""
    deadline = time.time() + timeout
    while time.time() < deadline and not stop_event.is_set():
        path = get_latest_log_file()
        if path:
            return path
        time.sleep(0.5)
    return None


# ---------------------------------------------------------------- detection worker

# Pulling the biome straight out of the line survives things json.loads will not:
# trailing text after the JSON object, or a line Roblox only half-flushed. Checked
# against every rich-presence line in the local logs -- identical results, so this is
# insurance rather than a fix.
HOVER_RE = re.compile(r'"largeImage"\s*:\s*\{[^}]*?"hoverText"\s*:\s*"([^"]*)"')
# Biome names are always written in capitals. The game also puts "Sol's RNG" in the
# presence payload, and anything mixed-case like that is a title, not a biome --
# rejecting it means a payload change can never turn the game name into a fake biome.
BIOME_TEXT_RE = re.compile(r"^[A-Z0-9][A-Z0-9 '&:-]*$")


def _clean_hover(hover):
    hover = (hover or "").strip()
    if not hover or not BIOME_TEXT_RE.match(hover):
        return None
    return hover


def parse_hover_text(line):
    if '"command":"SetRichPresence"' not in line:
        return None
    match = HOVER_RE.search(line)
    if match:
        return _clean_hover(match.group(1))
    # fall back to a strict parse in case the presence payload ever changes shape
    start = line.find('{"command":"SetRichPresence"')
    if start == -1:
        return None
    try:
        data = json.loads(line[start:])
    except json.JSONDecodeError:
        return None
    return _clean_hover(data.get("data", {}).get("largeImage", {}).get("hoverText", ""))


def read_current_biome(path, tail_bytes=250000):
    """Whatever the LAST rich-presence line in the file says is the biome you are in
    right now. Without this, starting the macro in the middle of a biome meant it had
    no idea one was running until the next change -- so a rare biome you were already
    sitting in was never reported."""
    try:
        size = os.path.getsize(path)
        with open(path, 'rb') as f:
            if size > tail_bytes:
                f.seek(size - tail_bytes)
                f.readline()  # discard the partial line we landed in
            latest = None
            for raw in f:
                found = parse_hover_text(raw.decode('utf-8', 'ignore'))
                if found:
                    latest = found
            return latest
    except OSError as exc:
        logger.warning("Could not read current biome from %s: %s", path, exc)
        return None


def watch_loop():
    """Runs on a worker thread. Never touches widgets directly -- UI updates go
    through ui_queue so Tk only ever runs on the main thread."""
    last_event = None
    biome_started_at = None
    current_path = None
    handle = None
    roblox_was_running = False
    last_rotation_check = 0.0
    poll = float(cfg('Settings', 'poll_interval', '0.1') or 0.1)

    try:
        while not stop_event.is_set():
            if not is_roblox_running():
                if roblox_was_running:
                    ui_queue.put(("log", "Roblox was closed/crashed, waiting for it to start..."))
                    send_status("Roblox was closed/crashed.")
                    if handle:
                        handle.close()
                        handle = None
                    current_path = None
                    last_event = None
                    roblox_was_running = False
                set_title("No Roblox Detected")
                stop_event.wait(0.5)
                continue

            if not roblox_was_running:
                roblox_was_running = True
                ui_queue.put(("log", "Detected Roblox " + ("Player." if roblox_version == "player" else "Microsoft Store.")))

            # (re)open the log, and re-check periodically so a mid-session rotation
            # doesn't leave us tailing a dead file forever
            if handle is None or time.time() - last_rotation_check > 5:
                last_rotation_check = time.time()
                latest = get_latest_log_file() if handle is not None else wait_for_log_file()
                if latest and latest != current_path:
                    if handle:
                        ui_queue.put(("log", "Log file rotated, switching over."))
                        handle.close()
                    try:
                        # BINARY, not text. TextIOWrapper.tell() returns an opaque
                        # cookie with the decoder state packed into the high bits, not
                        # a byte offset -- on a real Roblox log it comes back as
                        # ~1.8e19, so the truncation check below saw "size < tell",
                        # rewound to the top and replayed the entire log as if it were
                        # live. That is what spammed the webhook.
                        handle = open(latest, 'rb')
                    except OSError as exc:
                        logger.error("Could not open log file %s: %s", latest, exc)
                        handle = None
                        stop_event.wait(1)
                        continue
                    current_path = latest
                    handle.seek(0, 2)  # only ever tail; history comes from the seed below
                    ui_queue.put(("log", f"Using log file: {current_path}"))
                    # Seed from the last rich-presence line so we know the biome that is
                    # running right now, instead of waiting for the next change. Replaces
                    # the old "read the whole file if it looks new" guess, which could
                    # either replay an entire session or miss the current biome entirely.
                    seeded = read_current_biome(current_path)
                    if seeded and seeded != last_event:
                        if seeded == "NORMAL":
                            last_event = seeded
                            set_title("Running")
                        elif not paused:
                            ui_queue.put(("log", f"Already in {seeded} on attach."))
                            biome_started_at = time.time()
                            announce_biome_start(seeded)
                            last_event = seeded
                        else:
                            last_event = seeded
                    else:
                        set_title("Running")
                elif handle is None:
                    ui_queue.put(("log", "No log files found."))
                    stop_event.wait(2)
                    continue

            # detect truncation (same path, file replaced under us). Valid now that
            # handle is binary and tell() is a real byte offset.
            try:
                if os.path.getsize(current_path) < handle.tell():
                    logger.info("Log file was truncated, restarting from the top.")
                    handle.seek(0)
            except OSError:
                pass

            raw = handle.readline()
            if not raw:
                stop_event.wait(poll)
                continue
            line = raw.decode('utf-8', 'ignore')

            if '"command":"SetRichPresence"' not in line:
                continue
            event = parse_hover_text(line)
            if not event or event == last_event:
                continue

            if paused:
                # Track state silently while paused. The old code discarded lines
                # outright, so resuming could miss the biome you were already in;
                # replaying the backlog instead would spam every biome you sat out.
                last_event = event
                biome_started_at = time.time() if event != "NORMAL" else None
                continue

            if event == "NORMAL":
                if last_event is not None:
                    announce_biome_end(last_event, biome_started_at)
                biome_started_at = None
            else:
                biome_started_at = time.time()
                announce_biome_start(event)
            last_event = event
    except Exception as exc:
        # A dead detector used to be completely silent -- the window still said
        # "Running" while nothing was being watched. Never again.
        logger.exception("Detection thread crashed: %s", exc)
        ui_queue.put(("log", "Detection stopped -- see crash.log"))
        set_title("STOPPED - see crash.log")
        ui_queue.put(("error", "Detection stopped unexpectedly:\n\n"
                               f"{type(exc).__name__}: {exc}\n\n"
                               "Details are in crash.log (Settings -> View Log).\n"
                               "Press Start to try again."))
        globals()['started'] = False
    finally:
        if handle:
            handle.close()


# ---------------------------------------------------------------- controls

def init():
    global started, paused, worker, session_started_at

    if started:
        if paused:
            paused = False
            root.title(APP_NAME + " - Running")
        return

    if not have_valid_webhook():
        message_box("Invalid or missing webhook link.", "Error")
        return
    # A Discord User ID is only needed to ping. Refusing to start without one meant
    # anyone using plain "Message" alerts got no detection at all -- the ID field is
    # blank in a default config, so this silently stopped the macro from ever running.
    disc = discID.get().strip()
    if disc and not disc.isnumeric():
        message_box("Discord User ID should only be a number.\n"
                    "If it is something else, such as @everyone, or your username, "
                    "that is not your Discord User ID.\n\n"
                    "Leave it empty if you don't want pings.", "Error")
        return

    set_cfg('Webhook', 'webhook_url', webhookURL.get())
    set_cfg('Webhook', 'private_server', psURL.get())
    set_cfg('Webhook', 'discord_user_id', discID.get())
    set_cfg('Macro', 'roblox_username', roblox_username.get())

    for field in (webhook_field, ps_field, discid_field, username_field):
        field.configure(state="disabled", text_color="gray")
    start_button.configure(state="disabled")

    started = True
    paused = False
    session_started_at = time.time()
    session_counts.clear()
    _recent_announce.clear()   # a stop/start inside 5s must not suppress the first biome
    stop_event.clear()
    refresh_runtime()
    threading.Thread(target=send_status, args=("Macro started!",), daemon=True).start()
    worker = threading.Thread(target=watch_loop, daemon=True)
    worker.start()
    fire_event("macro_start")
    root.title(APP_NAME + " - Running")


def pause():
    global paused
    if not started:
        return
    paused = not paused
    # through the queue like every other title change, so it cannot race the worker
    set_title("Paused" if paused else "Running")


def send_session_summary():
    """What did this session actually catch? Cheap to produce, and the thing people
    screenshot."""
    if not RT['session_summary'] or not session_counts:
        return
    lines = [f"**{count}x** {name}" for name, count in session_counts.most_common()]
    length = format_duration(time.time() - session_started_at) if session_started_at else "?"
    embed = make_embed("> ## Session Summary\n> " + "\n> ".join(lines), color="6784E0")
    embed.add_embed_field(name="Session Length", value=length)
    embed.add_embed_field(name="Biomes Seen", value=str(sum(session_counts.values())))
    send(embed)


def stop():
    # stop rescheduling Tk callbacks first; anything still pending fires after
    # destroy() and throws "invalid command name" into the log
    global _shutting_down
    _shutting_down = True
    set_cfg('Webhook', 'webhook_url', webhookURL.get())
    set_cfg('Webhook', 'private_server', psURL.get())
    set_cfg('Webhook', 'discord_user_id', discID.get())
    set_cfg('Macro', 'roblox_username', roblox_username.get())
    if started:
        stop_event.set()
        dispatch_event("macro_stop", ())

        def _farewell():
            send_session_summary()
            send_status("Macro stopped.")
            flush_webhooks(3.0)

        # Discord being slow should not freeze the window on close.
        closer = threading.Thread(target=_farewell, daemon=True)
        closer.start()
        closer.join(timeout=3)
    root.destroy()


def on_close():
    stop()


_shutting_down = False


def pump_ui():
    """Drains worker messages on the main thread."""
    if _shutting_down:
        return
    try:
        while True:
            kind, payload = ui_queue.get_nowait()
            if kind == "title":
                root.title(payload)
            elif kind == "log":
                # PyInstaller's windowed mode sets sys.stdout to None, and print()
                # would raise straight through the detection loop
                if sys.stdout is not None:
                    print(payload)
                logger.info(payload)
            elif kind == "notify":
                show_balloon(*payload)
            elif kind == "error":
                message_box(payload, "Detection Stopped")
            elif kind == "event":
                dispatch_event(*payload)
    except queue.Empty:
        pass
    if not _shutting_down:
        root.after(100, pump_ui)


def open_url(url):
    webbrowser.open(url, new=2, autoraise=True)


# ---------------------------------------------------------------- settings callbacks

def set_appearance(value):
    customtkinter.set_appearance_mode(value)
    set_cfg('Settings', 'appearance', value)


def toggle_setting(key, var):
    set_cfg('Settings', key, str(var.get()))
    refresh_runtime()


# No button in the classic window any more -- kept because plugins reach them
# through api.main.
def open_folder():
    os.startfile(DATA_DIR)


def open_crash_log():
    if os.path.exists(_LOG_PATH) and os.path.getsize(_LOG_PATH) > 0:
        os.startfile(_LOG_PATH)
    else:
        message_box("Nothing logged yet -- nothing has gone wrong.", "Nothing to show")



def send_test_webhook():
    if not have_valid_webhook():
        message_box("Invalid or missing webhook link.", "Error")
        return

    def _run():
        send(make_embed("> ## Test message\n> If you can read this, your webhook works.",
                        color="6784E0", include_ps=True))
    threading.Thread(target=_run, daemon=True).start()
    notify_desktop("Test sent", "Check your Discord channel.")


SETTING_VARS = SETTINGS_TK_VARS  # keeps reset in sync as settings get added


def reset_settings():
    for key, value in DEFAULTS['Settings'].items():
        config.set('Settings', key, value)
    save_config()
    for key, var in SETTING_VARS.items():
        default = DEFAULTS['Settings'][key]
        var.set(default if isinstance(var, customtkinter.StringVar) else int(default))
    customtkinter.set_appearance_mode(DEFAULTS['Settings']['appearance'])
    refresh_runtime()
    message_box("Settings reset to defaults.", "Done")


# ---------------------------------------------------------------- configure pings window

tlw_open = False


def manage_tlw():
    global tlw_open
    if tlw_open:
        return
    tlw_open = True
    tlw = customtkinter.CTkToplevel()
    tlw.title("Configure Pings")

    def _closed():
        global tlw_open
        tlw_open = False
        tlw.destroy()

    tlw.protocol("WM_DELETE_WINDOW", _closed)

    tlw_label = customtkinter.CTkLabel(tlw, text="Choose what you get notified for!",
                                       font=customtkinter.CTkFont(family="Segoe UI", size=20))
    tlw_label.grid(row=0, column=0, columnspan=4, pady=10, padx=10)

    def make_setter(name, info):
        def _set(new_val):
            set_cfg('Biomes', info['slug'], new_val)
            RT['actions'][name] = new_val
        return _set

    # Same two-column label/dropdown layout as before, just generated from the registry
    # so every biome gets a row -- Heaven and Singularity previously had config entries
    # with no way to change them.
    names = [n for n, i in BIOMES.items() if i['configurable']]
    half = (len(names) + 1) // 2
    for index, name in enumerate(names):
        info = BIOMES[name]
        column = 0 if index < half else 2
        row = (index if index < half else index - half) + 1
        label = customtkinter.CTkLabel(tlw, text=info['label'],
                                       font=customtkinter.CTkFont(family="Segoe UI", size=20))
        label.grid(column=column, row=row, padx=(10, 0), pady=10, sticky="w")
        menu = customtkinter.CTkOptionMenu(tlw, values=["Message", "Ping", "Nothing"],
                                           font=customtkinter.CTkFont(family="Segoe UI", size=20),
                                           variable=biome_vars[name], command=make_setter(name, info))
        menu.grid(row=row, column=column + 1, sticky="w", padx=10, pady=10)

    tlw.after(0, tlw.focus)
    tlw.after(100, lambda: tlw.resizable(False, False))
    tlw.after(250, lambda: tlw.iconbitmap(os.path.join(BUNDLE_DIR, 'icon.ico')))


# ---------------------------------------------------------------- webhook tab

tabview.set("Webhook")

webhook_label = customtkinter.CTkLabel(tabview.tab("Webhook"), text="Webhook URL:",
                                       font=customtkinter.CTkFont(family="Segoe UI", size=20))
webhook_label.grid(column=0, row=0, columnspan=2, padx=(10, 0), pady=(5, 0), sticky="w")

webhook_field = customtkinter.CTkEntry(tabview.tab("Webhook"), font=customtkinter.CTkFont(family="Segoe UI", size=20),
                                       width=335, textvariable=webhookURL)
webhook_field.grid(row=0, column=1, padx=(144, 0), pady=(10, 0), sticky="w")
if multi_webhook.get() == "1":
    webhook_field.configure(state="disabled", text_color="gray")
    webhookURL.set("Multi-Webhook On")

ps_label = customtkinter.CTkLabel(tabview.tab("Webhook"), text="Private Server URL:",
                                  font=customtkinter.CTkFont(family="Segoe UI", size=20))
ps_label.grid(column=0, row=1, padx=(10, 0), pady=(20, 0), columnspan=2, sticky="w")

ps_field = customtkinter.CTkEntry(tabview.tab("Webhook"), font=customtkinter.CTkFont(family="Segoe UI", size=20),
                                  width=300, textvariable=psURL)
ps_field.grid(row=1, column=1, padx=(179, 0), pady=(23, 0), sticky="w")

discid_label = customtkinter.CTkLabel(tabview.tab("Webhook"), text="Discord User ID:",
                                      font=customtkinter.CTkFont(family="Segoe UI", size=20))
discid_label.grid(column=0, row=2, padx=(10, 0), pady=(20, 0), columnspan=2, sticky="w")

discid_field = customtkinter.CTkEntry(tabview.tab("Webhook"), font=customtkinter.CTkFont(family="Segoe UI", size=20),
                                      width=324, textvariable=discID)
discid_field.grid(row=2, column=1, padx=(155, 0), pady=(23, 0), sticky="w")

# ---------------------------------------------------------------- macro tab

username_label = customtkinter.CTkLabel(tabview.tab("Macro"), text="Roblox Username:",
                                        font=customtkinter.CTkFont(family="Segoe UI", size=20))
username_label.grid(column=0, row=0, padx=(10, 0), pady=(5, 0), columnspan=2, sticky="w")

username_field = customtkinter.CTkEntry(tabview.tab("Macro"), font=customtkinter.CTkFont(family="Segoe UI", size=20),
                                        width=307, textvariable=roblox_username)
username_field.grid(row=0, column=1, padx=(172, 0), pady=(10, 0), sticky="w")

biome_button = customtkinter.CTkButton(tabview.tab("Macro"), text="Configure Pings",
                                       font=customtkinter.CTkFont(family="Segoe UI", size=20, weight="bold"), width=75,
                                       command=manage_tlw)
biome_button.grid(row=3, column=0, padx=(10, 0), columnspan=2, pady=(12, 0), sticky="w")

# ---------------------------------------------------------------- settings tab
#
# Everything new lives here so the other three tabs stay exactly as they were.
# A scrollable frame keeps the window at its original 505x285 no matter how many
# settings get added later -- new options scroll instead of overflowing the tab.

settings_scroll = tabview.tab("Settings")


def add_toggle(text, variable, key, row, column):
    box = customtkinter.CTkCheckBox(
        settings_scroll, text=text, font=customtkinter.CTkFont(family="Segoe UI", size=15),
        checkbox_width=20, checkbox_height=20,
        variable=variable, command=lambda: toggle_setting(key, variable))
    box.grid(row=row, column=column, padx=(10, 8), pady=(8, 0), sticky="w")
    return box


appearance_frame = customtkinter.CTkFrame(settings_scroll, fg_color="transparent")
appearance_frame.grid(row=0, column=0, columnspan=2, padx=(10, 0), pady=(6, 0), sticky="w")
appearance_label = customtkinter.CTkLabel(appearance_frame, text="Appearance:",
                                          font=customtkinter.CTkFont(family="Segoe UI", size=15))
appearance_label.grid(column=0, row=0, padx=(0, 10), sticky="w")
appearance_menu = customtkinter.CTkOptionMenu(appearance_frame, values=["Dark", "Light", "System"],
                                              font=customtkinter.CTkFont(family="Segoe UI", size=15),
                                              width=110, height=26, variable=appearance, command=set_appearance)
appearance_menu.grid(row=0, column=1, sticky="w")

# Only the settings a normal user actually changes. Everything else -- start/stop
# messages, biome duration, role pings, session summary, biome in title, history
# CSV, second-copy warning -- still works, defaults on, and lives in config.ini.
notif_toggle = add_toggle("Desktop notifications", desktop_notifications, 'desktop_notifications', 1, 0)
autostart_toggle = add_toggle("Start detecting on launch", autostart, 'autostart', 1, 1)

button_frame = customtkinter.CTkFrame(settings_scroll, fg_color="transparent")
button_frame.grid(row=3, column=0, columnspan=2, padx=(10, 0), pady=(14, 0), sticky="w")

def settings_button(text, column, row, command, **kwargs):
    button = customtkinter.CTkButton(button_frame, text=text,
                                     font=customtkinter.CTkFont(family="Segoe UI", size=13, weight="bold"),
                                     width=88, height=26, command=command, **kwargs)
    button.grid(row=row, column=column, padx=(0, 5))
    return button


test_button = settings_button("Test Webhook", 0, 0, send_test_webhook)
reset_button = settings_button("Reset", 1, 0, reset_settings,
                               fg_color="#8B2E2E", hover_color="#A33A3A")

settings_info = customtkinter.CTkLabel(settings_scroll,
                                       text=f"v{APP_VERSION}  |  {len(BIOMES)} biomes loaded",
                                       font=customtkinter.CTkFont(family="Segoe UI", size=12))
settings_info.grid(row=4, column=0, columnspan=2, padx=(10, 0), pady=(10, 0), sticky="w")

# ---------------------------------------------------------------- credits tab

max_pfp = customtkinter.CTkImage(dark_image=Image.open(os.path.join(BUNDLE_DIR, "maxstellar.png")), size=(70, 70))
max_pfp_label = customtkinter.CTkLabel(tabview.tab("Credits"), image=max_pfp, text="")
max_pfp_label.grid(row=0, column=0, padx=(10, 0), pady=(10, 0), sticky="w")

sols_sniper = customtkinter.CTkImage(dark_image=Image.open(os.path.join(BUNDLE_DIR, "sols_sniper.png")), size=(70, 70))
sols_sniper_label = customtkinter.CTkLabel(tabview.tab("Credits"), image=sols_sniper, text="")
sols_sniper_label.grid(row=1, column=0, padx=(10, 0), pady=(10, 0), sticky="w")

credits_frame = customtkinter.CTkFrame(tabview.tab("Credits"))
credits_frame.grid(row=0, column=1, padx=(7, 0), pady=(10, 0), sticky="w")

credits_frame_2 = customtkinter.CTkFrame(tabview.tab("Credits"))
credits_frame_2.grid(row=1, column=1, padx=(7, 0), pady=(10, 0), sticky="w")

max_label = customtkinter.CTkLabel(credits_frame, text="maxstellar - Creator",
                                   font=customtkinter.CTkFont(family="Segoe UI", size=15, weight="bold"))
max_label.grid(row=0, column=0, padx=(5, 0), sticky="nw")

youtube_link = customtkinter.CTkLabel(credits_frame, text="YouTube", font=("Segoe UI", 14, "underline"),
                                      text_color="dodgerblue", cursor="hand2")
youtube_link.grid(row=1, column=0, padx=(5, 0), sticky="nw")
youtube_link.bind("<Button-1>", lambda e: open_url("https://youtube.com/@maxstellar_"))

sniper_label = customtkinter.CTkLabel(credits_frame_2, text="dannw & yeswe - Developers",
                                      font=customtkinter.CTkFont(family="Segoe UI", size=15, weight="bold"))
sniper_label.grid(row=2, column=0, padx=(5, 0), pady=(5, 0), sticky="nw")

support_link = customtkinter.CTkLabel(credits_frame_2, text="Discord", font=("Segoe UI", 14, "underline"),
                                      text_color="dodgerblue", cursor="hand2")
support_link.grid(row=3, column=0, padx=(5, 0), sticky="nw")
support_link.bind("<Button-1>", lambda e: open_url("https://discord.gg/solsniper"))

# ---------------------------------------------------------------- bottom buttons

start_button = customtkinter.CTkButton(root, text="Start",
                                       font=customtkinter.CTkFont(family="Segoe UI", size=20, weight="bold"), width=75,
                                       command=init)
start_button.grid(row=1, column=0, padx=(10, 0), pady=(10, 0), sticky="w")

pause_button = customtkinter.CTkButton(root, text="Pause",
                                       font=customtkinter.CTkFont(family="Segoe UI", size=20, weight="bold"), width=75,
                                       command=pause)
pause_button.grid(row=1, column=1, padx=(5, 0), pady=(10, 0), sticky="w")

stop_button = customtkinter.CTkButton(root, text="Stop",
                                      font=customtkinter.CTkFont(family="Segoe UI", size=20, weight="bold"), width=75,
                                      command=stop)
stop_button.grid(row=1, column=2, padx=(5, 0), pady=(10, 0), sticky="w")

# ---------------------------------------------------------------- plugins

PLUGIN_DIR = os.path.join(DATA_DIR, 'plugins')
_plugin_handlers = {}   # event name -> [(plugin name, callback)]
_loaded_plugins = []
_disabled_plugins = set()

PLUGIN_README = """\
maxstellar's Biome Macro -- plugins
===================================

Drop a .py file in this folder and it loads the next time the macro starts.
Copy _template.py to get started -- files beginning with "_" are skipped, so the
template itself never runs.

A plugin may define register(api). Everything else is optional.

    def register(api):
        api.log("hello from my plugin")
        api.on("biome_start", lambda biome: api.log("started " + biome))

What api gives you
------------------
  api.name                 this plugin's filename
  api.log(msg)             write to crash.log, prefixed with the plugin name
  api.on(event, fn)        subscribe to an event (see below)
  api.send(embed, content) send through the macro's webhook layer, with retries
  api.make_embed(...)      build a Discord embed the same way the macro does
  api.add_tab(title)       add your own tab to the window, returns its frame
  api.root                 the CTk window
  api.tabview              the tab bar
  api.config               config.ini (configparser), api.save_config() to persist
  api.state                live settings dict the detection thread reads
  api.biomes               the biome registry loaded from biomes.json
  api.main                 every module-level name as a dict --
                           api.main["init"](), api.main["webhookURL"], and so on
  api.data_dir             folder next to the .exe
  api.version              macro version string

Events
------
  biome_start(biome)       a biome began
  biome_end(biome, secs)   a biome ended, with how long it lasted
  macro_start()            detection started
  macro_stop()             detection stopped

Handlers run on the UI thread, so touching widgets is safe. If a plugin raises,
it is disabled for the rest of the session and the macro keeps running -- a
broken plugin can never stop biome detection.

A word of warning
-----------------
Plugins are ordinary Python and run with full access to your machine. Only add
plugins from people you trust, the same way you would treat any .exe.
"""


def seed_plugin_folder():
    """Create plugins/ next to the exe and copy the bundled ones in on first run."""
    try:
        os.makedirs(PLUGIN_DIR, exist_ok=True)
        readme = os.path.join(PLUGIN_DIR, 'README.txt')
        if not os.path.exists(readme):
            with open(readme, 'w', encoding='utf-8') as f:
                f.write(PLUGIN_README)
        bundled = os.path.join(BUNDLE_DIR, 'plugins')
        if os.path.isdir(bundled) and os.path.abspath(bundled) != os.path.abspath(PLUGIN_DIR):
            for name in os.listdir(bundled):
                if not name.endswith('.py'):
                    continue
                target = os.path.join(PLUGIN_DIR, name)
                if not os.path.exists(target):
                    shutil.copyfile(os.path.join(bundled, name), target)
    except OSError as exc:
        logger.error("Could not prepare the plugins folder: %s", exc)


class PluginAPI:
    """Full access, as designed -- window, config, webhooks, detection state."""

    def __init__(self, name):
        self.name = name
        self.root = root
        self.tabview = tabview
        self.config = config
        self.save_config = save_config
        self.state = RT
        self.biomes = BIOMES
        self.data_dir = DATA_DIR
        self.plugin_dir = PLUGIN_DIR
        self.version = APP_VERSION
        self.app_name = APP_NAME
        self.logger = logger
        self.send = send
        self.make_embed = make_embed
        self.biome_info = biome_info
        # full access, as chosen: every module-level name, so a plugin can reach
        # init/pause/stop, the Tk variables, set_cfg, and anything else it needs
        self.main = globals()

    def log(self, message):
        logger.info("[%s] %s", self.name, message)

    def on(self, event, callback):
        _plugin_handlers.setdefault(event, []).append((self.name, callback))

    def add_tab(self, title):
        tabview.add(title)
        return tabview.tab(title)

    @property
    def started(self):
        return started

    @property
    def paused(self):
        return paused


def dispatch_event(event, args):
    """Runs on the UI thread via pump_ui, so plugins may touch widgets safely."""
    for plugin_name, callback in list(_plugin_handlers.get(event, [])):
        if plugin_name in _disabled_plugins:
            continue
        try:
            callback(*args)
        except Exception as exc:
            logger.exception("Plugin '%s' failed handling %s: %s", plugin_name, event, exc)
            _disabled_plugins.add(plugin_name)
            ui_queue.put(("log", f"Plugin '{plugin_name}' errored and was disabled."))


def fire_event(event, *args):
    """Safe to call from the detection thread; delivery happens on the UI thread."""
    if _plugin_handlers.get(event):
        ui_queue.put(("event", (event, args)))


def load_plugins():
    seed_plugin_folder()
    if not os.path.isdir(PLUGIN_DIR):
        return
    import importlib.util
    for filename in sorted(os.listdir(PLUGIN_DIR)):
        if not filename.endswith('.py') or filename.startswith('_'):
            continue
        path = os.path.join(PLUGIN_DIR, filename)
        try:
            modname = "biomeplugin_" + filename[:-3]
            spec = importlib.util.spec_from_file_location(modname, path)
            module = importlib.util.module_from_spec(spec)
            # register before executing, so the plugin behaves like a normal module:
            # relative imports, dataclasses and pickling all look it up in sys.modules
            sys.modules[modname] = module
            spec.loader.exec_module(module)
            if hasattr(module, 'register'):
                module.register(PluginAPI(filename))
            _loaded_plugins.append(filename)
            logger.info("Loaded plugin: %s", filename)
        except Exception as exc:
            # a broken plugin must never stop the macro from detecting biomes
            logger.exception("Plugin '%s' failed to load: %s", filename, exc)
            _disabled_plugins.add(filename)
    if _loaded_plugins:
        print(f"Plugins loaded: {', '.join(_loaded_plugins)}")


# multi-webhook sanity check, kept from the original (including the attitude)
if multi_webhook.get() == "1":
    if len(webhook_urls) < 2:
        message_box("there's no reason to use multi-webhook... without multiple webhooks??", "bruh are you serious")
    elif len(webhook_urls) > 49:
        message_box("you've gotta be doing this on purpose now... you don't need this many webhooks",
                    "this is ridiculous")
    elif len(webhook_urls) > 14:
        message_box("bro you do not need this many webhooks", "okay dude wtf")



load_plugins()

root.protocol("WM_DELETE_WINDOW", on_close)
root.bind("<Button-1>", lambda e: e.widget.focus_set())
root.after(100, pump_ui)
if autostart.get() == 1:
    root.after(400, init)

root.mainloop()
