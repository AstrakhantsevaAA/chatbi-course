"""Load your Spotify listening data with dlt: DuckDB locally, the playground on dltHub.

Run `uv run python spotify_pipeline.py`. Plays load incrementally, because the API
keeps only your last 50; everything else is replaced with the current state.
"""

from datetime import datetime, timezone

import dlt
from dlt.sources.helpers.rest_client import RESTClient
from dlt.sources.helpers.rest_client.auth import OAuth2ClientCredentials
from dlt.sources.rest_api import rest_api_resources

from destinations import destination

BASE_URL = "https://api.spotify.com/v1/"
TOKEN_URL = "https://accounts.spotify.com/api/token"
DROP = {"images", "tracks", "copyrights", "available_markets"}


def clean(row):
    """Drop images and nested track lists, and lift track and album ids to the top."""
    if isinstance(row, list):
        return [clean(v) for v in row]
    if not isinstance(row, dict):
        return row
    row = {k: clean(v) for k, v in row.items() if k not in DROP}
    track = row.get("track") or row.get("item")
    if isinstance(track, dict):
        row["track_id"] = track.get("id")
    if isinstance(row.get("album"), dict):
        row["album_id"] = row["album"].get("id")
    return row


@dlt.source(name="spotify")
def spotify_source(client_id=dlt.secrets.value, client_secret=dlt.secrets.value,
                   refresh_token=dlt.secrets.value):
    """Plays, saved tracks and albums, playlists, profile, and top items."""
    auth = OAuth2ClientCredentials(
        access_token_url=TOKEN_URL, client_id=client_id, client_secret=client_secret,
        access_token_request_data={"grant_type": "refresh_token", "refresh_token": refresh_token},
    )
    yield from rest_api_resources({
        "client": {"base_url": BASE_URL, "auth": auth,
                   "paginator": {"type": "json_link", "next_url_path": "next"}},
        "resource_defaults": {
            "write_disposition": "replace",
            "endpoint": {"params": {"limit": 50}, "data_selector": "items"},
            "processing_steps": [{"map": clean}],
        },
        "resources": [
            {"name": "plays", "primary_key": "played_at", "write_disposition": "append",
             "endpoint": {"path": "me/player/recently-played", "incremental": {
                 "start_param": "after", "cursor_path": "played_at",
                 "initial_value": "2020-01-01T00:00:00Z",
                 "convert": lambda ts: int(datetime.fromisoformat(ts).timestamp() * 1000)}}},
            {"name": "saved_tracks", "endpoint": "me/tracks"},
            {"name": "saved_albums", "endpoint": "me/albums"},
            {"name": "playlists", "endpoint": "me/playlists"},
            {"name": "playlist_items", "include_from_parent": ["id"], "endpoint": {
                "path": "playlists/{resources.playlists.id}/items",
                "response_actions": [{"status_code": 403, "action": "ignore"}]}},
            {"name": "profile", "endpoint": {"path": "me", "params": {}, "data_selector": "$",
                                             "paginator": "single_page"}},
        ],
    })
    yield top_items(auth)


@dlt.resource(write_disposition="merge", primary_key=("snapshot_date", "item_type", "time_range", "id"))
def top_items(auth):
    """Snapshot today's top tracks and artists, with their rank, for all three time ranges."""
    client = RESTClient(base_url=BASE_URL, auth=auth)
    today = datetime.now(timezone.utc).date().isoformat()
    for item_type in ("tracks", "artists"):
        for time_range in ("short_term", "medium_term", "long_term"):
            items = client.get(f"me/top/{item_type}", params={"time_range": time_range, "limit": 50})
            for rank, item in enumerate(items.json()["items"], start=1):
                yield {**clean(item), "snapshot_date": today, "item_type": item_type,
                       "time_range": time_range, "rank": rank}


def main():
    pipeline = dlt.pipeline("spotify_pipeline", destination=destination(), dataset_name="spotify_raw")
    print(pipeline.run(spotify_source()))


if __name__ == "__main__":
    main()
