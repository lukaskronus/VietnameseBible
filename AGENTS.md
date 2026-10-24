# AGENTS.md

Bilingual Vietnamese–English Bible site. Static site built by `tools/*.py` and
deployed to Wasmer Edge; the former PHP frontend (`index.php`, `test.php`) is
gone. The six XML files in `data/xml/` are the only data source. `data/txt/` and
`data/sqlite/` are tracked legacy files that nothing reads anymore.

## Build and verify

`.github/workflows/build.yml` is the source of truth for builds. Builds run on
GitHub Actions only — the Python docstrings explicitly say local machines are
code storage, so do not run the pipeline locally. There is no test suite,
linter, or formatter; CI is the verification. Exact CI invocations:

```sh
python tools/parse_bible.py --data data --out build
python tools/build_db.py --json build/bible.json --out build
python tools/build_site.py --json build/bible.json --index build/search_index.json \
  --out site --base-url "$SITE_BASE_URL" --base-path "$SITE_BASE_PATH"
```

`--data` accepts `data/` or `data/xml/` (it resolves `xml/` itself). `build/` is
gitignored; `site/` and `site.zip` are build outputs that are never committed.
Each build uploads `site` and, separately, `site.zip` as the `site-zip`
artifact for nginx/docker hosting.

Builds trigger only on changes to `data/**`, `tools/**`, or `build.yml`.
Editing only `app.yaml`, `wasmer.toml`, or docs will not start a build.

Deployment is a separate manual workflow: `.github/workflows/deploy.yml` (must
run from `master`) downloads the latest successful `site` artifact — or the
explicit `run_id` input — patches `version` in `wasmer.toml` to
`0.1.<run_number>` (the registry rejects republishing an existing version), and
deploys. It needs the `WASMER_TOKEN` secret. `wasmer.toml` maps `site/` to
`/public` and `settings/` to `/settings`; `app.yaml` pins the app
name/owner/app_id. `SITE_BASE_URL` and `SITE_BASE_PATH` are build-time repo
variables.

`.github/workflows/cleanup.yml` deletes all workflow runs older than 30 days,
weekly and on manual dispatch.

## Rules that span multiple files

- **Daily chapter formula** lives in `tools/static/daily.js`:
  `id = ((701 * days_since_unix_epoch_UTC + 123) % total_chapters) + 1`.
  701 is coprime to 1189, so every chapter appears once per cycle.
- **Book titles** live only in `tools/parse_bible.py` (`VI_TITLES`,
  `EN_TITLES`, `OSIS`); the XML stores numbers 1–66 only. Slugs derive from the
  Vietnamese titles via `slugify()`, so renaming a book changes its URLs.
- **Search folding** must match between `fold`/`tokenize` in
  `tools/build_db.py` and `fold`/`toks` in `tools/static/search.js`: NFD, strip
  combining marks, `đ/Đ/ð/Ð → d/D`, lowercase, `[a-z0-9]+` runs, tokens of at
  least 2 chars.

## Static site internals

- Chapter IDs are global canon order `1..1189`, not per book. The pairing
  switcher fetches `data/tr/<translation-code>/ch/<id>.json` for one VI and one
  EN translation; baked chapter pages contain only the default pair.
- Client scripts read the base path from `<meta name="kt-base">`.
- `build_site.py` minifies `tools/static/*.js` with a regex that strips
  everything after `//`. Never put `//` inside a JS string or regex (a URL such
  as `https://…` would be truncated at build time).
- Verse numbers are unioned across translations; a missing verse is `""`.
  Switcher views can therefore show verses absent from the default pair
  (e.g. 3 John 15), while baked pages skip them.
