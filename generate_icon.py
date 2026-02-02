"""
Generates the yeelight.ico icon file.
Run this once after installation: python generate_icon.py
"""
from PIL import Image, ImageDraw
import os

def generate_icon():
    size = 64
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Bulb body (yellow circle)
    bulb_color = (255, 220, 50)
    draw.ellipse([14, 6, 50, 42], fill=bulb_color, outline=(200, 170, 30), width=2)

    # Bulb base (gray screw part)
    base_color = (140, 140, 140)
    draw.rectangle([22, 40, 42, 48], fill=base_color)
    draw.rectangle([24, 48, 40, 52], fill=(120, 120, 120))
    draw.rectangle([26, 52, 38, 56], fill=(100, 100, 100))

    # Filament inside
    draw.arc([26, 18, 38, 32], 0, 180, fill=(255, 150, 0), width=2)

    # Glow effect
    glow = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse([8, 0, 56, 48], fill=(255, 255, 200, 60))

    # Composite
    final = Image.alpha_composite(glow, img)

    # Save as ICO
    script_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(script_dir, 'yeelight.ico')
    final.save(icon_path, format='ICO', sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    print(f'Icon created: {icon_path}')

if __name__ == '__main__':
    generate_icon()

