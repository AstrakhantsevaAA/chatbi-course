"""Log in to Spotify once and save a refresh token to .dlt/dev.secrets.toml.

Run `uv run python get_refresh_token.py` after you put client_id and
client_secret under [sources.spotify] in .dlt/dev.secrets.toml. It opens the
Spotify login page, catches the redirect on 127.0.0.1:8888, and writes the
refresh token. The token value is never printed.
"""

import base64
import secrets
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import dlt
import requests
import tomlkit

REDIRECT_URI = "http://127.0.0.1:8888/callback"
SECRETS_PATH = Path(".dlt/dev.secrets.toml")
SCOPES = [
    "user-read-recently-played",
    "user-top-read",
    "user-library-read",
    "playlist-read-private",
    "playlist-read-collaborative",
]


class CallbackHandler(BaseHTTPRequestHandler):
    """Capture the authorization code from the Spotify redirect."""

    code: str | None = None
    state: str | None = None
    error: str | None = None

    def do_GET(self) -> None:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        CallbackHandler.code = query.get("code", [None])[0]
        CallbackHandler.state = query.get("state", [None])[0]
        CallbackHandler.error = query.get("error", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Done. You can close this tab and go back to the terminal.")

    def log_message(self, *args: object) -> None:
        pass


def exchange_code(client_id: str, client_secret: str, code: str) -> str:
    """Exchange an authorization code for a refresh token."""
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    response = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={"Authorization": f"Basic {basic}"},
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["refresh_token"]


def save_refresh_token(token: str) -> None:
    """Write the refresh token under [sources.spotify] and keep other keys."""
    doc = tomlkit.parse(SECRETS_PATH.read_text()) if SECRETS_PATH.exists() else tomlkit.document()
    sources = doc.setdefault("sources", tomlkit.table())
    spotify = sources.setdefault("spotify", tomlkit.table())
    spotify["refresh_token"] = token
    SECRETS_PATH.write_text(tomlkit.dumps(doc))


def main() -> None:
    client_id = dlt.secrets["sources.spotify.client_id"]
    client_secret = dlt.secrets["sources.spotify.client_secret"]
    state = secrets.token_urlsafe(16)
    url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": " ".join(SCOPES),
            "state": state,
        }
    )
    print(f"Opening the Spotify login page. If it does not open, visit:\n{url}\n")
    webbrowser.open(url)
    server = HTTPServer(("127.0.0.1", 8888), CallbackHandler)
    while CallbackHandler.code is None and CallbackHandler.error is None:
        server.handle_request()
    if CallbackHandler.error:
        raise SystemExit(f"Spotify returned an error: {CallbackHandler.error}")
    if CallbackHandler.state != state:
        raise SystemExit("State mismatch: the redirect did not come from this login.")
    save_refresh_token(exchange_code(client_id, client_secret, CallbackHandler.code))
    print(f"Refresh token saved to {SECRETS_PATH} under [sources.spotify]")


if __name__ == "__main__":
    main()
