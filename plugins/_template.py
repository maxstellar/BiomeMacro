"""Plugin template for maxstellar's Biome Macro.

Copy this file, rename it to something without a leading underscore
(files starting with "_" are skipped, which is why this one never runs),
and restart the macro.

Everything below is optional -- delete what you don't need.
"""


def register(api):
    """Called once at startup. `api` is your handle on the whole macro."""

    api.log("hello from the template plugin")

    # ---------------------------------------------------------------- events
    # Handlers run on the UI thread, so touching widgets here is safe.

    def on_biome_start(biome):
        info = api.biome_info(biome)          # colour, label, thumbnail, settings
        api.log(f"{info['label']} started")

        # Send your own Discord message through the macro's webhook layer.
        # It queues, retries, and respects rate limits for you.
        # api.send(api.make_embed(f"> ## {biome} is live", color=info["color"]))

    def on_biome_end(biome, seconds):
        api.log(f"{biome} lasted {seconds}s")

    def on_macro_start():
        api.log("detection started")

    def on_macro_stop():
        api.log("detection stopped")

    api.on("biome_start", on_biome_start)
    api.on("biome_end", on_biome_end)
    api.on("macro_start", on_macro_start)
    api.on("macro_stop", on_macro_stop)

    # ---------------------------------------------------------------- your own tab
    # Uncomment to add a tab to the main window. It's a normal CustomTkinter frame.
    #
    # import customtkinter
    # tab = api.add_tab("My Plugin")
    # customtkinter.CTkLabel(tab, text="Hello",
    #                        font=customtkinter.CTkFont(family="Segoe UI", size=20)
    #                        ).grid(row=0, column=0, padx=10, pady=10)

    # ---------------------------------------------------------------- settings
    # config.ini is yours too. Use your own section so you don't collide.
    #
    # if not api.config.has_section("MyPlugin"):
    #     api.config.add_section("MyPlugin")
    #     api.config.set("MyPlugin", "greeting", "hi")
    #     api.save_config()
    # greeting = api.config.get("MyPlugin", "greeting", fallback="hi")

    # ---------------------------------------------------------------- everything else
    # api.main is the macro's module namespace -- every function and variable.
    #   api.main["init"]()            start detection
    #   api.main["stop"]()            stop and close
    #   api.main["webhookURL"].get()  the webhook field
    #   api.state                     live settings the detection thread reads
    #   api.biomes                    the registry from biomes.json
    #   api.data_dir                  folder next to the .exe

    # If this function raises, the plugin is disabled for the session and the
    # error goes to crash.log. Detection keeps running either way.
