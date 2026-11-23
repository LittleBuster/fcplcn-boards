# Power split — mechanical audit

PASS — actual frozen native KiCad sources.

| Board | SHA256 |
|---|---|
| Upper | `efbac1f16778141782f6dc2f035f00b5267eb7b93ceb189ee218b322c01f7f08` |
| Lower | `15ab3935683fea5c40f0f1efeb9c5d5e8f763ca321789e3e115367d0fb38f096` |

Board clearance **11.05 mm**; Upper F above Lower F **12.65 mm**. Both outlines and four mating connector footprints are unchanged.

| Envelope | Bounds X/Y, mm | Maximum height |
|---|---|---|
| Lower.U2 | 137.025, 83.260, 144.825, 95.260 | 10.7 mm |
| Upper.U17 | 99.965, 72.150, 112.065, 81.150 | 10.9 mm |

Minimum new/moved Upper B part to Lower vertical clearance: **1.050 mm**. Minimum new U17 solder-tail clearance: **0.800 mm**.

Minimum all Upper B part to Lower vertical clearance: **0.050 mm**. Minimum Upper PTH solder-tail to Lower clearance: **0.800 mm**. U17 PTH copper to SMD pad minimum: **0.447 mm**.

Lower U2 maximum case is 1.025 mm outside the Upper board edge, and 1.175 mm inside the Lower board edge.

Checks: 21. Failed checks: 0. New/changed missing models: 0. Retained baseline missing models: 1.

The global B-side minimum includes unchanged BT1 over an intentionally conservative7mm ordinary Lower component height bound; the actual new/moved-part bound is listed separately.

Every new/moved component native model reference resolves. The only retained missing file is the unchanged global KiCad model for Lower.F1 (explicit baseline limitation); unpopulated test-point pads need no 3D model. Maximum-case and solder allowances are documented in JSON; physical prototype verification remains necessary.
