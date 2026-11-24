# AGENTS.md

Rules an AI agent (or a new contributor) follows in this repository.

## What this is

An Action Platform plugin (`apx-notify`, slug `notify`) built from [apx-example](https://github.com/actionplatform/apx-example): the hosted platform hands it an organization's events (`Plugin.routes`, `Plugin.deliver`) and it posts them to Slack, Discord, Microsoft Teams or a signed webhook. The contract is apx-example's `SPEC.md` and the core's [writing a plugin](https://github.com/actionplatform/action-platform/blob/master/docs/contribute_plugins.md#events).

## Code

- Python 3.11+, `ruff check . && ruff format --check .`, `pytest` green before a commit.
- No comments inside function bodies; no test docstrings. Module docstrings say what the module is for.
- `register` and `routes` declare and decide only — no I/O. Network happens in `deliver`, through `Transport`.
- A refusal a retry cannot fix raises `Refused` (an `ActionPlatformError`); anything a retry may fix raises `Unavailable`. Error text names the channel and the status, never a URL or a secret — the organization's admins read it.
- Every webhook URL is a `secret` option. Nothing outside `transport.guard` decides which addresses the worker may reach.
- One ABC per responsibility (`abc.py`: `Channel`, `Transport`); `tests/fake.py` answers like the real services; `tests/live/` against real webhooks, skipped without them.
- `needs` lists every host and environment variable the plugin touches.

## Commits and branches

[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/): `type(scope): description`; one commit per concern; stage files explicitly. Git-flow: `<kind>/<issue>-<slug>` from `master`, kinds `feature bugfix hotfix release chore docs refactor test ci perf`; never commit on `master`. One pull request per issue.

## Release

`action-platform release <level>`; publishing the GitHub release runs `python-publish-pypi.yml` (PyPI trusted publishing, environment `pypi`); then a PR to `plugins-index` with the new `latest`, and a dependency bump in the platform's API image.
