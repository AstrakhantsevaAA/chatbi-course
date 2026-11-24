# chatbi-course

Reference solution for the dltHub Academy course **ChatBI on your warehouse**.

You load your own Spotify data with dlt into any destination, generate an
ontology with the dltHub AI Harness, and build an agent that answers
questions about your listening through a semantic layer.

> Work in progress. Modules are added as they are reproduced end to end.

| Module | Status | Files |
|---|---|---|
| 1. Load Spotify into your warehouse | ✅ offline test passes | `get_refresh_token.py`, `spotify_pipeline.py` |
| 2. Generate the ontology with the AI Harness | ✅ on real data (DuckDB) | `.schema/listening_activity/`, `transformations/` |
| 3. Roles and metrics | ⏳ | `course_skills/` |
| 4. The answering agent | ⏳ | `course_skills/answer-question`, `gate.py` |
| 5. Agent-drafted actions and deploy | ⏳ | |

## Quick start

You need [uv](https://docs.astral.sh/uv/), Spotify Premium, and a
[Spotify developer app](https://developer.spotify.com/dashboard) with the
redirect URI `http://127.0.0.1:8888/callback`.

```bash
uv sync
uv run dlthub ai toolkit install rest-api-pipeline
uv run dlthub ai toolkit install transformations
```

Put your app credentials in `.dlt/secrets.toml`:

```toml
[sources.spotify]
client_id = "..."
client_secret = "..."
```

Then log in once and load:

```bash
uv run python get_refresh_token.py   # saves refresh_token to .dlt/secrets.toml
uv run python spotify_pipeline.py    # DuckDB by default
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
