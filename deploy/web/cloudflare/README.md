# deploy

Deploys the site in `web/` (repo root) to Cloudflare as a static-assets Worker (`kavach-web`) on the
custom domain **kavach.lib13.com**.

```sh
pip install markdown          # once, for build.py
./deploy.sh                   # build web/index.html from SPEC.md, then wrangler deploy
./deploy.sh --dry-run         # validate without deploying
npm run dev                   # build, then preview locally with wrangler dev
```

- `build.py` renders `SPEC.md` (repo root) (a copy of the live Claude Doc, *Agent Containment Toolkit —
  Pitch & Spec*) into `web/index.html`. When the doc changes, re-export it into `SPEC.md` and redeploy.
- `web/slides/index.html` is the hackathon deck (kavach.lib13.com/slides/). It is hand-written, not
  generated; the hero's "Demo presentation" button links to it.
- `lib13.com` must be a zone on the Cloudflare account you're logged into (`npx wrangler whoami`);
  Wrangler creates the `kavach` DNS record and certificate on first deploy.
