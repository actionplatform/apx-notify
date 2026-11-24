# apx-notify

An [Action Platform](https://github.com/actionplatform/action-platform) plugin that tells a team what happened without anyone watching the web app. When a release is cut, a deploy succeeds or fails, readiness blocks a release, or CI fails on a release tag, the platform posts it to the organization's **Slack**, **Discord** or **Microsoft Teams** channel, or to its own **webhook**, signed. Each message links back to the release's timeline, or to the app's deployments or CI runs.

It runs where the platform's events are raised: in the API and worker of a platform whose image carries it (a self-hosted platform adds it to its `api` image, see [plugins on the hosted platform](https://github.com/actionplatform/action-platform/blob/master/docs/use_plugins.md#on-the-hosted-platform)). Each organization then configures it under **Plugins → Notifications → Configure**. It needs action-platform 0.34 or later. The CLI raises no events, so installing it next to the CLI adds only `action-platform notify test`.

## What gets sent

| Event | When | By default |
|---|---|---|
| `release.created` | a release is cut on the platform | sent |
| `deployment.succeeded` | a deployment succeeds — run by the platform, or a Jenkins build or a GitHub Actions run the platform observes | sent |
| `deployment.failed` | a deployment fails, whoever ran it | sent |
| `readiness.blocked` | a release's readiness for a scope turns blocked; listed with each failing check and its fix | sent |
| `ci.failed` | a CI run on a release's tag fails | sent |
| `deployment.started` | the platform starts a deploy; an observed run is first seen queued or running | only when listed in **Events** |
| `deployment.verified` | the destination confirms the version is live | only when listed in **Events** |

Something that happened more than a day before the platform saw it (the history a first Sync imports) sends nothing.

## Configure

Every URL and the signing secret are `secret` options: the platform seals them at rest and never returns them, `GET /api/v1/plugins/notify/options` included. Leave a channel empty to skip it.

| Option | |
|---|---|
| Slack webhook URL | an [incoming webhook](https://api.slack.com/messaging/webhooks) of the channel |
| Discord webhook URL | channel settings → Integrations → Webhooks → Copy Webhook URL |
| Microsoft Teams webhook URL | a Teams workflow *Post to a channel when a webhook request is received*; the message is an Adaptive Card |
| Webhook URL | your HTTPS endpoint; it receives the event envelope as JSON |
| Webhook signing secret | the key of the body's HMAC-SHA256; required with a webhook URL |
| Events | comma-separated event kinds; empty sends the defaults above |
| Projects | comma-separated project slugs; empty sends every project |

Before saving a URL, check it from your machine (the URL is asked for, or read from `APX_NOTIFY_URL`, so it stays out of the shell history):

```bash
pip install apx-notify
action-platform notify test slack
APX_NOTIFY_SECRET=… action-platform notify test webhook --kind release.created
```

## Deliveries

Each event goes to each configured channel as its own job on the platform's queue, a few seconds after it happened. A channel that answers 408, 425, 429 or 5xx, or does not answer, is tried again with backoff (30 s, then 60 s, three attempts in all); any other answer fails the delivery at once. **Plugins → Notifications → Deliveries** (`GET /api/v1/plugins/notify/deliveries`) shows the organization's admins every delivery: event, channel, app, status, attempts, error.

## The webhook

```http
POST /your/endpoint
Content-Type: application/json
User-Agent: apx-notify
X-AP-Event: deployment.failed
X-AP-Delivery: 5b0c…            (the event's id, the same on every retry)
X-AP-Signature-256: sha256=9f2a…

{"actor": "ana", "app": "api", "at": "2026-11-24T20:00:00+00:00", "id": "5b0c…",
 "kind": "deployment.failed", "organization": "acme", "project": "shop",
 "payload": {"stage": "prod", "version": "1.2.0", "target": "app", "executor": "jenkins", "error": "…", …},
 "url": "https://platform.example.com/projects/…/deployments"}
```

Check the signature over the raw body before parsing it, and drop a repeated `X-AP-Delivery`:

```python
import hashlib, hmac

def valid(secret: bytes, body: bytes, header: str) -> bool:
    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)
```

The fields of every event and its payload: [writing a plugin → events](https://github.com/actionplatform/action-platform/blob/master/docs/contribute_plugins.md#events).

## Network

The platform's worker sends only over HTTPS and only to public addresses: a URL whose host resolves to a private, loopback or link-local address is refused, and redirects are not followed. A self-hosted platform that posts to an internal service sets `APX_NOTIFY_ALLOW_PRIVATE=1` on the worker; that also allows `http://`.

## Development

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check . && pytest
APX_NOTIFY_LIVE_SLACK_URL=https://hooks.slack.com/services/… pytest tests/live
```

`tests/fake.py` stands in for the services; `tests/live/` posts a sample to each `APX_NOTIFY_LIVE_<SLACK|DISCORD|TEAMS|WEBHOOK>_URL` that is set.

## License

Apache-2.0
