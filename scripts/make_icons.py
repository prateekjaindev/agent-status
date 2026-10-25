"""Draw the home-screen icons (PNG) with the standard library only: python3 scripts/make_icons.py"""
import struct, zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "agent_status/web"
BG_TOP, BG_BOTTOM = (22, 28, 38), (8, 10, 14)
DOTS = [((0.30, 0.50), (255, 181, 71)), ((0.50, 0.50), (94, 161, 255)), ((0.70, 0.50), (61, 220, 151))]


def png(path, size, pixels):
    raw = b"".join(b"\0" + bytes(c for px in row for c in px) for row in pixels)
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def draw(size, ss=3):
    """Full-bleed background (platforms apply their own mask) with three glowing status dots."""
    rows = []
    r = 0.075  # dot radius as a fraction of the icon
    for y in range(size):
        row = []
        for x in range(size):
            acc = [0, 0, 0]
            for sy in range(ss):
                for sx in range(ss):
                    u, v = (x + (sx + 0.5) / ss) / size, (y + (sy + 0.5) / ss) / size
                    c = [BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * v for i in range(3)]
                    for (cx, cy), col in DOTS:
                        d = ((u - cx) ** 2 + (v - cy) ** 2) ** 0.5
                        if d < r:
                            c = list(col)
                        elif d < r * 2.6:  # soft glow
                            k = (1 - (d - r) / (r * 1.6)) ** 2 * 0.35
                            c = [c[i] + (col[i] - c[i]) * k for i in range(3)]
                    acc = [acc[i] + c[i] for i in range(3)]
            row.append(tuple(int(a / ss / ss) for a in acc))
        rows.append(row)
    return rows


if __name__ == "__main__":
    for name, size in (("icon-180.png", 180), ("icon-192.png", 192), ("icon-512.png", 512)):
        png(OUT / name, size, draw(size, ss=3 if size < 512 else 2))
        print("wrote", OUT / name)
