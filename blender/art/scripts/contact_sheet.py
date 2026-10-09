"""Preview contact sheets of every delivered image -> blender/art/previews/

  Blender -b --factory-startup --python contact_sheet.py
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import artkit as A  # noqa: E402

ZONES = ["plaza", "metro", "facility", "vault", "rooftops", "core"]
PORTRAITS = ["kael", "lyra", "oren", "mira", "tomas", "nia", "maren", "bolt", "guardian"]


def main():
    P = A.PREVIEWS
    load = [os.path.join(A.RES_ART, "Loading", f"{z}.jpg") for z in ZONES]
    load = [p for p in load if os.path.exists(p)]
    if load:
        A.contact_sheet(load, os.path.join(P, "sheet_loading.png"), cols=3, cell=(640, 360))
    por = [os.path.join(A.RES_ART, "Portraits", f"{c}.png") for c in PORTRAITS]
    por = [p for p in por if os.path.exists(p)]
    if por:
        A.contact_sheet(por, os.path.join(P, "sheet_portraits.png"), cols=5, cell=(256, 256))
    items = sorted(glob.glob(os.path.join(A.RES_ART, "Items", "*.png")))
    if items:
        A.contact_sheet(items, os.path.join(P, "sheet_items.png"), cols=6, cell=(192, 192))
    logo = os.path.join(A.RES_ART, "Title", "logo.png")
    if os.path.exists(logo):
        A.over_color(logo, os.path.join(P, "logo_on_dark.png"))
    mk = sorted(glob.glob(os.path.join(A.MARKETING, "*.png")))
    if mk:
        A.contact_sheet(mk, os.path.join(P, "sheet_marketing.png"), cols=2, cell=(800, 450))
    allp = load + mk + [os.path.join(P, "logo_on_dark.png")] * os.path.exists(logo) + por + items
    if allp:
        A.contact_sheet(allp, os.path.join(P, "contact_sheet.png"), cols=6, cell=(400, 225))


if __name__ == "__main__":
    main()
