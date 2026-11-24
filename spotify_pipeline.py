"""Load your Spotify listening data with dlt into any destination.

Run `uv run python spotify_pipeline.py`. It writes DuckDB locally and the
dltHub playground in a deployed job (see destinations.py); override it with
`SPOTIFY_DESTINATION=snowflake`. Plays load incrementally because the API
keeps only your last 50 plays.
"""

import os
from datetime import datetime, timezone
from typing import Any, Iterator

import dlt
from dlt.sources.helpers.rest_client import RESTClient
from dlt.sources.helpers.rest_client.auth import OAuth2ClientCredentials
from dlt.sources.helpers.rest_client.paginators import JSONLinkPaginator
from dlt.sources.rest_api import RESTAPIConfig, rest_api_resources

from destinations import destination

BASE_URL = "https://api.spotify.com/v1/"
TOKEN_URL = "https://accounts.spotify.com/api/token"
TIME_RANGES = ("short_term", "medium_term", "long_term")


def spotify_auth(client_id: str, client_secret: str, refresh_token: str) -> OAuth2ClientCredentials:
    """Return an auth object that swaps the refresh token for access tokens."""
    return OAuth2ClientCredentials(
        access_token_url=TOKEN_URL,
        client_id=client_id,
        client_secret=client_secret,
        access_token_request_data={"grant_type": "refresh_token", "refresh_token": refresh_token},
    )


def iso_to_unix_ms(value: str) -> int:
    """Convert an ISO timestamp into the unix milliseconds Spotify expects."""
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


NOISE_KEYS = {"images", "available_markets", "video_thumbnail", "primary_color"}


def strip_noise(value: Any) -> Any:
    """Drop image and market fields that only add tables to the schema."""
    if isinstance(value, dict):
        return {k: strip_noise(v) for k, v in value.items() if k not in NOISE_KEYS}
    if isinstance(value, list):
        return [strip_noise(v) for v in value]
    return value


def with_album_id(row: dict[str, Any]) -> dict[str, Any]:
    """Lift the album id and drop the album's full track list and copyrights."""
    album = row.get("album") or {}
    album.pop("tracks", None)
    album.pop("copyrights", None)
    row["album_id"] = album.get("id")
    return row


def with_track_id(row: dict[str, Any]) -> dict[str, Any]:
    """Lift the nested track id to the top level so it can be a key."""
    track = row.get("track") or row.get("item") or {}
    row["track_id"] = track.get("id")
    return row


@dlt.source(name="spotify")
def spotify_source(
    client_id: str = dlt.secrets.value,
    client_secret: str = dlt.secrets.value,
    refresh_token: str = dlt.secrets.value,
) -> Any:
    """Spotify profile, plays, saved tracks and albums, playlists, and top items."""
    auth = spotify_auth(client_id, client_secret, refresh_token)
    next_link = {"type": "json_link", "next_url_path": "next"}
    config: RESTAPIConfig = {
        "client": {"base_url": BASE_URL, "auth": auth, "paginator": next_link},
        "resource_defaults": {
            "write_disposition": "replace",
            "endpoint": {"params": {"limit": 50}, "data_selector": "items"},
        },
        "resources": [
            {
                "name": "plays",
                "primary_key": "played_at",
                "write_disposition": "append",
                "endpoint": {
                    "path": "me/player/recently-played",
                    "incremental": {
                        "start_param": "after",
                        "cursor_path": "played_at",
                        "initial_value": "2020-01-01T00:00:00Z",
                        "convert": iso_to_unix_ms,
                    },
                },
                "processing_steps": [{"map": strip_noise}, {"map": with_track_id}],
            },
            {
                "name": "saved_tracks",
                "endpoint": {"path": "me/tracks"},
                "processing_steps": [{"map": strip_noise}, {"map": with_track_id}],
            },
            {
                "name": "saved_albums",
                "endpoint": {"path": "me/albums"},
                "processing_steps": [{"map": strip_noise}, {"map": with_album_id}],
            },
            {
                "name": "profile",
                "primary_key": "id",
                "endpoint": {"path": "me", "params": {}, "data_selector": "$", "paginator": "single_page"},
            },
            {
                "name": "playlists",
                "endpoint": {"path": "me/playlists"},
                "processing_steps": [{"map": strip_noise}],
            },
            {
                "name": "playlist_items",
                "include_from_parent": ["id"],
                "endpoint": {
                    "path": "playlists/{resources.playlists.id}/items",
                    "response_actions": [
                        {"status_code": 403, "action": "ignore"},
                        {"status_code": 404, "action": "ignore"},
                    ],
                },
                "processing_steps": [{"map": strip_noise}, {"map": with_track_id}],
            },
        ],
    }
    yield from rest_api_resources(config)
    yield top_items(auth)


@dlt.resource(
    name="top_items",
    write_disposition="merge",
    primary_key=("snapshot_date", "item_type", "time_range", "id"),
)
def top_items(auth: OAuth2ClientCredentials) -> Iterator[dict[str, Any]]:
    """Snapshot today's top tracks and artists for all three time ranges."""
    client = RESTClient(base_url=BASE_URL, auth=auth, paginator=JSONLinkPaginator("next"))
    snapshot_date = datetime.now(timezone.utc).date().isoformat()
    for item_type in ("tracks", "artists"):
        for time_range in TIME_RANGES:
            response = client.get(f"me/top/{item_type}", params={"time_range": time_range, "limit": 50})
            for rank, item in enumerate(response.json()["items"], start=1):
                yield {
                    **strip_noise(item),
                    "snapshot_date": snapshot_date,
                    "item_type": item_type,
                    "time_range": time_range,
                    "rank": rank,
                }


def main() -> None:
    pipeline = dlt.pipeline(
        pipeline_name="spotify_pipeline",
        destination=destination(),
        dataset_name="spotify_raw",
    )
    load_info = pipeline.run(spotify_source())
    print(load_info)


if __name__ == "__main__":
    main()
