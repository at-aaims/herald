# deploy/

Docker dev stack for HERALD (backend + frontend + optional ClickHouse) —
see `Makefile`'s `docker-up`/`docker-down`/`clickhouse-up`/`clickhouse-down`
targets.

## Corporate TLS-inspecting proxy (e.g. ORNL's Netskope)

If your network intercepts outbound HTTPS (common on corporate VPNs), the
Docker container needs to separately trust that proxy's CA — your host
already does (via its OS-level/MDM-installed trust store), but a fresh
container's minimal trust store doesn't know about it, so calls to Azure,
PyPI, etc. fail cert verification *only inside the container*.

Fix: export the CA's public certificate (not a secret — CA certs are public
trust anchors by design) and place it at `deploy/ornl-netskope-ca.pem`
(gitignored, since it's site-specific, not something to publish). On macOS,
find it via Keychain Access (search the intercepting proxy's name, e.g.
"netskope" or "goskope") or:

```bash
security find-certificate -a -p /Library/Keychains/System.keychain \
  | csplit -s -z -f /tmp/cert_ - '/-----BEGIN CERTIFICATE-----/' '{*}'
# then grep each /tmp/cert_* for the proxy's subject via:
#   openssl x509 -in /tmp/cert_N -noout -subject
```

**Include the full chain, not just one cert.** A TLS-inspecting proxy
typically has an intermediate (site-specific, e.g. `ca.ornl.goskope.com`)
signed by a separate, self-signed root (e.g. `caadmin.netskope.com`) — check
with `openssl x509 -in <cert> -noout -subject -issuer`; if `-issuer` doesn't
match `-subject`, that cert isn't the root and you need the one that issued
it too. Missing the root produces a different, easy-to-misread error than
missing everything: `unable to get issuer certificate` instead of `self-signed
certificate in certificate chain`. Concatenate both into the one `.pem` file
(order doesn't matter):

```bash
cat intermediate.pem root.pem > deploy/ornl-netskope-ca.pem
```

`Dockerfile.backend`'s `COPY deploy/ornl-netskope-ca.pem*` (note the trailing
`*`) makes this optional — the build still succeeds with no proxy cert
present, it just skips the trust step, so this isn't required on networks
without TLS inspection. This optional-glob behavior relies on BuildKit
(Docker Desktop's default builder since 2021); a legacy non-BuildKit builder
errors on a COPY glob that matches zero files instead of skipping it. Run
`docker buildx version` to confirm BuildKit is active if a build fails here
unexpectedly.

The Dockerfile points `SSL_CERT_FILE`/`REQUESTS_CA_BUNDLE` at the system
trust store (which `update-ca-certificates` builds from the cert above)
rather than patching Python's `certifi` package directly — appending to
`certifi`'s bundle file used to be how this worked, but `pip install -e .`
runs later in the build and can silently reinstall/re-resolve `certifi`,
overwriting its bundle with a pristine copy and erasing the appended cert.
Happened in practice on this project, not a hypothetical.

**Only RAG indexing needs this.** It's the one build/boot step that reaches
out to HuggingFace to download the embedding model — chat, SQL, syslog, and
job-prediction don't touch the network the same way and aren't affected if
this is misconfigured. If RAG indexing fails at boot (wrong/missing cert,
or a network that blocks HuggingFace entirely), the backend logs a clear
warning and starts anyway rather than refusing to boot — RAG search just
won't work until it's fixed. To skip the attempt entirely (e.g. you know
this network can't reach HuggingFace and don't want to wait for it to fail
on every restart), set `SKIP_RAG_INDEX=1` in `.env`.
