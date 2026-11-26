"""Generate the app icon (app.ico) used by the production build and shortcut."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
SIZE = 512


def font(size):
    for name in ("seguisb.ttf", "segoeuib.ttf", "arialbd.ttf", "segoeui.ttf", "arial.ttf"):
        path = Path("C:/Windows/Fonts") / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def build():
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Blue gradient tile with rounded corners.
    tile = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    td = ImageDraw.Draw(tile)
    top, bottom = (37, 99, 235), (29, 78, 216)  # #2563eb -> #1d4ed8
    for y in range(28, SIZE - 28):
        t = (y - 28) / (SIZE - 56)
        color = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,)
        td.line((28, y, SIZE - 28, y), fill=color)
    td.rounded_rectangle((28, 28, SIZE - 28, SIZE - 28), radius=104, outline=(147, 197, 253, 255), width=3)

    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle((28, 28, SIZE - 28, SIZE - 28), radius=104, fill=255)
    img.paste(tile, (0, 0), mask)

    draw = ImageDraw.Draw(img)
    f = font(268)
    draw.text((SIZE / 2, SIZE / 2 - 8), "₹", font=f, fill="white", anchor="mm")
    draw.rounded_rectangle((166, 386, 346, 398), radius=6, fill=(191, 219, 254, 255))

    preview = ROOT / "app_icon.png"
    ico = ROOT / "app.ico"
    img.save(preview)
    img.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", ico)
    print("wrote", preview)


if __name__ == "__main__":
    build()
