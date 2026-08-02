# Contributing

Thanks for looking. Issues and pull requests are both welcome — bug reports, a label workflow
that's awkward, or a feature you'd want.

**How changes land:** anyone can open an issue or a pull request. PRs are merged by the
maintainer after review; CI has to be green.

## Getting it running

```bash
docker compose up --build      # http://localhost:8080
```

Or run the pieces directly — the backend needs an OpenSCAD **2025 or newer** on your machine
(see below for why):

```bash
cd backend
pip install -r requirements.txt
OPENSCAD_BIN=/path/to/OpenSCAD.AppImage DATA_DIR=/tmp/cullenect \
  RENDER_CACHE=/tmp/cullenect/cache uvicorn app.main:app --port 8000

cd app && npm install && npm run dev     # proxies /api to :8000
```

## Tests

```bash
cd backend && python -m pytest tests -q
```

The suite is organised around behaviour that would otherwise fail silently — a substituted
font, a dropped label, an overlapping plate. Renderer-dependent tests skip automatically if
OpenSCAD isn't on your machine, so the rest still runs anywhere.

**If you add behaviour that can be stated as a rule, add the test that holds it.** Two bugs
that shipped here were things everyone assumed were true: label ids were regenerated on every
read (so saving 404'd), and the editor became unreachable below a certain window width. Both
are now tests.

## Things that will bite you

**The renderer must be OpenSCAD 2025+.** Colored 3MF (`-O export-3mf/color-mode`) doesn't exist
before that, and the Manifold backend is ~250× faster than CGAL for this geometry. On an older
OpenSCAD the app still runs but exports lose their color; `/api/health` reports it.

**`backend/scad/Cullenect.scad` is vendored verbatim — don't edit it.** It's upstream's file at
a pinned commit, and patching it here would silently diverge from the Cullenect standard, so
labels would stop fitting other people's sockets. Change behaviour by changing the parameters
the app passes. To take an upstream update: copy the new file in, update the commit hash in
`NOTICE`, and check `backend/app/models.py` still lists every option the customizer offers —
`test_every_offered_option_actually_validates` will catch a mismatch.

**Unknown parameter values fail silently in OpenSCAD.** The `.scad` matches options with an
if-chain, so a typo doesn't error — it renders the label with the icon missing, and you find
out after printing. That's why every option field is validated at the API edge; keep new ones
validated too.

**Fonts substitute silently.** Any font offered in the UI must actually be installed in the
image, or OpenSCAD quietly renders a different face. If you add a font to the picker, add it to
the `Dockerfile` as well.

**Check narrow and very wide windows.** Layout bugs here have twice made the app unusable — once
below 1024px (editor off-screen in a container that couldn't scroll) and once at 3440px (the
middle column absorbed all the width). If you touch layout, look at it at ~390px, ~900px and an
ultrawide.

## Style

Match what's there. Comments explain *why* something is the way it is — particularly where the
obvious approach doesn't work — rather than restating the code.
