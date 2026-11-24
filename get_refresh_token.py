"""Log in to Spotify once and save a refresh token to .dlt/dev.secrets.toml.

Put client_id and client_secret under [sources.spotify] in .dlt/dev.secrets.toml,
then run `uv run python get_refresh_token.py`. Log in, copy the address of the page
you land on (it does not load, which is fine), and paste it here.
"""

import urllib.parse
from pathlib import Path

import dlt
import requests
import tomlkit

SECRETS = Path(".dlt/dev.secrets.toml")
REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPES = "user-read-recently-played user-top-read user-library-read playlist-read-private playlist-read-collaborative"

client_id = dlt.secrets["sources.spotify.client_id"]
client_secret = dlt.secrets["sources.spotify.client_secret"]
query = {"client_id": client_id, "response_type": "code", "redirect_uri": REDIRECT_URI, "scope": SCOPES}
print("Open this URL and log in:\n" + "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(query))

landed_on = input("\nPaste the address of the page you landed on: ")
code = urllib.parse.parse_qs(urllib.parse.urlparse(landed_on).query)["code"][0]
response = requests.post(
    "https://accounts.spotify.com/api/token",
    auth=(client_id, client_secret),
    data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI},
    timeout=30,
)
response.raise_for_status()

secrets = tomlkit.parse(SECRETS.read_text()) if SECRETS.exists() else tomlkit.document()
secrets.setdefault("sources", {}).setdefault("spotify", {})["refresh_token"] = response.json()["refresh_token"]
SECRETS.write_text(tomlkit.dumps(secrets))
print(f"Refresh token saved to {SECRETS} under [sources.spotify]")
