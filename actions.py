"""Human-in-the-loop actions: an agent drafts, a person approves, then it runs.

Proposals live in the `agent_actions` dataset, so this works on any destination.
  uv run python actions.py draft proposal.json     # the agent writes a draft
  uv run python actions.py list                    # see drafts and their status
  uv run python actions.py approve ID [--remove TRACK_ID ...] | reject ID --note "..."
  uv run python actions.py run                     # create approved playlists
"""

import argparse
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import dlt
from dlt.sources.helpers.rest_client import RESTClient

import spotify_pipeline

DESTINATION = os.getenv("SPOTIFY_DESTINATION", "duckdb")


def actions_pipeline() -> dlt.Pipeline:
    """Return the pipeline that stores proposals."""
    return dlt.pipeline(pipeline_name="agent_actions", destination=DESTINATION, dataset_name="agent_actions")


def save(proposal: dict[str, Any]) -> None:
    """Insert or update one proposal by id."""
    row = {**proposal, "payload": json.dumps(proposal["payload"]), "updated_at": datetime.now(timezone.utc)}
    actions_pipeline().run([row], table_name="agent_proposals", write_disposition="merge", primary_key="id")


def load_all() -> list[dict[str, Any]]:
    """Return every proposal, newest first, with the payload parsed."""
    pipeline = actions_pipeline()
    if "agent_proposals" not in pipeline.default_schema.tables:
        return []
    rows = pipeline.dataset().agent_proposals.order_by("created_at", "desc").fetchall()
    columns = list(pipeline.dataset().agent_proposals.columns)
    proposals = [dict(zip(columns, row)) for row in rows]
    for p in proposals:
        p["payload"] = json.loads(p["payload"])
    return proposals


def get(proposal_id: str) -> dict[str, Any]:
    """Return one proposal by id, or stop with a clear message."""
    for p in load_all():
        if p["id"] == proposal_id:
            return {k: v for k, v in p.items() if not k.startswith("_dlt")}
    raise SystemExit(f"No proposal with id {proposal_id}")


def draft(path: Path) -> None:
    payload = json.loads(path.read_text())
    if not payload.get("name") or not payload.get("tracks"):
        raise SystemExit("A draft needs 'name' and a non-empty 'tracks' list")
    proposal = {
        "id": uuid.uuid4().hex[:8],
        "created_at": datetime.now(timezone.utc),
        "kind": "create_playlist",
        "status": "draft",
        "reviewer_note": "",
        "payload": payload,
    }
    save(proposal)
    print(f"Draft {proposal['id']} saved: {payload['name']} with {len(payload['tracks'])} tracks")


def list_proposals() -> None:
    for p in load_all():
        print(f"{p['id']}  {p['status']:9}  {p['payload']['name']}  ({len(p['payload']['tracks'])} tracks)")


def approve(proposal_id: str, remove: list[str]) -> None:
    proposal = get(proposal_id)
    if proposal["status"] != "draft":
        raise SystemExit(f"Only drafts can be approved; {proposal_id} is {proposal['status']}")
    proposal["payload"]["tracks"] = [t for t in proposal["payload"]["tracks"] if t["track_id"] not in remove]
    proposal["status"] = "approved"
    save(proposal)
    print(f"Approved {proposal_id} with {len(proposal['payload']['tracks'])} tracks")


def reject(proposal_id: str, note: str) -> None:
    proposal = get(proposal_id)
    proposal["status"], proposal["reviewer_note"] = "rejected", note
    save(proposal)
    print(f"Rejected {proposal_id}: {note}")


def default_auth() -> Any:
    """Build Spotify auth from the [sources.spotify] secrets."""
    secrets = dlt.secrets["sources.spotify"]
    return spotify_pipeline.spotify_auth(secrets["client_id"], secrets["client_secret"], secrets["refresh_token"])


def create_playlist(payload: dict[str, Any], auth: Any = None) -> str:
    """Create a private playlist with the payload's tracks and return its id."""
    auth = auth or default_auth()
    client = RESTClient(base_url=spotify_pipeline.BASE_URL, auth=auth)
    body = {"name": payload["name"], "public": False, "description": payload.get("description", "")}
    playlist_id = client.post("me/playlists", json=body).json()["id"]
    uris = [f"spotify:track:{t['track_id']}" for t in payload["tracks"]]
    for start in range(0, len(uris), 100):
        client.post(f"playlists/{playlist_id}/items", json={"uris": uris[start : start + 100]})
    return playlist_id


def run(auth: Any = None) -> None:
    approved = [p for p in load_all() if p["status"] == "approved"]
    if not approved:
        print("No approved proposals")
    for p in approved:
        proposal = {k: v for k, v in p.items() if not k.startswith("_dlt")}
        playlist_id = create_playlist(proposal["payload"], auth)
        proposal["status"], proposal["reviewer_note"] = "done", f"playlist {playlist_id}"
        save(proposal)
        print(f'Created playlist "{proposal["payload"]["name"]}" with {len(proposal["payload"]["tracks"])} tracks')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("draft").add_argument("file", type=Path)
    sub.add_parser("list")
    approve_cmd = sub.add_parser("approve")
    approve_cmd.add_argument("id")
    approve_cmd.add_argument("--remove", nargs="*", default=[])
    reject_cmd = sub.add_parser("reject")
    reject_cmd.add_argument("id")
    reject_cmd.add_argument("--note", required=True)
    sub.add_parser("run")
    args = parser.parse_args()
    if args.command == "draft":
        draft(args.file)
    elif args.command == "list":
        list_proposals()
    elif args.command == "approve":
        approve(args.id, args.remove)
    elif args.command == "reject":
        reject(args.id, args.note)
    else:
        run()


if __name__ == "__main__":
    main()
