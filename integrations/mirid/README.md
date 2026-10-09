# Mirid desktop integration

Mirid Identity is being built as Mirid's own age-verification layer. This release
integrates its face-comparison and signed-evidence components; age decisions and
production access enforcement are not implemented yet. See
[the service scope](../../docs/service-scope.md).

The standalone Python package works without Mirid. This directory also carries
the new Mirid interface and local API adapter as source, for integration with
Mirid's React frontend and FastAPI service. It does not contain an entire Mirid
distribution.

Install the package with its `face` dependencies in the Python environment used
by Mirid, then run `mirid-identity models download` as the desktop user. Models
normally live in `$XDG_CACHE_HOME/mirid-identity/models` or
`~/.cache/mirid-identity/models`. `MIRID_IDENTITY_MODEL_DIR` overrides that path.

Copy the files using their relative paths. In `backend/app/main.py`, import
`identity_router` from `.identity_routes` and call
`app.include_router(identity_router)`. Retain Mirid's local Host/Origin boundary
middleware. The adapter additionally restricts identity requests to loopback
clients, even when another Mirid feature allows LAN access. Add `identity` to
the private-route matcher in `backend/app/privacy_logging.py`.

In `frontend/src/App.jsx`, import `IdentityPage` from
`./pages/IdentityPage` and render it when `activeTab` is `identity`. In
`frontend/src/components/Navbar.jsx`, add the tool entry
`{ id: 'identity', label: 'Identity verification', icon: Fingerprint }`, importing
`Fingerprint` from `lucide-react`. Build the frontend and desktop host so the new
screen is embedded in the native application.

The page uses Mirid's existing Button, endpoint and local-fetch helpers. Review
those imports when porting to another version. The adapter expects the existing
`runtime_paths.runtime_config_root` helper; issuer and policy configurations go
in its `identity` subdirectory. No issuer or calibration is enabled by default.
See the package's `examples` and `docs/evidence-protocol.md` before configuring
real issuers.

Available routes:

| Route | Purpose |
| --- | --- |
| `GET /identity/status` | Check local model integrity and configuration presence |
| `POST /identity/compare` | Compare two consented images in memory |
| `POST /identity/challenge` | Bind a fresh challenge to the subject and image bytes |
| `POST /identity/verify` | Consume a session and verify trusted signed assertions |
| `DELETE /identity/session` | Clear pending server image bytes early |

Requests use JSON. Images are JPEG, PNG or WebP data URLs, up to 8 MB each and
16 megapixels. Pending sessions expire after five minutes, with at most four
held in memory. Camera frames do not constitute presentation-attack detection.
The UI neither stores images in browser storage nor includes them in chats.

Tests under this directory run inside the corresponding Mirid checkout. The
package's ordinary `pytest` suite exercises the standalone crypto, policy and
face engine without needing a Mirid checkout.
