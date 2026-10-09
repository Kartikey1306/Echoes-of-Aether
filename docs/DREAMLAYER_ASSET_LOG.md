# DreamLayer Asset Log

Status date: 2026-10-08. DreamLayer was first used on 2026-10-06 at the user's explicit request ("use DreamLayer to
make something"), after promotional credits became available (100 promotional, 0 purchased). Earlier entries: none
(0 credits until then, and the user had ruled out AI imagery; that directive was lifted by the user on 2026-10-06).

| Asset | Reason | Prompt (summary) | Reference | Operation | Result | Credit usage | Integration status | Accepted / rejected | Revision notes |
|---|---|---|---|---|---|---|---|---|---|
| `dreamlayer/characters/kael/kael_master_front.png` | Master identity reference for the Kael remake (face, hair, outfit, armour, forearm interface) | Full-body front concept of Kael Voss: rugged handsome face, swept side-part hair, graphite quilted techwear jacket, olive suit, chest rig, segmented pauldrons, glowing cyan right-forearm interface, armoured boots; stylized-realistic AAA | none (text) | text_to_image | 1728x2304 PNG | 1 | Reference for the character modellers; not shipped in the game | Accepted | Scar reads as an "x"; pauldrons heavier than the in-game model |
| `dreamlayer/characters/lyra/giva_master_front.png` | Master identity reference for the Giva remake | Full-body front concept of Giva Vale: refined face, long dark wavy hair, asymmetric graphite suit with violet panels, glowing magenta harness core on the left, right shoulder armour, holo forearm guard, thigh rig, armoured boots | none (text) | text_to_image | 1728x2304 PNG | 1 | Reference for the character modellers; not shipped in the game | Accepted | Image includes a text label ("Aether harness / Giva Vale"); harness core sits upper-left chest |
| `dreamlayer/ads/ad_implant.png` | In-world holographic advert (city billboards) | Fictional cybernetic arm implant product shot, cyan/magenta rim light, no text | none (text) | text_to_image | 2560x1440 PNG | 1 | Shipped: `Resources/Art/DreamLayer/Ads/ad_implant.png` (1024x576), shown on about one in three city hologram adverts (`NeonKit.HoloPanel`) | Accepted | |
| `dreamlayer/ads/ad_ramen.png` | In-world holographic advert | Steaming ramen bowl street-food advert, magenta/amber neon, no text | none (text) | text_to_image | 2560x1440 PNG | 1 | Shipped, cropped to the billboard face: `Resources/Art/DreamLayer/Ads/ad_ramen.png` | Accepted | The generator drew the advert on a billboard in a street, so the bowl was cropped out |
| `dreamlayer/ads/ad_aethercore.png` | In-world holographic advert (ties to the story's Aether Core) | Floating teal energy crystal in a reactor chamber, corporate advert, no text | none (text) | text_to_image | 2560x1440 PNG | 1 | Shipped: `Resources/Art/DreamLayer/Ads/ad_aethercore.png` | Accepted | |
| `dreamlayer/ads/ad_fashion_portrait.png` | Portrait holographic advert | Fictional model in techwear with a violet visor, fashion advert, no text | none (text) | text_to_image | 1440x2560 PNG | 1 | Shipped: `Resources/Art/DreamLayer/Ads/ad_fashion_tall.png` (576x1024), portrait panels | Accepted | Fictional person |
| `dreamlayer/ads/ad_drink_portrait.png` | Portrait holographic advert | Fictional energy drink can with green/cyan lightning, no text | none (text) | text_to_image | 1440x2560 PNG | 1 | Shipped: `Resources/Art/DreamLayer/Ads/ad_drink_tall.png` | Accepted | |
| `dreamlayer/ads/ad_hovercar.png` | In-world holographic advert | Fictional hover-car silhouette with cyan/violet neon trails, no text | none (text) | text_to_image | 2560x1440 PNG | 1 | Shipped: `Resources/Art/DreamLayer/Ads/ad_hovercar.png` | Accepted | Queued for about an hour at DreamLayer before it ran |

## Summary

| Item | Value |
|---|---|
| Balance before first use (2026-10-06) | 100 promotional credits, 0 purchased |
| Images generated | 8 (2 concept references 2026-10-06, 6 in-world adverts 2026-10-08) |
| Credits consumed | 8 (98 promotional left before the 2026-10-08 batch) |
| DreamLayer images shipped inside the game | 6 holographic city adverts, including the Arcology Gate mega-billboard (Aether crystal) and the plaza Noodle Bar (ramen); the two concepts remain references only |
| DreamLayer images in marketing material | 2 comparison images in `marketing/jam/` (the two hero concepts next to the in-game heroes; the ramen and AetherCore adverts next to their billboards in the city) |

No API key or other secret appears in this file or anywhere in the repository (validator secret scan).
