# Setup — Nikhilreddy1011 self-generating profile

## 1. Create the repo (must match your username exactly)
```bash
gh repo create Nikhilreddy1011 --public --clone
cd Nikhilreddy1011
```
Then copy everything from this folder into it (README.md, requirements.txt,
scripts/, .github/, fonts/).

## 2. Install local dependencies (only needed for the portrait step)
```bash
pip install -r requirements.txt
```
First run downloads a ~176 MB background-removal model — once, then cached.

## 3. Generate the portrait (local, one-time — then commit the SVG)
Take a photo following the guide's requirements:
- side light at ~45°, plain background
- tight crop: chin to just above the hair
- 1200px+ resolution
- slight angle, not dead-on

```bash
python3 scripts/generate_portrait.py --input your-photo.jpg --output portrait.svg
```

Optional — embed a font so it doesn't render 7% narrower on Windows
(see `fonts/SUBSET_INSTRUCTIONS.md` first):
```bash
python3 scripts/generate_portrait.py --input your-photo.jpg --output portrait.svg --font fonts/ramp.woff2
```

Preview it before committing — a full-page headless-Chrome screenshot
restarts the SMIL animation, so use a tall viewport and wait ~5s instead.

## 4. Commit the portrait
```bash
git add portrait.svg
git commit -m "add portrait"
git push
```

## 5. Let the Action generate the stats
The workflow in `.github/workflows/refresh-stats.yml` runs nightly at
05:17 UTC and on manual dispatch. It needs no secrets beyond the
built-in `GITHUB_TOKEN` — nothing to configure.

To trigger it immediately instead of waiting for the cron:
```bash
gh workflow run "refresh stats"
```

## 6. Verify markdown survives GitHub's sanitiser
Before committing README changes, test against the same sanitiser
GitHub's site uses:
```bash
curl -X POST https://api.github.com/markdown \
  -H "Authorization: bearer $(gh auth token)" \
  -H "Content-Type: application/json" \
  -d '{"text": "'"$(cat README.md | sed 's/"/\\"/g' | tr '\n' ' ')"'"}'
```

## 7. If the README doesn't show up on your profile
A newly created profile README is cached — edit it once through the
web UI to force a refresh.

## 8. Two things the API can't do (manual, in the UI, no way around it)
- Pinned repositories
- Your bio

## Gotchas to remember
- Don't colour per character in the portrait — one fill colour, or it
  looks like static.
- Regenerating stats locally too (in addition to the Action) will cause
  merge conflicts — your local run and the workflow's run bucket days
  near a week boundary differently, so output is never byte-identical.
  Let the Action own the generated `.svg` files.
