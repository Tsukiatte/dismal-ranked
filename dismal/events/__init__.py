"""Gateway event listeners, loaded as cogs at startup."""

# Modules listed here are loaded by main.py via load_extension().
EXTENSIONS = [
    "dismal.events.queue",
    "dismal.events.reactions",
]
