"""Cutest picture: a chubby baby panda hugging a bamboo stalk.

Drawn procedurally with the standard library only. The picture is
rendered at 2x resolution and downsampled for smooth edges, then
encoded as a PNG by hand (zlib + struct, no imaging libraries).
"""
import math
import os
import struct
import zlib

W, H = 800, 800
SS = 2
IW, IH = W * SS, H * SS


def _chunk(kind, data):
    out = struct.pack(">I", len(data)) + kind + data
    out += struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return out


def encode_png(rgb, w, h):
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += rgb[y * w * 3:(y + 1) * w * 3]
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + _chunk(b"IEND", b""))


class Canvas:
    """An RGB buffer at 2x resolution with simple vector shapes."""

    def __init__(self):
        self.px = bytearray(IW * IH * 3)

    def _put(self, x, y, color):
        i = (y * IW + x) * 3
        self.px[i] = color[0]
        self.px[i + 1] = color[1]
        self.px[i + 2] = color[2]

    def _mix(self, x, y, color, alpha):
        i = (y * IW + x) * 3
        a = alpha
        self.px[i] = int(color[0] * a + self.px[i] * (1 - a))
        self.px[i + 1] = int(color[1] * a + self.px[i + 1] * (1 - a))
        self.px[i + 2] = int(color[2] * a + self.px[i + 2] * (1 - a))

    def vgrad(self, top, bottom):
        for y in range(IH):
            t = y / (IH - 1)
            r = int(top[0] + (bottom[0] - top[0]) * t)
            g = int(top[1] + (bottom[1] - top[1]) * t)
            b = int(top[2] + (bottom[2] - top[2]) * t)
            self.px[y * IW * 3:(y + 1) * IW * 3] = bytes((r, g, b)) * IW

    def ellipse(self, cx, cy, rx, ry, color, alpha=1.0, angle=0.0):
        cx *= SS
        cy *= SS
        rx *= SS
        ry *= SS
        x0 = max(0, int(cx - rx - 1))
        x1 = min(IW, int(cx + rx + 2))
        y0 = max(0, int(cy - ry - 1))
        y1 = min(IH, int(cy + ry + 2))
        if alpha >= 1.0 and angle == 0.0:
            for y in range(y0, y1):
                dy = (y - cy) / ry
                if dy < -1.0 or dy > 1.0:
                    continue
                hw = rx * math.sqrt(1.0 - dy * dy)
                a = max(x0, int(cx - hw))
                b = min(x1, int(cx + hw) + 1)
                if b > a:
                    base = y * IW * 3
                    self.px[base + a * 3:base + b * 3] = bytes(color) * (b - a)
            return
        ca = math.cos(-angle)
        sa = math.sin(-angle)
        for y in range(y0, y1):
            for x in range(x0, x1):
                dx = (x - cx) * ca - (y - cy) * sa
                dy = (x - cx) * sa + (y - cy) * ca
                if (dx / rx) ** 2 + (dy / ry) ** 2 <= 1.0:
                    if alpha >= 1.0:
                        self._put(x, y, color)
                    else:
                        self._mix(x, y, color, alpha)

    def circle(self, cx, cy, r, color, alpha=1.0):
        self.ellipse(cx, cy, r, r, color, alpha)

    def poly(self, points, color, alpha=1.0):
        pts = [(x * SS, y * SS) for x, y in points]
        ys = [p[1] for p in pts]
        y0 = max(0, int(min(ys)))
        y1 = min(IH, int(max(ys)) + 1)
        n = len(pts)
        for y in range(y0, y1):
            xs = []
            for i in range(n):
                x1, y1p = pts[i]
                x2, y2p = pts[(i + 1) % n]
                if (y1p <= y < y2p) or (y2p <= y < y1p):
                    t = (y - y1p) / (y2p - y1p)
                    xs.append(x1 + t * (x2 - x1))
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                a = max(0, int(xs[k]))
                b = min(IW, int(xs[k + 1]) + 1)
                if b <= a:
                    continue
                if alpha >= 1.0:
                    base = y * IW * 3
                    self.px[base + a * 3:base + b * 3] = bytes(color) * (b - a)
                else:
                    for x in range(a, b):
                        self._mix(x, y, color, alpha)

    def thick_line(self, x0, y0, x1, y1, w, color):
        dx = x1 - x0
        dy = y1 - y0
        length = math.hypot(dx, dy)
        steps = max(1, int(length / (w / 3.0)) + 1)
        for s in range(steps + 1):
            t = s / steps
            self.circle(x0 + dx * t, y0 + dy * t, w / 2.0, color)

    def arc(self, cx, cy, r, a0, a1, w, color):
        n = max(2, int(abs(a1 - a0) * r / (w / 2.0)) + 1)
        for s in range(n + 1):
            a = a0 + (a1 - a0) * s / n
            self.circle(cx + r * math.cos(a), cy + r * math.sin(a), w / 2.0, color)


def downsample(cv):
    out = bytearray(W * H * 3)
    for y in range(H):
        for x in range(W):
            r = g = b = 0
            for dy in range(SS):
                row = (y * SS + dy) * IW * 3
                for dx in range(SS):
                    i = row + (x * SS + dx) * 3
                    r += cv.px[i]
                    g += cv.px[i + 1]
                    b += cv.px[i + 2]
            o = (y * W + x) * 3
            out[o] = r // (SS * SS)
            out[o + 1] = g // (SS * SS)
            out[o + 2] = b // (SS * SS)
    return bytes(out)


# --- colors ---
WHITE = (255, 255, 255)
SHADE = (232, 232, 232)
SOFT = (240, 240, 240)
INK = (43, 43, 43)
INK2 = (70, 70, 70)
BLUSH = (255, 179, 193)
GREEN = (105, 181, 120)
GREEN_D = (78, 154, 95)
GREEN_L = (124, 195, 131)
RED = (230, 57, 70)
RED_D = (200, 40, 55)
PINK = (255, 183, 197)
YELLOW = (255, 214, 120)


def draw(cv):
    cv.vgrad((255, 229, 236), (211, 240, 222))
    cv.ellipse(140, 100, 90, 34, WHITE, 0.92)
    cv.ellipse(660, 80, 80, 30, WHITE, 0.92)
    cv.ellipse(720, 300, 55, 20, WHITE, 0.85)
    cv.ellipse(390, 705, 270, 34, (183, 220, 196), 0.5)
    for (fx, fy, fr, fc) in ((90, 640, 8, PINK), (700, 640, 8, YELLOW),
                             (110, 720, 7, YELLOW), (680, 730, 7, PINK)):
        cv.circle(fx, fy, fr, fc)
        cv.circle(fx, fy, 3, WHITE)
    cv.thick_line(602, 95, 602, 720, 36, GREEN)
    cv.thick_line(590, 95, 590, 720, 6, GREEN_D)
    for ny in (230, 395, 560):
        cv.ellipse(602, ny, 23, 8, GREEN_D)
    cv.poly(((602, 110), (668, 64), (648, 140)), GREEN_L)
    cv.poly(((602, 130), (540, 84), (560, 150)), GREEN_D)
    cv.poly(((602, 300), (660, 270), (640, 330)), GREEN_L)
    cv.poly(((590, 720), (560, 680), (600, 690)), GREEN)
    cv.ellipse(360, 560, 175, 155, SHADE)
    cv.ellipse(360, 560, 170, 150, WHITE)
    cv.ellipse(360, 605, 110, 85, SOFT)
    cv.ellipse(255, 685, 58, 40, INK)
    cv.ellipse(465, 685, 58, 40, INK)
    cv.circle(238, 210, 54, INK)
    cv.circle(482, 210, 54, INK)
    cv.circle(238, 210, 28, INK2)
    cv.circle(482, 210, 28, INK2)
    cv.circle(360, 330, 154, SHADE)
    cv.circle(360, 330, 150, WHITE)
    cv.ellipse(302, 318, 36, 52, INK, 1.0, 0.35)
    cv.ellipse(418, 318, 36, 52, INK, 1.0, -0.35)
    cv.circle(302, 312, 17, WHITE)
    cv.circle(418, 312, 17, WHITE)
    cv.circle(304, 314, 9, INK)
    cv.circle(416, 314, 9, INK)
    cv.circle(298, 306, 4, WHITE)
    cv.circle(414, 306, 4, WHITE)
    cv.ellipse(360, 382, 19, 13, INK)
    cv.arc(360, 388, 20, 0.2 * math.pi, 0.8 * math.pi, 5, INK)
    cv.ellipse(252, 388, 28, 17, BLUSH, 0.55)
    cv.ellipse(468, 388, 28, 17, BLUSH, 0.55)
    cv.thick_line(285, 480, 575, 545, 48, INK)
    cv.thick_line(435, 480, 590, 500, 48, INK)
    cv.circle(578, 548, 30, INK)
    cv.circle(592, 502, 30, INK)
    cv.thick_line(250, 468, 470, 472, 36, RED)
    cv.circle(405, 478, 24, RED)
    cv.poly(((395, 495), (430, 495), (425, 575), (400, 560)), RED)
    cv.poly(((375, 492), (398, 498), (388, 560), (368, 548)), RED_D)
    cv.ellipse(678, 200, 16, 22, PINK, 1.0, -0.4)
    cv.ellipse(702, 200, 16, 22, (255, 214, 224), 1.0, 0.4)
    cv.thick_line(690, 192, 690, 214, 4, INK)
    cv.thick_line(690, 192, 682, 182, 2, INK)
    cv.thick_line(690, 192, 698, 182, 2, INK)


def render():
    cv = Canvas()
    draw(cv)
    return downsample(cv)


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    data = encode_png(render(), W, H)
    path = os.path.join(out_dir, "entry.png")
    with open(path, "wb") as f:
        f.write(data)
    print("wrote " + path + " " + str(len(data)) + " bytes")


if __name__ == "__main__":
    main()
