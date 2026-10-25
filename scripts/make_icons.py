"""Rasterize docs/logo.svg into the home-screen icons. Needs rsvg-convert or ImageMagick."""
import shutil, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / "docs/logo.svg"
OUT = ROOT / "agent_status/web"


def render(size, path):
    if shutil.which("rsvg-convert"):
        subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size), str(SVG), "-o", str(path)], check=True)
    elif shutil.which("magick"):
        subprocess.run(["magick", "-background", "none", "-resize", f"{size}x{size}", str(SVG), str(path)], check=True)
    else:
        raise SystemExit("need rsvg-convert or ImageMagick to rasterize the logo")


if __name__ == "__main__":
    for name, size in (("icon-180.png", 180), ("icon-192.png", 192), ("icon-512.png", 512)):
        render(size, OUT / name)
        print("wrote", OUT / name)
    render(512, ROOT / "docs/logo.png")
    print("wrote", ROOT / "docs/logo.png")
