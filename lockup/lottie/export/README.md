# Mascot Lottie exports

Per-job folders (see `lockup/LOTTIE_RUNBOOK.md`):

| Job | Plate | Source | Files |
|-----|-------|--------|-------|
| `thumbs_5829/` | light gray | Kling 5829 thumbs-up | `mascot_{idle,thumbs,full}.json` |
| `clip_5896/` | black | Kling 5896 thumbs-up | `mascot_{idle,thumbs,full}.json` |

Rebuild a job:

```bash
lockup/source/.venv/bin/python lockup/lottie/convert_mov.py \
  --mov /path/to/file.mov --job my_slug
```

Preview: `cd lockup/lottie && python3 -m http.server` → `preview.html`
