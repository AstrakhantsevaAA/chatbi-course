"""A tiny fake Spotify Web API for offline tests of the pipeline."""

import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

def _url(kind: str, key: str) -> dict:
    return {"spotify": f"https://open.spotify.com/{kind}/{key}"}


def _artist(i: int) -> dict:
    return {"id": f"ar{i}", "name": f"Artist {i}", "type": "artist", "external_urls": _url("artist", f"ar{i}")}


TRACKS = [
    {"id": f"t{i}", "name": f"Track {i}", "duration_ms": 180000 + i * 1000, "explicit": False,
     "is_local": False, "external_ids": {"isrc": f"ISRC{i}"}, "external_urls": _url("track", f"t{i}"),
     "album": {"id": f"al{i % 3}", "name": f"Album {i % 3}", "album_type": "album",
               "release_date": "2020-01-01", "release_date_precision": "day", "total_tracks": 10,
               "artists": [_artist(i % 4)]},
     "artists": [_artist(i % 4)]}
    for i in range(1, 9)
]
PLAYS = [
    {"played_at": f"2026-11-2{d}T10:00:00.000Z", "track": TRACKS[d], "context": {"type": "playlist", "uri": "spotify:playlist:pl_mine"}}
    for d in range(0, 5)
]


class FakeSpotify(BaseHTTPRequestHandler):
    """Serve canned Spotify responses and record the query strings it sees."""

    requests_seen: list[str] = []

    def _send(self, status: int, body: Any) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        self._send(200, {"access_token": "fake", "expires_in": 3600})

    def do_GET(self) -> None:
        url = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(url.query)
        FakeSpotify.requests_seen.append(self.path)
        path = url.path.removeprefix("/v1/")
        if path == "me/player/recently-played":
            after = int(query.get("after", ["0"])[0])
            items = [p for p in PLAYS if _ms(p["played_at"]) > after]
            self._send(200, {"items": items, "next": None})
        elif path == "me/tracks":
            self._send(200, {"items": [{"added_at": "2025-06-01T00:00:00Z", "track": t} for t in TRACKS[:6]],
                             "next": None})
        elif path == "me/albums":
            album = {"id": "al9", "name": "Saved Album", "album_type": "album", "release_date": "2019-05-01",
                     "release_date_precision": "day", "total_tracks": 10,
                     "artists": [_artist(1)],
                     "tracks": {"items": [{"id": "x"}]}, "copyrights": [{"text": "c"}]}
            self._send(200, {"items": [{"added_at": "2024-02-01T00:00:00Z", "album": album}], "next": None})
        elif path == "me":
            self._send(200, {"id": "me_user", "display_name": "Me", "type": "user"})
        elif path == "me/playlists":
            self._send(200, {"items": [{"id": "pl_mine", "name": "Mine", "public": False, "collaborative": False, "owner": {"id": "me_user", "display_name": "Me"}, "description": "", "items": {"total": 3}},
                                       {"id": "pl_other", "name": "Other", "public": True, "collaborative": False, "owner": {"id": "someone", "display_name": "Someone"}, "description": "", "items": {"total": 9}}],
                             "next": None})
        elif path == "playlists/pl_mine/items":
            self._send(200, {"items": [{"added_at": "2026-01-0{}T00:00:00Z".format(i), "item": TRACKS[i], "added_by": {"id": "me_user"}, "is_local": False}
                                       for i in range(1, 4)], "next": None})
        elif path == "playlists/pl_other/items":
            self._send(403, {"error": {"status": 403, "message": "Forbidden"}})
        elif path.startswith("me/top/"):
            kind = path.removeprefix("me/top/")
            items = TRACKS[:5] if kind == "tracks" else [
                _artist(i) for i in range(4)]
            self._send(200, {"items": items, "next": None})
        else:
            self._send(404, {"error": {"status": 404, "message": "Not found"}})

    def log_message(self, *args: object) -> None:
        pass


def _ms(iso: str) -> int:
    from datetime import datetime

    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def start() -> str:
    """Start the fake server on a free port and return its base URL."""
    server = HTTPServer(("127.0.0.1", 0), FakeSpotify)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}"
