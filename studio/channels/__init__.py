"""Channel themes: voice, fonts, colours, backgrounds and characters for each channel."""
import importlib

CHANNELS = {
    "what-if-institute": "whatif",
    "stoic-ember": "stoic",
    "mind-mites": "mites",
}


def get_theme(channel):
    if channel not in CHANNELS:
        raise KeyError(f"Unknown channel '{channel}'. Known: {', '.join(CHANNELS)}")
    return importlib.import_module(f".{CHANNELS[channel]}", __name__).Theme()
