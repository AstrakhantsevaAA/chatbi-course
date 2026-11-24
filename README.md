# chatbi-course

Reference solution for the dltHub Academy course **ChatBI on your warehouse**.

You load your own Spotify data with dlt into any destination, generate an
ontology with the dltHub AI Harness, and build an agent that answers
questions about your listening through a semantic layer.

> Work in progress. Modules are added as they are reproduced end to end.

| Module | Status | Files |
|---|---|---|
| 1. Load Spotify into your warehouse | ✅ real data, deployed | `get_refresh_token.py`, `spotify_pipeline.py` |
| 2. Generate the ontology with the AI Harness | ✅ real data, deployed | `.schema/listening_activity/`, `transformations/` |
| 3. Roles and metrics | ✅ 61 roles, 7 metrics verified | `course_skills/annotate-column-roles`, `course_skills/add-metrics` |
| 4. Report apps | ✅ deployed as dltHub data apps | `my_music_history.py` (years of library data), `listening_activity_cdm_dashboard.py` (recent listening) |
| 5. The answering agent | ✅ 10/10 headless Claude Code runs | `course_skills/answer-question`, `gate.py`, `.claude/settings.json` |
| 6. Deploy and a weekly agent | ✅ on dltHub | `__deployment__.py`, `listening_jobs.py`, `agents/forgotten_favorites/` |

## Quick start

You need [uv](https://docs.astral.sh/uv/), Spotify Premium, and a
[Spotify developer app](https://developer.spotify.com/dashboard) with the
redirect URI `http://127.0.0.1:8888/callback`.

```bash
uv sync
uv run dlthub ai toolkit install rest-api-pipeline
uv run dlthub ai toolkit install transformations
```

Put your app credentials in `.dlt/dev.secrets.toml` (local) and
`.dlt/prod.secrets.toml` (dltHub batch jobs). Keep them out of the
workspace-wide `secrets.toml`: that file also reaches the read-only `access`
profile used by the report app and the agent.

```toml
[sources.spotify]
client_id = "..."
client_secret = "..."
```

Then log in once and load:

```bash
uv run python get_refresh_token.py   # saves refresh_token to .dlt/secrets.toml; move it too
uv run python spotify_pipeline.py    # named destination "playground": DuckDB locally
SPOTIFY_DESTINATION=snowflake uv run python spotify_pipeline.py
```

## Tests

No Spotify account needed; the tests use a fake Spotify API.

```bash
uv run python -m unittest discover -s tests -t .
```

## Build the CDM

```bash
uv run python transformations/listening_activity_to_cdm.py
```

The ontology files in `.schema/listening_activity/` were generated with the
AI Harness `transformations` toolkit (`/annotate-sources` → `/create-ontology`
→ `/generate-cdm` → `/create-transformation`).

## Deploy to dltHub

```bash
uv run dlthub workspace connect chatbi-course --create --org-id <your org id>
uv run dlthub variable set AGENT__API_KEY --secret --profile access   # reads stdin
uv run dlthub variable set AGENT__MODEL --plain --profile access --value anthropic:claude-sonnet-5-5
uv run dlthub deploy
```

Jobs: `ingest` (every 3 hours) → `build_cdm` → the report app, and the
`forgotten_favorites` agent (Mondays 09:00 UTC), which returns a top 20 of
forgotten songs as its run result.
