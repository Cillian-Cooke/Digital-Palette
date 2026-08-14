# Segment table (draft from 1s contact sheet + spot frames)

Source: `mascot.mov` @ **24 fps**, **1440×1440**, **361 frames**, **15.04 s**
Original: `/home/cillian/Downloads/kling_20260815_VIDEO_can_you_an_147_0.mov`

Frame numbers are **1-based** (matching `frame_%04d.png`).

| Segment id | Label | Start | End | Loop? | Notes |
|------------|-------|-------|-----|-------|-------|
| `intro` | idle + expressions | 1 | 144 | no | stand → shush → clasp → eyes closed → arms-wide welcome (~0–6 s) |
| `wave` | waving | 145 | 288 | maybe | right arm raise / wave / return (~6–12 s) |
| `sit` | sitting down | 289 | 361 | yes hold | settle into seated pose, eyes closed smile (~12–15 s) |

Refine cuts on pose holds after a full scrub of `frames_rgba/`. Do **not** include Kling watermark (bottom-right).

## Next for 1:1 vector

**Current:** contour-traced Lotties in `lottie/export/` (`intro` / `wave` / `sit` / `full`) + `lottie/preview.html`.

Hierarchy to refine toward (cream fill + dark outline, prefer transforms over morph soup):

- Shackle (U)
- Head (squircle)
- Eyes ×2 (circles)
- Mouth closed (stroke) / mouth open (fill + tongue)
- Torso
- Arm_L, Arm_R (independent for wave)
- Leg_L, Leg_R (independent for sit)
