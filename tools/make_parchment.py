#!/usr/bin/env python3
"""Generate the tileable parchment texture (src/w3qt/data/parchment.jpg).

Procedural value noise in several octaves plus fine grain and a few fibres;
deterministic (fixed seed), no external artwork.
"""
import random
import sys
from pathlib import Path

from PySide6.QtGui import QColor, QGuiApplication, QImage

SIZE = 512
OUT = Path(__file__).resolve().parent.parent / "src" / "w3qt" / "data" / "parchment.jpg"


def value_noise(size: int, cells: int, rng: random.Random) -> list[list[float]]:
    grid = [[rng.random() for _ in range(cells)] for _ in range(cells)]
    step = size / cells
    out = []
    for y in range(size):
        gy = y / step
        y0 = int(gy) % cells
        y1 = (y0 + 1) % cells
        ty = gy - int(gy)
        ty = ty * ty * (3 - 2 * ty)
        row = []
        for x in range(size):
            gx = x / step
            x0 = int(gx) % cells
            x1 = (x0 + 1) % cells
            tx = gx - int(gx)
            tx = tx * tx * (3 - 2 * tx)
            a = grid[y0][x0] + (grid[y0][x1] - grid[y0][x0]) * tx
            b = grid[y1][x0] + (grid[y1][x1] - grid[y1][x0]) * tx
            row.append(a + (b - a) * ty)
        out.append(row)
    return out


def main() -> int:
    QGuiApplication(sys.argv[:1])
    rng = random.Random(1271)  # fixed seed: reproducible texture
    octaves = [(4, 0.45), (8, 0.25), (16, 0.15), (64, 0.15)]
    layers = [(value_noise(SIZE, c, rng), w) for c, w in octaves]
    base = (232, 216, 178)      # warm parchment
    dark = (196, 168, 118)      # stains
    img = QImage(SIZE, SIZE, QImage.Format_RGB32)
    for y in range(SIZE):
        for x in range(SIZE):
            n = sum(layer[y][x] * w for layer, w in layers)
            n = max(0.0, min(1.0, (n - 0.25) * 1.6))
            grain = rng.uniform(-6, 6)
            c = [base[i] + (dark[i] - base[i]) * n * 0.55 + grain for i in range(3)]
            img.setPixelColor(x, y, QColor(*[max(0, min(255, int(v))) for v in c]))
    # faint fibres
    for _ in range(60):
        x, y = rng.randrange(SIZE), rng.randrange(SIZE)
        length = rng.randrange(8, 40)
        dx, dy = rng.choice([(1, 0), (1, 1), (0, 1), (1, -1)])
        for i in range(length):
            px, py = (x + dx * i) % SIZE, (y + dy * i) % SIZE
            col = img.pixelColor(px, py)
            img.setPixelColor(px, py, col.darker(104 + rng.randrange(4)))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(OUT), "JPG", 88)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
