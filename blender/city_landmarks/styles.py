"""District architecture presets (lmparts.style). Floor heights 3.2-3.6 m; ground floors 4.0-5.4 m."""
from lmparts import style

# NeonMarket: dense low/mid-rise market blocks: painted render and mosaic, shops / stalls, blade lightboxes,
# AC units, awnings, red lacquer and brass trims.
MARKET = style(wall="lm_plaster_pastel", wall2="lm_mosaic_tile", trim="concrete_dark", ledge="concrete_dark", ledge_proj=0.14,
               G=4.4, H=3.4, bay=3.6, win="punched", win_w=1.6, win_h=1.6, reveal=0.2, ac=0.35, cage=0.12, balcony=0.12,
               laundry=0.25, plants=0.2, signs=0.35, cables=0.8, lit=0.45, warm=0.65, ground="shops", parapet=1.0)
MARKET_B = style(MARKET, wall="lm_mosaic_tile", wall2="lm_concrete_weathered", win="pair", win_w=1.5, ledge="lacquer_red",
                 ledge_proj=0.08, signs=0.45, cage=0.18, ac=0.4)

# KowloonStacks: tall, narrow, everything bolted on: caged windows, cantilevered rooms, AC clusters, laundry.
STACK = style(wall="lm_mosaic_tile", wall2="lm_concrete_weathered", trim="concrete_dark", ledge="concrete_dark", ledge_proj=0.06,
              G=4.0, H=3.2, bay=3.4, win="punched", win_w=1.4, win_h=1.45, reveal=0.15, mullion=False, transom=0.55,
              ac=0.55, cage=0.42, balcony=0.08, cant=0.14, laundry=0.35, plants=0.15, grille=0.3, signs=0.12, cables=1.0,
              lit=0.5, warm=0.45, ground="shops", parapet=1.1)
STACK_B = style(STACK, wall="lm_concrete_weathered", wall2="lm_mosaic_tile", cage=0.5, cant=0.2, ac=0.6)

# ArcologyGate: corporate glass and dark cladding, curtain walls with mullions, LED seams, lobby ground floors.
CORP = style(wall="lm_cladding_dark", wall2="lm_cladding_dark", trim="paint_glossy_dark", ledge="metal_dark", ledge_proj=0.05,
             ledge_h=0.12, G=5.4, H=3.6, bay=1.8, win="curtain", frame="metal_dark", ac=0.0, cage=0.0, balcony=0.0, signs=0.0,
             cables=0.0, lit=0.45, warm=0.3, ground="lobby", parapet=1.2, coping="metal_dark", led_seam="emit_strip_cyan",
             pier_proj=0.0, roof="concrete_dark", transom=True)
CORP_B = style(CORP, wall="metal_plate", led_seam="emit_strip_violet", bay=2.4)

# CanalWard: old brick / pastel render, balconies with laundry, cyber retrofits (cables, AC, LED strips).
CANAL = style(wall="lm_brick_soot", wall2="lm_plaster_pastel", trim="concrete", ledge="concrete", ledge_proj=0.12, ledge_every=1,
              G=4.2, H=3.4, bay=3.4, win="punched", win_w=1.2, win_h=1.9, win_sill=0.75, reveal=0.24, transom=0.72,
              ac=0.3, cage=0.05, balcony=0.3, laundry=0.45, plants=0.35, signs=0.1, cables=0.7, lit=0.45, warm=0.75, ground="shops",
              parapet=0.9, sill="concrete")
CANAL_B = style(CANAL, wall="lm_plaster_pastel", wall2="lm_brick_soot", trim="concrete_dark", balcony=0.4)

# FoundryRow: brick and corrugated works, steel factory glazing, roller doors.
FOUNDRY = style(wall="lm_corrugated_painted", wall2="lm_brick_soot", trim="metal_dark", ledge="metal_dark", ledge_proj=0.08,
                G=6.0, H=4.2, bay=4.8, win="industrial", ac=0.05, signs=0.0, cables=0.5, lit=0.3, warm=0.2, ground="industrial",
                parapet=0.6, sill="concrete_dark", frame="metal_dark")
FOUNDRY_B = style(FOUNDRY, wall="lm_brick_soot", wall2="lm_corrugated_painted", trim="concrete_dark")

BY_DISTRICT = {"NeonMarket": [MARKET, MARKET_B], "KowloonStacks": [STACK, STACK_B], "ArcologyGate": [CORP, CORP_B],
               "CanalWard": [CANAL, CANAL_B], "FoundryRow": [FOUNDRY, FOUNDRY_B]}
