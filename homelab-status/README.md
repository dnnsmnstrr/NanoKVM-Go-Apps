# Homelab

A status board for the services on your [Dashy](https://dashy.to) dashboard.
Every item that has a `url` gets an HTTP check on an interval. Each service
then shows as up (green), responding with an error code (orange), down (red)
or not checked (gray).

## Setup

Set **DASHY_URL** in the App environment to your Dashy address, for example
`http://raspberrypi.local:4000`. The App loads `<DASHY_URL>/conf.yml` plus any
sub-pages listed under `pages:`. You can also give a direct link to a `.yml`
file. The last config fetched is cached, so the board still works when Dashy
itself is down.

Without Dashy, put a `conf.yml` in Dashy's format into this directory before
zipping the App. It is gitignored so your service list stays out of the
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
