"""Draft, approve, and run a playlist proposal against the fake Spotify API."""

import json
import tempfile
import unittest
from pathlib import Path

import dlt

import actions
import spotify_pipeline
from tests import fake_spotify


class OfflineActionsTest(unittest.TestCase):
    def setUp(self) -> None:
        base = fake_spotify.start()
        spotify_pipeline.BASE_URL = f"{base}/v1/"
        spotify_pipeline.TOKEN_URL = f"{base}/token"
        self.tmp = Path(tempfile.mkdtemp())
        db = str(self.tmp / "actions.duckdb")
        actions.actions_pipeline = lambda: dlt.pipeline(
            pipeline_name="agent_actions_test", destination=dlt.destinations.duckdb(db),
            dataset_name="agent_actions", pipelines_dir=str(self.tmp),
        )
        self.auth = spotify_pipeline.spotify_auth("id", "secret", "refresh")

    def test_draft_approve_run(self) -> None:
        draft = self.tmp / "draft.json"
        tracks = [{"track_id": f"t{i}", "reason": "saved, not played"} for i in range(1, 4)]
        draft.write_text(json.dumps({"name": "Forgotten favorites", "tracks": tracks}))
        actions.draft(draft)
        [proposal] = actions.load_all()
        self.assertEqual(proposal["status"], "draft")

        actions.approve(proposal["id"], remove=["t2"])
        actions.run(self.auth)
        [done] = actions.load_all()
        self.assertEqual(done["status"], "done")
        self.assertEqual(done["reviewer_note"], "playlist new_pl")
        items = [body for path, body in fake_spotify.FakeSpotify.posted if path == "playlists/new_pl/items"]
        self.assertEqual(items[-1]["uris"], ["spotify:track:t1", "spotify:track:t3"])

    def test_rejected_draft_never_runs(self) -> None:
        draft = self.tmp / "draft.json"
        draft.write_text(json.dumps({"name": "Nope", "tracks": [{"track_id": "t1"}]}))
        actions.draft(draft)
        [proposal] = actions.load_all()
        actions.reject(proposal["id"], note="not this week")
        fake_spotify.FakeSpotify.posted.clear()
        actions.run(self.auth)
        self.assertEqual(fake_spotify.FakeSpotify.posted, [])


if __name__ == "__main__":
    unittest.main()
