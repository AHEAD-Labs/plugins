# Architecture build map

`index.html` is the status map: what is verified, partial, a gap, exposed or Arm-owned across the release
plane, marketplaces, laptop, AWS, Azure and MuleSoft, plus the build order. Open it in a browser
(self-contained, no network). `build-map.png` is a snapshot.

To update it, edit the card, layer and link lists in `build_map.py` and run `python3 build_map.py`
(writes `index.html`). Statuses must come from something that was run, not from intent.

Last updated 13 Nov 2026: Azure agent gateway with Entra OBO verified; MuleSoft plane added (not built).
