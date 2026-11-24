import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

S = 2048
k = S / 1024


def px(v):
    return int(round(v * k))


fond = Image.new("RGBA", (S, S), (0, 0, 0, 0))
x0, y0, x1, y1 = px(100), px(100), px(924), px(924)
rayon = px(186)

ombre = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(ombre)
d.rounded_rectangle((x0, y0 + px(14), x1, y1 + px(14)), rayon, fill=(0, 0, 0, 110))
ombre = ombre.filter(ImageFilter.GaussianBlur(px(18)))
fond.alpha_composite(ombre)

degrade = Image.new("RGBA", (S, S))
haut = (29, 53, 87)
bas = (42, 157, 143)
gd = ImageDraw.Draw(degrade)
for y in range(S):
    t = min(max((y - y0) / (y1 - y0), 0), 1)
    t = t * t * (3 - 2 * t)
    c = tuple(int(haut[i] + (bas[i] - haut[i]) * t) for i in range(3)) + (255,)
    gd.line([(0, y), (S, y)], fill=c)
masque = Image.new("L", (S, S), 0)
ImageDraw.Draw(masque).rounded_rectangle((x0, y0, x1, y1), rayon, fill=255)
carre = Image.new("RGBA", (S, S), (0, 0, 0, 0))
carre.paste(degrade, (0, 0), masque)

lumiere = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ImageDraw.Draw(lumiere).ellipse((px(140), px(-260), px(900), px(420)), fill=(255, 255, 255, 40))
lumiere = lumiere.filter(ImageFilter.GaussianBlur(px(90)))
lumiere_m = Image.new("L", (S, S), 0)
lumiere_m.paste(lumiere.split()[3], (0, 0), masque)
lumiere.putalpha(lumiere_m)
carre.alpha_composite(lumiere)
fond.alpha_composite(carre)


def carte(img, box, remplie, alpha_bord=255):
    calque = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    dd = ImageDraw.Draw(calque)
    r = px(46)
    if remplie:
        so = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        ImageDraw.Draw(so).rounded_rectangle((box[0], box[1] + px(16), box[2], box[3] + px(16)), r, fill=(8, 25, 45, 120))
        so = so.filter(ImageFilter.GaussianBlur(px(20)))
        img.alpha_composite(so)
        dd.rounded_rectangle(box, r, fill=(255, 255, 255, 255))
        entete = (box[0], box[1], box[2], box[1] + px(96))
        dd.rounded_rectangle(entete, r, fill=(42, 157, 143, 255))
        dd.rectangle((box[0], box[1] + px(60), box[2], box[1] + px(96)), fill=(42, 157, 143, 255))
        larg = box[2] - box[0]
        for i in (1, 2):
            x = box[0] + larg * i / 3
            dd.line([(x, box[1] + px(96)), (x, box[3] - px(24))], fill=(206, 222, 230, 255), width=px(9))
        haut_lignes = box[1] + px(96)
        pas = (box[3] - haut_lignes) / 4
        for j in (1, 2, 3):
            y = haut_lignes + pas * j
            dd.line([(box[0] + px(24), y), (box[2] - px(24), y)], fill=(206, 222, 230, 255), width=px(9))
    else:
        dd.rounded_rectangle(box, r, fill=(255, 255, 255, 46), outline=(255, 255, 255, alpha_bord), width=px(16))
        larg = box[2] - box[0]
        for i in (1, 2):
            x = box[0] + larg * i / 3
            dd.line([(x, box[1] + px(110)), (x, box[3] - px(40))], fill=(255, 255, 255, 120), width=px(9))
        haut_lignes = box[1] + px(96)
        pas = (box[3] - haut_lignes) / 4
        for j in (1, 2, 3):
            y = haut_lignes + pas * j
            dd.line([(box[0] + px(40), y), (box[2] - px(40), y)], fill=(255, 255, 255, 120), width=px(9))
        dd.line([(box[0] + px(8), box[1] + px(96)), (box[2] - px(8), box[1] + px(96))], fill=(255, 255, 255, alpha_bord), width=px(14))
    img.alpha_composite(calque)


carte(fond, (px(232), px(250), px(632), px(690)), False, 235)
carte(fond, (px(392), px(370), px(792), px(810)), True)

cad = Image.new("RGBA", (S, S), (0, 0, 0, 0))
dc = ImageDraw.Draw(cad)
cx, cy = px(742), px(772)
so = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ImageDraw.Draw(so).ellipse((cx - px(128), cy - px(116), cx + px(128), cy + px(140)), fill=(8, 25, 45, 140))
so = so.filter(ImageFilter.GaussianBlur(px(16)))
fond.alpha_composite(so)
dc.ellipse((cx - px(124), cy - px(124), cx + px(124), cy + px(124)), fill=(244, 162, 97, 255), outline=(255, 255, 255, 255), width=px(14))
dc.rounded_rectangle((cx - px(58), cy - px(12), cx + px(58), cy + px(70)), px(16), fill=(255, 255, 255, 255))
dc.arc((cx - px(40), cy - px(78), cx + px(40), cy + px(6)), 180, 360, fill=(255, 255, 255, 255), width=px(18))
dc.line([(cx - px(40), cy - px(36)), (cx - px(40), cy - px(8))], fill=(255, 255, 255, 255), width=px(18))
dc.line([(cx + px(40), cy - px(36)), (cx + px(40), cy - px(8))], fill=(255, 255, 255, 255), width=px(18))
dc.ellipse((cx - px(13), cy + px(12), cx + px(13), cy + px(38)), fill=(231, 111, 81, 255))
dc.rectangle((cx - px(5), cy + px(30), cx + px(5), cy + px(54)), fill=(231, 111, 81, 255))
fond.alpha_composite(cad)

sortie = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "macos"
final = fond.resize((1024, 1024), Image.LANCZOS)
final.save(sortie / "icone.png")
final.save(sortie / "applet.icns", sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)])
print("icône écrite dans", sortie)
