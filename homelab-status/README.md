# Homelab

A status board for the services on your [Dashy](https://dashy.to) dashboard.
Every item that has a `url` gets an HTTP check on an interval. Each service
then shows as up (green), responding with an error code (orange), down (red)
or not checked (gray).

## Setup

Configure the App under **Settings > Apps > Installed > Homelab >
Environment**. No rebuild is needed. Restart the App, or tap its header, to
apply changes.

### Without Dashy: `HOMELAB_SERVICES`

List your services directly. The field is single-line, so use one of these
compact forms:

```text
Server: Gitea=http://raspberrypi.local:8124, Beszel=http://raspberrypi.local:8090; NAS: UGOS=http://192.168.1.10:9999
```

```json
{"Server": {"Gitea": "http://raspberrypi.local:8124", "Portainer": "https://raspberrypi.local:9443"}, "NAS": {"UGOS": "http://192.168.1.10:9999"}}
```

Sections are separated with `;` and services with `,`. A service is
`Title=URL`, or just a URL, which is then titled by its host. The JSON form
also accepts Dashy's own shape (`{"sections": [...]}`) or a list of sections,
including per-item options such as `statusCheckAcceptCodes`. When
`HOMELAB_SERVICES` is set, it takes precedence over `DASHY_URL`.

### With Dashy: `DASHY_URL`

Set **DASHY_URL** in the App environment to your Dashy address, for example
`http://raspberrypi.local:4000`. The App loads `<DASHY_URL>/conf.yml` plus any
sub-pages listed under `pages:`. You can also give a direct link to any
Dashy-format `.yml` or JSON file, for example a raw Gist. The last config
fetched is cached, so the board still works when Dashy itself is down.

### Bundled file

If neither env value is set, the App reads a `conf.yml` in Dashy's format from
its own directory, which you add before zipping the App. It is gitignored so your service list stays out of the
repository. Only `sections[].items[]` matter:

```yaml
pageInfo:
  title: Home Lab
sections:
  - name: Server
    items:
      - title: Gitea
        url: http://raspberrypi.local:8124/
      - title: Portainer
        url: https://raspberrypi.local:9443/
        statusCheckAcceptCodes: "401"
```

| Env | Default | Meaning |
| --- | --- | --- |
| `HOMELAB_SERVICES` | empty | Inline service list (see above) |
| `DASHY_URL` | empty | Dashy address or `conf.yml` link |
| `CHECK_INTERVAL` | `60` | Seconds between check rounds (minimum 5) |
| `CHECK_TIMEOUT` | `6` | Seconds before a service counts as down |

Supported Dashy item options: `statusCheck: false` (skip),
`statusCheckUrl` (check a different URL), `statusCheckAcceptCodes` (extra
codes that count as up) and `statusCheckMaxRedirects: 0` (do not follow
redirects). Any 2xx or 3xx response counts as up. TLS certificates are not
verified, so self-signed homelab certificates work.

`.local` hostnames work even though the NanoKVM cannot resolve them itself:
the App sends its own mDNS query when normal DNS lookup fails.

## Controls

- Swipe up/down, or tap the footer arrows, to move between pages.
- The first page sums up each Dashy section and lists the current issues. Tap a
  section to open it.
- Tap a service to see its URL, last result, uptime and a latency history.
  **RECHECK** checks it again right away.
- Tap the middle of the footer to check everything now.
- Tap the header to reload the Dashy config.

## Tests

```sh
python3 -m unittest discover -s homelab-status -p 'test_*.py'
```
