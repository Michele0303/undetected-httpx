from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("undetected-httpx")
except PackageNotFoundError:
    __version__ = "0.0.0"  # fallback for uninstalled package
