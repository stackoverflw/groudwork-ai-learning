"""Generate a local multi-size Windows icon using Pillow."""
from pathlib import Path
from PIL import Image, ImageDraw
image = Image.new('RGB',(128,128),'#151c22')
draw = ImageDraw.Draw(image)
draw.rectangle((24,72,104,102),fill='#b9da8c')
draw.rectangle((46,30,82,62),fill='#b9da8c')
image.save(Path(__file__).resolve().parents[1]/'app/web/groundwork.ico',sizes=[(16,16),(32,32),(64,64),(128,128)])
