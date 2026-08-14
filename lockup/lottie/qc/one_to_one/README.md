# 1:1 frame QC (Lottie player vs plate)

Mapping (0-based Lottie index → 1-based `frames_rgba`):

| Clip | Formula |
|------|---------|
| intro | Lottie `t` → `frame_{t+1:04d}.png` |
| wave | Lottie `t` → `frame_{145+t:04d}.png` |
| sit | Lottie `t` → `frame_{289+t:04d}.png` |
| full | Lottie `t` → `frame_{t+1:04d}.png` |

## Timing lock
- wave L72 best-matches S216/S217 (tied; expected **S217**)
- intro L120 best-matches **S121**

## Metrics (player SVG vs magenta plate)
- Silhouette IoU ≈ **0.935** (gap is ~1–2px SVG antialias fringe, ~44k extra px)
- Color closeness (Δ<80 on overlap) ≈ **97.7%**
- Mean abs channel error ≈ **4.5**

Screenshots: `compare_*` (plate | player | heat), `dense_wave_*`, `CONTACT_SHEET_1to1.png`.
