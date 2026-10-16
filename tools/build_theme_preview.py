"""Create a compact README GIF from the two current editor smoke renders."""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
frames = []
for name in ('hardware-preview.png', 'network-preview.png'):
    with Image.open(ROOT / 'artifacts/editor-smoke' / name) as source:
        # Match the physical panel's visible height; leave theme assets untouched.
        frame = source.convert('RGB').crop((0, 0, 1920, 462))
        frame = frame.resize((1280, 308), Image.Resampling.LANCZOS)
        frames.append(frame.quantize(colors=256))
target = ROOT / 'docs/images/cluster-retro.gif'
target.parent.mkdir(parents=True, exist_ok=True)
frames[0].save(target, save_all=True, append_images=frames[1:], duration=3000,
               loop=0, optimize=True, disposal=2)
print(target)
