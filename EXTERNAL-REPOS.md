# Independent public owners and machine integrations

| Component | Owner/source | Candidate boundary |
| --- | --- | --- |
| pi-boxed-tools | https://github.com/BubbatheVTOG/pi-boxed-tools | Commit `9ad64f8d773708aef9a823a2bc896c5537d8b0e0`, HTTPS archive in npm union lock; source not forked here |
| OpenCodeHyperTermTheme | https://github.com/BubbatheVTOG/OpenCodeHyperTermTheme | Existing `config/themes/` fallback snapshots retained; no mutable external theme symlink |
| agent-voice | https://github.com/BubbatheVTOG/agent-voice | Commit `8b32166f0d3f2f592779468f3d5b2762ec93c941`, archive SHA-256 in manifest; only extension resource deployed |
| npm plugins | Exact identities/revisions in `manifest.json` | Complete public lock in `config/dependencies/`; no sequential Pi installs |
| SearXNG | User-managed service | Optional personal feature, default endpoint `http://127.0.0.1:8080`; no service setup/startup here |
| agent-say/TTS | agent-voice owner | Separate opt-in backend prerequisite; this repository does not install/start it |

Voice remains off by default; its footer indicator is part of the same feature.
SearXNG forwards queries to its configured search engines. Neither local file storage
nor a loopback search endpoint means data stays on the machine.

Do not clone private integrations or install local notification/agent-state hooks
implicitly. They are not standalone prerequisites. Any additional integration needs
explicit feature ownership, classification, collision review and separate activation
approval; unknown existing hooks cause deployment to refuse.

## Dependency lifecycle policy

All npm candidate installs use `--ignore-scripts --legacy-peer-deps --no-audit
--no-fund`. Pi supplies host peer modules; several UI packages advertise stale peer
ranges, so compatibility is checked using the installed Pi and no-network tests,
not by installing another Pi core. npm versions/transitives and archive integrity
are fixed in the complete union lock, not copied from a live npm tree.

Reviewed package postinstall hooks in pi-tool-display/pi-image-tools search for a
separate live patch helper; they are unnecessary in a generation and are ignored.
The npm pi-lens artifact already includes its compiled distribution/grammars. Its
prepare hook (build/download/hooks/cache) is not run. Native optional npm artifacts
supply ast-grep on supported platforms; missing platform/runtime prerequisites must
be reported, not repaired during Pi startup. Pi-lens can separately auto-install
language tools during normal use; see its installed dependency/env docs and obtain
appropriate approval. This composition tool does not start those runtime paths.
