"""Run the Spotify pipeline against the fake API, with no Spotify account."""

import tempfile
import unittest
from pathlib import Path

import dlt

import spotify_pipeline
from tests import fake_spotify


class OfflinePipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        base = fake_spotify.start()
        spotify_pipeline.BASE_URL = f"{base}/v1/"
        spotify_pipeline.TOKEN_URL = f"{base}/token"
        self.tmp = tempfile.mkdtemp()
        self.pipeline = dlt.pipeline(
            pipeline_name="spotify_offline_test",
            destination=dlt.destinations.duckdb(str(Path(self.tmp) / "test.duckdb")),
            dataset_name="spotify_raw",
            pipelines_dir=self.tmp,
        )

    def run_source(self) -> None:
        self.pipeline.run(spotify_pipeline.spotify_source("id", "secret", "refresh"))

    def count(self, table: str) -> int:
        return self.pipeline.dataset()(f"SELECT COUNT(*) AS n FROM {table}").fetchone()[0]

    def test_loads_all_tables_and_appends_only_new_plays(self) -> None:
        self.run_source()
        self.assertEqual(self.count("plays"), 5)
        self.assertEqual(self.count("saved_tracks"), 6)
        self.assertEqual(self.count("playlists"), 2)
        self.assertEqual(self.count("playlist_items"), 3)
        self.assertEqual(self.count("top_items"), 3 * 5 + 3 * 4)
        self.assertEqual(self.count("saved_albums"), 1)
        self.assertEqual(self.count("profile"), 1)
        tables = self.pipeline.default_schema.data_table_names()
        self.assertNotIn("saved_albums__album__tracks__items", tables)
        self.assertIn("saved_albums__album__artists", tables)

        new_play = {"played_at": "2026-11-25T10:00:00.000Z", "track": fake_spotify.TRACKS[1],
                    "context": {"type": "album"}}
        fake_spotify.PLAYS.append(new_play)
        self.addCleanup(fake_spotify.PLAYS.remove, new_play)
        fake_spotify.FakeSpotify.requests_seen.clear()
        self.run_source()
        self.assertEqual(self.count("plays"), 6)
        after = [r for r in fake_spotify.FakeSpotify.requests_seen if "recently-played" in r]
        self.assertIn("after=1795514400000", after[0])

    def test_track_id_is_lifted_from_track_and_item(self) -> None:
        self.run_source()
        ds = self.pipeline.dataset()
        nulls = ds("SELECT COUNT(*) FROM playlist_items WHERE track_id IS NULL").fetchone()[0]
        self.assertEqual(nulls, 0)
        nulls = ds("SELECT COUNT(*) FROM plays WHERE track_id IS NULL").fetchone()[0]
        self.assertEqual(nulls, 0)


if __name__ == "__main__":
    unittest.main()
