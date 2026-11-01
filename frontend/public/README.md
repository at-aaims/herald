# Static assets (served at the site root)

Drop the branding logos here so the sidebar shows them:

- `ornl-logo.svg`     — the ORNL wordmark (the SVG you have). Served at `/ornl-logo.svg`.
- `frontier-logo.png` — the Frontier logo PNG. Served at `/frontier-logo.png`.

The sidebar renders both at the top (`frontend/app/page.tsx`) and hides any that
are missing, so the UI stays clean until the files are added. A dark-friendly
(light or transparent-background) version reads best on the dark surface.
