import os
import time
import json
import webbrowser
import psutil
import discord_webhook
import configparser
import customtkinter
import logging
import sys
import ctypes
import atexit # python standard library, for graceful exit
import win32api
import win32con
from PIL import Image

logging.basicConfig(
    filename='crash.log',  # Optional: Specify a file to log to
    level=logging.DEBUG,  # Set the minimum level for logging (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format='%(asctime)s - %(levelname)s - %(message)s'  # Customize the log format
)

logger = logging.getLogger('mylogger')


def my_handler(types, value, tb):
    logger.exception("Uncaught exception: {0}".format(str(value)))
    ctypes.windll.user32.MessageBoxW(0, "Check crash.log for information on this crash.", "Crashed!", 0)
    sys.exit()


# exception handler / logger
sys.excepthook = my_handler

# create UI window
customtkinter.set_default_color_theme("dark-blue")
root = customtkinter.CTk()
root.title("maxstellar's Biome Macro")
root.geometry('505x285')
root.resizable(False, False)
dirname = os.path.dirname(__file__)
root.iconbitmap(dirname + '\\icon.ico')
tabview = customtkinter.CTkTabview(root, width=505, height=230)
tabview.grid(row=0, column=0, sticky='nsew', columnspan=75)
tabview.add("Webhook")
tabview.add("Macro")
tabview.add("Credits")
tabview._segmented_button.configure(font=customtkinter.CTkFont(family="Segoe UI", size=16))
tabview._segmented_button.grid(sticky="w", padx=15)

# read configuration file
config_name = 'config.ini'
config = configparser.ConfigParser()
if not os.path.exists(config_name):
    logger.info("Config file not found, creating one...")
    print("Config file not found, creating one...")
    config['Webhook'] = {'webhook_url': "", 'private_server': "", "discord_user_id": "", 'multi_webhook': "0",
                         'multi_webhook_urls': ""}
    config['Macro'] = {'aura_detection': "1", "aura_ping": "0", "min_rarity_to_ping": "", "last_roblox_version": "", "roblox_username": "", "seen_notice": "0"}
    config['Biomes'] = {'windy': "Message", 'snowy': "Message", 'rainy': "Message", 'sand_storm': "Message",
                        'hell': "Message", "starfall": "Message",
                        "corruption": "Message", "null": "Message", "pumpkin_moon": "Message", "graveyard": "Message"}
    with open(config_name, 'w') as conffile:
        config.write(conffile)
config.read(config_name)
webhookURL = customtkinter.StringVar(root, config['Webhook']['webhook_url'])
psURL = customtkinter.StringVar(root, config['Webhook']['private_server'])
discID = customtkinter.StringVar(root, config['Webhook']['discord_user_id'])
multi_webhook = customtkinter.StringVar(root, config['Webhook']['multi_webhook'])
if multi_webhook.get() != "1" and webhookURL.get() == "Multi-Webhook On":
    webhookURL.set("")
webhook_urls_string = customtkinter.StringVar(root, config['Webhook']['multi_webhook_urls'])
webhook_urls = webhook_urls_string.get().split()
last_roblox_version = config['Macro']['last_roblox_version']
roblox_username = customtkinter.StringVar(root, config['Macro']['roblox_username'])
try:
    seen_notice = customtkinter.StringVar(root, config['Macro']['seen_notice'])
except:
    seen_notice = customtkinter.StringVar(root, "0")
    config.set('Macro', "seen_notice", "0")
    with open(config_name, 'w+') as configfile:
        config.write(configfile)
if seen_notice.get() == "0":
    seen_notice.set("1")
    config.set('Macro', "seen_notice", "1")
    with open(config_name, 'w+') as configfile:
        config.write(configfile)
    ctypes.windll.user32.MessageBoxW(0,
                                     "Thanks for continuing to use my macro!\n\nPlease check out my fishing macro, fishSol Macro. (discord.gg/fishsol)",
                                     "Notice", 0)

# variables
roblox_open = False
versions_directory = os.path.expandvars(r"%localappdata%\Roblox\Versions")
log_directory = os.path.expandvars(r"%localappdata%\Roblox\logs")
packages_path = os.path.expandvars(r"%localappdata%\Packages")
roblox_folder = None
roblox_log_path = None
roblox_version = None
biome_colors = {"NORMAL": "ffffff", "SAND STORM": "F4C27C",
                "HELL": "5C1219", "STARFALL": "6784E0", "CORRUPTION": "9042FF", "NULL": "000000", "GLITCHED": "65FF65",
                "WINDY": "91F7FF", "SNOWY": "C4F5F6", "RAINY": "4385FF", "DREAMSPACE": "ff7dff",
                "PUMPKIN MOON": "d55f09", "GRAVEYARD": "FFFFFF", "BLOOD RAIN": "ff0000", "CYBERSPACE": "2c53a7", "HEAVEN": "e8c49e", "SINGULARITY": "ffa375"}
started = False
stopped = False
paused = False
destroyed = False
debug_window = False
aura_detection = customtkinter.IntVar(root, int(config['Macro']['aura_detection']))
aura_ping = customtkinter.IntVar(root, int(config['Macro']['aura_ping']))
tlw_open = False
windy = customtkinter.StringVar(root, config['Biomes']['windy'])
snowy = customtkinter.StringVar(root, config['Biomes']['snowy'])
rainy = customtkinter.StringVar(root, config['Biomes']['rainy'])
sand_storm = customtkinter.StringVar(root, config['Biomes']['sand_storm'])
hell = customtkinter.StringVar(root, config['Biomes']['hell'])
starfall = customtkinter.StringVar(root, config['Biomes']['starfall'])
corruption = customtkinter.StringVar(root, config['Biomes']['corruption'])
null = customtkinter.StringVar(root, config['Biomes']['null'])
glitched = customtkinter.StringVar(root, "Message")
dreamspace = customtkinter.StringVar(root, "Message")
cyberspace = customtkinter.StringVar(root, "Message")
try:
    heaven = customtkinter.StringVar(root, config['Biomes']['heaven'])
    heaven = customtkinter.StringVar(root, config['Biomes']['singularity'])
except:
    config.set('Biomes', "heaven", "Message")
    config.set('Biomes', "singularity", "Message")
    with open(config_name, 'w+') as configfile:
        config.write(configfile)
blood_rain = customtkinter.StringVar(root, "Message")


def get_biome_color(biome):
    try:
        return biome_colors[biome]
    except:
        return "ff69b4"

def stop():
    global stopped
    # write config data
    config.set('Webhook', 'webhook_url', webhookURL.get())
    config.set('Webhook', 'private_server', psURL.get())
    config.set('Webhook', 'discord_user_id', discID.get())
    if detectping_field.get() == "Minimum Rarity":
        config.set('Macro', 'min_rarity_to_ping', "")
    else:
        config.set('Macro', 'min_rarity_to_ping', detectping_field.get())
    with open(config_name, 'w+') as configfile:
        config.write(configfile)

    # end webhook
    if started and not stopped:
        if multi_webhook.get() != "1":
            if "discord" in webhookURL.get() and "https://" in webhookURL.get():
                ending_webhook = discord_webhook.DiscordWebhook(url=webhookURL.get())
                ending_embed = discord_webhook.DiscordEmbed(
                    description="[" + time.strftime('%H:%M:%S') + "]: Macro stopped.")
                ending_embed.set_footer(text="maxstellar's Biome Macro | v2.3",
                                        icon_url="https://maxstellar.github.io/maxstellar.png")
                ending_webhook.add_embed(ending_embed)
                ending_webhook.execute()
        else:
            ending_embed = discord_webhook.DiscordEmbed(
                description="[" + time.strftime('%H:%M:%S') + "]: Macro stopped.")
            ending_embed.set_footer(text="maxstellar's Biome Macro | v2.3",
                                    icon_url="https://maxstellar.github.io/maxstellar.png")
            for url in webhook_urls:
                ending_webhook = discord_webhook.DiscordWebhook(url=url)
                ending_webhook.add_embed(ending_embed)
                ending_webhook.execute()
    stopped = True

    if sys.meta_path is not None:
            atexit.unregister(stop)
            sys.exit(0)

def pause():
    global paused
    paused = not paused
    if paused:
        root.title("maxstellar's Biome Macro - Paused")
    else:
        root.title("maxstellar's Biome Macro - Running")


if multi_webhook.get() == "1":
    if len(webhook_urls) < 2:
        ctypes.windll.user32.MessageBoxW(0, "there's no reason to use multi-webhook... without multiple webhooks??",
                                         "bruh are you serious", 0)
        stop()
    elif len(webhook_urls) > 14:
        if len(webhook_urls) > 49:
            ctypes.windll.user32.MessageBoxW(0,
                                             "you've gotta be doing this on purpose now... you don't need this many webhooks",
                                             "this is ridiculous", 0)
        else:
            ctypes.windll.user32.MessageBoxW(0, "bro you do not need this many webhooks", "okay dude wtf", 0)
        stop()


def x_stop():
    global destroyed
    destroyed = True
    stop()


def detect_roblox_version():
    global roblox_log_path, roblox_version, roblox_folder
    for proc in psutil.process_iter(['name']):
        if 'RobloxPlayerBeta.exe' in proc.info['name']:
            if roblox_version != 'player':
                roblox_version = 'player'
                roblox_log_path = log_directory
            return 'player'
        elif 'Windows10Universal.exe' in proc.info['name']:
            if roblox_version != 'store':
                roblox_version = 'store'
                for folder in os.listdir(packages_path):
                    if folder.startswith("ROBLOXCORPORATION.ROBLOX"):
                        roblox_folder = folder
                        roblox_log_path = os.path.join(packages_path, roblox_folder, "LocalState", "logs")
            return 'store'
    return None


def get_latest_log_file():
    if roblox_log_path:
        files = [f for f in os.listdir(roblox_log_path) if f.endswith(".log") and not "Installer" in f]
        if not files:
            return None
        latest_created_file = max(files, key=lambda f: os.path.getctime(os.path.join(roblox_log_path, f))) # find most recently created
        latest_modified_file = max(files, key=lambda f: os.path.getmtime(os.path.join(roblox_log_path, f))) # find most recently modified
        
        if latest_created_file != latest_modified_file:
                logger.info("Most recently created player log differs from most recently modified. Preferring most recently modified.")

        return os.path.join(roblox_log_path, latest_modified_file)
    return None


def is_roblox_running():
    return detect_roblox_version() is not None


def check_for_hover_text(file):
    global roblox_version, roblox_username
    last_event = None
    file.seek(0, 2)
    while True:
        if not stopped:
            root.update()
        else:
            if not destroyed:
                root.destroy()
            sys.exit()
        check = is_roblox_running()
        if check:
            line = file.readline()
            if line and not paused:
                if '"command":"SetRichPresence"' in line:
                    try:
                        json_data_start = line.find('{"command":"SetRichPresence"')
                        if json_data_start != -1:
                            json_data = json.loads(line[json_data_start:])
                            event = json_data.get("data", {}).get("largeImage", {}).get("hoverText", "")
                            if event and event != last_event:
                                if multi_webhook.get() != "1":
                                    if "discord" not in webhookURL.get() or "https://" not in webhookURL.get():
                                        ctypes.windll.user32.MessageBoxW(0, "Invalid or missing webhook link.", "Error",
                                                                         0)
                                        stop()
                                        return
                                    webhook = discord_webhook.DiscordWebhook(url=webhookURL.get())
                                    if event == "NORMAL":
                                        if last_event is not None:
                                            print(time.strftime('%H:%M:%S') + f": Biome Ended - " + last_event)
                                            try:
                                                if globals()[last_event.replace(" ", "_").lower()].get() != "Nothing":
                                                    embed = discord_webhook.DiscordEmbed(
                                                        title="[" + time.strftime('%H:%M:%S') + "]",
                                                        color=get_biome_color(last_event),
                                                        description="> ## Biome Ended - " + last_event)
                                                    embed.set_footer(text="maxstellar's Biome Macro | v2.3",
                                                                     icon_url="https://maxstellar.github.io/maxstellar.png")
                                                    embed.set_thumbnail(
                                                        url="https://maxstellar.github.io/biome_thumb/" + last_event.replace(
                                                            " ", "_") + ".png")
                                                    webhook.add_embed(embed)
                                                    webhook.execute()
                                            except:
                                                pass
                                        else:
                                            pass
                                    else:
                                        print(time.strftime('%H:%M:%S') + f": Biome Started - {event}")
                                        try:
                                            if globals()[event.replace(" ", "_").lower()].get() != "Nothing":
                                                embed = discord_webhook.DiscordEmbed(
                                                    title="[" + time.strftime('%H:%M:%S') + "]",
                                                    color=get_biome_color(event),
                                                    description="> ## Biome Started - " + event)
                                                embed.set_footer(text="maxstellar's Biome Macro | v2.3",
                                                                 icon_url="https://maxstellar.github.io/maxstellar.png")
                                                embed.add_embed_field(name="Private Server Link", value=psURL.get())
                                                embed.set_thumbnail(
                                                    url="https://maxstellar.github.io/biome_thumb/" + event.replace(" ", "_") + ".png")
                                                webhook.add_embed(embed)
                                            if globals()[event.replace(" ", "_").lower()].get() == "Ping":
                                                webhook.set_content(f"<@{discID.get()}>")
                                            if event == "GLITCHED" or event == "DREAMSPACE" or event == "CYBERSPACE":
                                                webhook.set_content("@everyone")
                                            webhook.execute()
                                        except:
                                            pass
                                else:
                                    if event == "NORMAL":
                                        if last_event is not None:
                                            print(time.strftime('%H:%M:%S') + f": Biome Ended - " + last_event)
                                            try:
                                                if globals()[last_event.replace(" ", "_").lower()].get() != "Nothing":
                                                    for url in webhook_urls:
                                                        webhook = discord_webhook.DiscordWebhook(url=url)
                                                        embed = discord_webhook.DiscordEmbed(
                                                            title="[" + time.strftime('%H:%M:%S') + "]",
                                                            color=get_biome_color(last_event),
                                                            description="> ## Biome Ended - " + last_event)
                                                        embed.set_footer(text="maxstellar's Biome Macro | v2.3",
                                                                         icon_url="https://maxstellar.github.io/maxstellar.png")
                                                        embed.set_thumbnail(
                                                            url="https://maxstellar.github.io/biome_thumb/" + last_event.replace(
                                                                " ", "_") + ".png")
                                                        webhook.add_embed(embed)
                                                        webhook.execute()
                                            except:
                                                pass
                                        else:
                                            pass
                                    else:
                                        print(time.strftime('%H:%M:%S') + f": Biome Started - {event}")
                                        try:
                                            if globals()[event.replace(" ", "_").lower()].get() != "Nothing":
                                                for url in webhook_urls:
                                                    embed = discord_webhook.DiscordEmbed(
                                                        title="[" + time.strftime('%H:%M:%S') + "]",
                                                        color=get_biome_color(event),
                                                        description="> ## Biome Started - " + event)
                                                    embed.set_footer(text="maxstellar's Biome Macro | v2.3",
                                                                     icon_url="https://maxstellar.github.io/maxstellar.png")
                                                    embed.add_embed_field(name="Private Server Link", value=psURL.get())
                                                    embed.set_thumbnail(
                                                        url="https://maxstellar.github.io/biome_thumb/" + event.replace(" ", "_") + ".png")
                                                    webhook = discord_webhook.DiscordWebhook(url=url)
                                                    webhook.add_embed(embed)
                                                    if globals()[event.replace(" ", "_").lower()].get() == "Ping":
                                                        webhook.set_content(f"<@{discID.get()}>")
                                                    if event == "GLITCHED" or event == "DREAMSPACE" or event == "CYBERSPACE":
                                                        webhook.set_content("@everyone")
                                                    webhook.execute()
                                        except:
                                            pass
                                last_event = event
                    except json.JSONDecodeError:
                        print("Error decoding JSON")
            else:
                time.sleep(0.1)
        else:
            print("Roblox is closed, waiting for Roblox to start...")
            if multi_webhook.get() != "1":
                if "discord" not in webhookURL.get() or "https://" not in webhookURL.get():
                    ctypes.windll.user32.MessageBoxW(0, "Invalid or missing webhook link.", "Error", 0)
                    stop()
                    return
                close_webhook = discord_webhook.DiscordWebhook(url=webhookURL.get())
                close_embed = discord_webhook.DiscordEmbed(
                    description="[" + time.strftime('%H:%M:%S') + "]: Roblox was closed/crashed.")
                close_embed.set_footer(text="maxstellar's Biome Macro | v2.3",
                                       icon_url="https://maxstellar.github.io/maxstellar.png")
                close_webhook.add_embed(close_embed)
                close_webhook.execute()
            else:
                for url in webhook_urls:
                    close_webhook = discord_webhook.DiscordWebhook(url=url)
                    close_embed = discord_webhook.DiscordEmbed(
                        description="[" + time.strftime('%H:%M:%S') + "]: Roblox was closed/crashed.")
                    close_embed.set_footer(text="maxstellar's Biome Macro | v2.3",
                                           icon_url="https://maxstellar.github.io/maxstellar.png")
                    close_webhook.add_embed(close_embed)
                    close_webhook.execute()
            root.title("maxstellar's Biome Macro - No Roblox Detected")
            while True:
                if not stopped:
                    root.update()
                else:
                    if not destroyed:
                        root.destroy()
                    sys.exit()
                check = is_roblox_running()
                if check:
                    break
                time.sleep(0.1)
            if roblox_version == "player":
                logger.info("Detected Roblox Player.")
                print("Detected Roblox Player.")
                time.sleep(5)
            else:
                logger.info("Detected Roblox Microsoft Store.")
                print("Detected Roblox Microsoft Store.")
                time.sleep(5)
            latest_log = get_latest_log_file()
            if not latest_log:
                logger.info("No log files found.")
                print("No log files found.")
                return
            with open(latest_log, 'r', encoding='utf-8', errors='ignore') as file:
                print(f"Using log file: {latest_log}")
                print()
                logger.info(f"Using log file: {latest_log}")
                root.title("maxstellar's Biome Macro - Running")
                check_for_hover_text(file)


def open_url(url):
    webbrowser.open(url, new=2, autoraise=True)


def auradetection_toggle_update():
    config.set('Macro', 'aura_detection', str(aura_detection.get()))
    with open(config_name, 'w+') as configfile:
        config.write(configfile)


def auraping_toggle_update():
    config.set('Macro', 'aura_ping', str(aura_ping.get()))
    with open(config_name, 'w+') as configfile:
        config.write(configfile)


def set_windy(new_val):
    config.set('Biomes', "windy", new_val)
    with open(config_name, 'w+') as configfile:
        config.write(configfile)


def set_snowy(new_val):
    config.set('Biomes', "snowy", new_val)
    with open(config_name, 'w+') as configfile:
        config.write(configfile)


def set_rainy(new_val):
    config.set('Biomes', "rainy", new_val)
    with open(config_name, 'w+') as configfile:
        config.write(configfile)


def set_sand_storm(new_val):
    config.set('Biomes', "sand_storm", new_val)
    with open(config_name, 'w+') as configfile:
        config.write(configfile)


def set_hell(new_val):
    config.set('Biomes', "hell", new_val)
    with open(config_name, 'w+') as configfile:
        config.write(configfile)


def set_starfall(new_val):
    config.set('Biomes', "starfall", new_val)
    with open(config_name, 'w+') as configfile:
        config.write(configfile)


def set_corruption(new_val):
    config.set('Biomes', "corruption", new_val)
    with open(config_name, 'w+') as configfile:
        config.write(configfile)


def set_null(new_val):
    config.set('Biomes', "null", new_val)
    with open(config_name, 'w+') as configfile:
        config.write(configfile)


def set_pumpkin_moon(new_val):
    config.set('Biomes', "pumpkin_moon", new_val)
    with open(config_name, 'w+') as configfile:
        config.write(configfile)


def set_graveyard(new_val):
    config.set('Biomes', "graveyard", new_val)
    with open(config_name, 'w+') as configfile:
        config.write(configfile)


def manage_tlw():
    global tlw_open, dirname
    if not tlw_open:
        # create tlw
        tlw_open = True
        tlw = customtkinter.CTkToplevel()
        tlw.bind("<Destroy>", lambda e: globals().__setitem__('tlw_open', False))
        tlw.title("Configure Pings")
        tlw_label = customtkinter.CTkLabel(tlw, text="Choose what you get notified for!",
                                           font=customtkinter.CTkFont(family="Segoe UI", size=20))
        tlw_label.grid(row=0, column=0, columnspan=2, pady=10, padx=10)
        windy_toggle = customtkinter.CTkOptionMenu(tlw, values=["Message", "Ping", "Nothing"],
                                                   font=customtkinter.CTkFont(family="Segoe UI", size=20),
                                                   variable=windy,
                                                   command=set_windy)
        windy_toggle.grid(row=1, column=1, sticky="w", padx=10, pady=10)
        snowy_toggle = customtkinter.CTkOptionMenu(tlw, values=["Message", "Ping", "Nothing"],
                                                   font=customtkinter.CTkFont(family="Segoe UI", size=20),
                                                   variable=snowy,
                                                   command=set_snowy)
        snowy_toggle.grid(row=2, column=1, sticky="w", padx=10, pady=10)
        rainy_toggle = customtkinter.CTkOptionMenu(tlw, values=["Message", "Ping", "Nothing"],
                                                   font=customtkinter.CTkFont(family="Segoe UI", size=20),
                                                   variable=rainy,
                                                   command=set_rainy)
        rainy_toggle.grid(row=3, column=1, sticky="w", padx=10, pady=10)
        sand_storm_toggle = customtkinter.CTkOptionMenu(tlw, values=["Message", "Ping", "Nothing"],
                                                        font=customtkinter.CTkFont(family="Segoe UI", size=20),
                                                        variable=sand_storm,
                                                        command=set_sand_storm)
        sand_storm_toggle.grid(row=4, column=1, sticky="w", padx=10, pady=10)
        hell_toggle = customtkinter.CTkOptionMenu(tlw, values=["Message", "Ping", "Nothing"],
                                                  font=customtkinter.CTkFont(family="Segoe UI", size=20), variable=hell,
                                                  command=set_hell)
        hell_toggle.grid(row=1, column=3, sticky="w", padx=10, pady=10)
        starfall_toggle = customtkinter.CTkOptionMenu(tlw, values=["Message", "Ping", "Nothing"],
                                                      font=customtkinter.CTkFont(family="Segoe UI", size=20),
                                                      variable=starfall, command=set_starfall)
        starfall_toggle.grid(row=2, column=3, sticky="w", padx=10, pady=10)
        corruption_toggle = customtkinter.CTkOptionMenu(tlw, values=["Message", "Ping", "Nothing"],
                                                        font=customtkinter.CTkFont(family="Segoe UI", size=20),
                                                        variable=corruption, command=set_corruption)
        corruption_toggle.grid(row=3, column=3, sticky="w", padx=10, pady=10)
        null_toggle = customtkinter.CTkOptionMenu(tlw, values=["Message", "Ping", "Nothing"],
                                                  font=customtkinter.CTkFont(family="Segoe UI", size=20), variable=null,
                                                  command=set_null)
        null_toggle.grid(row=4, column=3, sticky="w", padx=10, pady=10)
        windy_label = customtkinter.CTkLabel(tlw, text="Windy",
                                             font=customtkinter.CTkFont(family="Segoe UI", size=20))
        windy_label.grid(column=0, row=1, padx=(10, 0), pady=10, sticky="w")
        snowy_label = customtkinter.CTkLabel(tlw, text="Snowy",
                                             font=customtkinter.CTkFont(family="Segoe UI", size=20))
        snowy_label.grid(column=0, row=2, padx=(10, 0), pady=10, sticky="w")
        rainy_label = customtkinter.CTkLabel(tlw, text="Rainy",
                                             font=customtkinter.CTkFont(family="Segoe UI", size=20))
        rainy_label.grid(column=0, row=3, padx=(10, 0), pady=10, sticky="w")
        sand_storm_label = customtkinter.CTkLabel(tlw, text="Sand Storm",
                                                  font=customtkinter.CTkFont(family="Segoe UI", size=20))
        sand_storm_label.grid(column=0, row=4, padx=(10, 0), pady=10, sticky="w")
        hell_label = customtkinter.CTkLabel(tlw, text="Hell",
                                            font=customtkinter.CTkFont(family="Segoe UI", size=20))
        hell_label.grid(column=2, row=1, padx=(10, 0), pady=10, sticky="w")
        starfall_label = customtkinter.CTkLabel(tlw, text="Starfall",
                                                font=customtkinter.CTkFont(family="Segoe UI", size=20))
        starfall_label.grid(column=2, row=2, padx=(10, 0), pady=10, sticky="w")
        corruption_label = customtkinter.CTkLabel(tlw, text="Corruption",
                                                  font=customtkinter.CTkFont(family="Segoe UI", size=20))
        corruption_label.grid(column=2, row=3, padx=(10, 0), pady=10, sticky="w")
        null_label = customtkinter.CTkLabel(tlw, text="Null",
                                            font=customtkinter.CTkFont(family="Segoe UI", size=20))
        null_label.grid(column=2, row=4, padx=(10, 0), pady=10, sticky="w")
        tlw.after(0, tlw.focus)
        tlw.after(100, lambda: tlw.resizable(False, False))
        tlw.after(250, lambda: tlw.iconbitmap(dirname + '\\icon.ico'))


def init():
    global roblox_open, started, paused, roblox_username

    if roblox_username.get().strip() == "":
        if aura_detection.get() == 1:
            aura_detection.set(0)
            auradetection_toggle_update()
            ctypes.windll.user32.MessageBoxW(0,
                                             "The Roblox username field was left empty, so aura detection is being disabled automatically. To re-enable the feature, please fill in your Roblox username.", "Warning", 0)

    if paused:
        paused = False
        root.title("maxstellar's Biome Macro - Running")

    if started:
        return

    webhook_field.configure(state="disabled", text_color="gray")
    ps_field.configure(state="disabled", text_color="gray")
    discid_field.configure(state="disabled", text_color="gray")
    username_field.configure(state="disabled", text_color="gray")
    if "," in detectping_field.get():
        new_dp_val = detectping_field.get().replace(",", "")
        detectping_field.delete(0, len(detectping_field.get()) + 1)
        detectping_field.insert(0, new_dp_val)
    if not detectping_field.get().isnumeric():
        detectping_field.delete(0, len(detectping_field.get()) + 1)
    detectping_field.configure(state="disabled", text_color="gray")
    # write new settings to config
    config.set('Webhook', 'webhook_url', webhookURL.get())
    config.set('Webhook', 'private_server', psURL.get())
    config.set('Webhook', 'discord_user_id', discID.get())
    if detectping_field.get() == "Minimum Rarity":
        config.set('Macro', 'min_rarity_to_ping', "")
    else:
        config.set('Macro', 'min_rarity_to_ping', detectping_field.get())

    # Writing configuration file to 'config.ini'
    with open(config_name, 'w+') as configfile:
        config.write(configfile)

    # start webhook
    starting_embed = discord_webhook.DiscordEmbed(
        description="[" + time.strftime('%H:%M:%S') + "]: Macro started!")
    starting_embed.set_footer(text="maxstellar's Biome Macro | v2.3",
                              icon_url="https://maxstellar.github.io/maxstellar.png")
    if multi_webhook.get() != "1":
        if "discord" not in webhookURL.get() or "https://" not in webhookURL.get():
            ctypes.windll.user32.MessageBoxW(0, "Invalid or missing webhook link.", "Error", 0)
            stop()
            return
        starting_webhook = discord_webhook.DiscordWebhook(url=webhookURL.get())
        starting_webhook.add_embed(starting_embed)
        starting_webhook.execute()
    else:
        for url in webhook_urls:
            starting_webhook = discord_webhook.DiscordWebhook(url=url)
            starting_webhook.add_embed(starting_embed)
            starting_webhook.execute()

    if not discID.get().isnumeric():
        ctypes.windll.user32.MessageBoxW(0,
                                         "Discord User ID should only be a number.\nIf it is something else, such as @everyone, or your username, that is not your Discord User ID.",
                                         "Error", 0)
        stop()
        return

    started = True

    # start detection
    if is_roblox_running():
        roblox_open = True
        logger.info("Roblox is open.")
        print("Roblox is open.")
        root.title("maxstellar's Biome Macro - Running")
    else:
        logger.info("Roblox is closed, waiting for Roblox to start...")
        print("Roblox is closed, waiting for Roblox to start...")
        root.title("maxstellar's Biome Macro - No Roblox Detected")
        while True:
            if not stopped:
                root.update()
            else:
                if not destroyed:
                    root.destroy()
                sys.exit()
            check = is_roblox_running()
            if check:
                break
            time.sleep(0.1)
    if not roblox_open:
        if roblox_version == "player":
            logger.info("Detected Roblox Player.")
            print("Detected Roblox Player.")
            time.sleep(1.5)
        else:
            logger.info("Detected Roblox Microsoft Store.")
            print("Detected Roblox Microsoft Store.")
            time.sleep(3.5)
    latest_log = get_latest_log_file()
    if not latest_log:
        logger.info(print("No log files found."))
        print("No log files found.")
        return
    with open(latest_log, 'r', encoding='utf-8') as file:
        print(f"Using log file: {latest_log}")
        print()
        logger.info(f"Using log file: {latest_log}")
        root.title("maxstellar's Biome Macro - Running")
        check_for_hover_text(file)

# Console control handler (should catch logoff/shutdown events I think)
def console_ctrl_handler(ctrl_type):
        if ctrl_type in (win32con.CTRL_LOGOFF_EVENT, win32con.CTRL_SHUTDOWN_EVENT, win32con.CTRL_CLOSE_EVENT, win32con.CTRL_C_EVENT, win32con.CTRL_BREAK_EVENT):
                stop()
        return True

# Main

win32api.SetConsoleCtrlHandler(console_ctrl_handler, True) # Attach graceful shutdown handler to win32api

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

biome_button = customtkinter.CTkButton(tabview.tab("Macro"), text="Configure Pings",
                                       font=customtkinter.CTkFont(family="Segoe UI", size=20, weight="bold"), width=75,
                                       command=manage_tlw)
biome_button.grid(row=3, column=0, padx=(10, 0), columnspan=2, pady=(12, 0), sticky="w")

# patch_button = customtkinter.CTkButton(tabview.tab("Macro"), text="Patch Roblox",
#                                       font=customtkinter.CTkFont(family="Segoe UI", size=20, weight="bold"), width=75,
#                                       command=patch_roblox)
# patch_button.grid(row=3, column=1, padx=(10, 0), columnspan=2, pady=(12, 0), sticky="w")

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

max_pfp = customtkinter.CTkImage(dark_image=Image.open(dirname + "\\maxstellar.png"), size=(70, 70))
max_pfp_label = customtkinter.CTkLabel(tabview.tab("Credits"), image=max_pfp, text="")
max_pfp_label.grid(row=0, column=0, padx=(10, 0), pady=(10, 0), sticky="w")

sols_sniper = customtkinter.CTkImage(dark_image=Image.open(dirname + "\\sols_sniper.png"), size=(70, 70))
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

discid_label = customtkinter.CTkLabel(tabview.tab("Macro"), text="Roblox Username:",
                                      font=customtkinter.CTkFont(family="Segoe UI", size=20))
discid_label.grid(column=0, row=0, padx=(10, 0), pady=(5, 0), columnspan=2, sticky="w")

username_field = customtkinter.CTkEntry(tabview.tab("Macro"), font=customtkinter.CTkFont(family="Segoe UI", size=20),
                                      width=307, textvariable=roblox_username)
username_field.grid(row=0, column=1, padx=(172, 0), pady=(10, 0), sticky="w")

detection_toggle = customtkinter.CTkCheckBox(tabview.tab("Macro"), text="Aura Detection [Not Working]",
                                             font=customtkinter.CTkFont(family="Segoe UI", size=20),
                                             variable=aura_detection, command=auradetection_toggle_update)
detection_toggle.grid(row=1, column=0, columnspan=2, padx=(10, 0), pady=(10, 0), sticky="w")

detectping_toggle = customtkinter.CTkCheckBox(tabview.tab("Macro"), text="Aura Pings",
                                              font=customtkinter.CTkFont(family="Segoe UI", size=20),
                                              variable=aura_ping, command=auraping_toggle_update)
detectping_toggle.grid(row=2, column=0, columnspan=2, padx=(10, 0), pady=(12, 0), sticky="w")
detectping_field = customtkinter.CTkEntry(tabview.tab("Macro"), font=customtkinter.CTkFont(family="Segoe UI", size=20),
                                          width=155, textvariable=None, placeholder_text="Minimum Rarity")
detectping_field.grid(row=2, column=1, padx=(140, 0), pady=(10, 0), sticky="w")

min_rarity_to_ping = config['Macro']['min_rarity_to_ping']
if min_rarity_to_ping != "":
    detectping_field.insert(0, min_rarity_to_ping)

atexit.register(stop)

root.bind("<Destroy>", lambda event: x_stop())
root.bind("<Button-1>", lambda e: e.widget.focus_set())

root.mainloop()
