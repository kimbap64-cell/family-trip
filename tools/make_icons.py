"""홈 화면 앱 아이콘(PNG) 생성 — 한 번 만들어 icons/ 에 커밋한다. 필요: pillow"""
import os
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "icons")
GREEN, WHITE, WARM = (43, 122, 87), (255, 255, 255), (255, 214, 102)
FONT = r"C:\Windows\Fonts\malgunbd.ttf"


def draw(size, maskable=False):
    im = Image.new("RGB", (size, size), GREEN)
    d = ImageDraw.Draw(im)
    if not maskable:  # 일반 아이콘은 둥근 모서리(투명) — 마스크 가능 아이콘은 꽉 채움(OS가 자름)
        im = im.convert("RGBA")
        m = Image.new("L", (size, size), 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * .22), fill=255)
        bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        bg.paste(im, (0, 0), m)
        im = bg
        d = ImageDraw.Draw(im)
    s = size * (0.8 if maskable else 1.0)  # 마스크 가능은 안전영역(중앙 80%) 안에 그린다
    o = (size - s) / 2
    P = lambda x, y: (o + x * s, o + y * s)
    d.ellipse([*P(.62, .12), *P(.82, .32)], fill=WARM)                    # 해
    d.polygon([P(.14, .56), P(.5, .24), P(.86, .56)], fill=WHITE)          # 지붕
    d.rectangle([*P(.24, .54), *P(.76, .78)], fill=WHITE)                  # 집
    d.rectangle([*P(.44, .62), *P(.56, .78)], fill=GREEN)                  # 문
    try:
        f = ImageFont.truetype(FONT, int(s * .13))
        t = "나들이"
        w = d.textlength(t, font=f)
        d.text((o + (s - w) / 2, o + s * .82), t, font=f, fill=WHITE)
    except OSError:
        pass
    return im


os.makedirs(OUT, exist_ok=True)
draw(192).save(os.path.join(OUT, "icon-192.png"))
draw(512).save(os.path.join(OUT, "icon-512.png"))
draw(512, maskable=True).save(os.path.join(OUT, "icon-maskable-512.png"))
draw(180, maskable=True).convert("RGB").save(os.path.join(OUT, "apple-touch-icon.png"))
print("아이콘 생성:", sorted(os.listdir(OUT)))
