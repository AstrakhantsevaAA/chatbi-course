"""Build the whole CDM from fake Spotify data, with no Spotify account."""

import tempfile
import unittest
from pathlib import Path

import dlt

import spotify_pipeline
from tests import fake_spotify
from transformations import listening_activity_to_cdm


class OfflineCdmTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        base = fake_spotify.start()
        spotify_pipeline.BASE_URL = f"{base}/v1/"
        spotify_pipeline.TOKEN_URL = f"{base}/token"
        tmp = tempfile.mkdtemp()
        destination = dlt.destinations.duckdb(str(Path(tmp) / "cdm.duckdb"))
        raw = dlt.pipeline("raw_test", destination=destination, dataset_name="spotify_raw", pipelines_dir=tmp)
        raw.run(spotify_pipeline.spotify_source("id", "secret", "refresh"))
        cdm = dlt.pipeline("cdm_test", destination=destination, dataset_name="listening_activity", pipelines_dir=tmp)
        cdm.run(listening_activity_to_cdm.listening_activity_to_cdm(raw.dataset()))
        cls.ds = cdm.dataset()

    def one(self, sql: str):
        return self.ds(sql).fetchone()[0]

    def test_saved_album_resolves_album_and_artist(self) -> None:
        self.assertEqual(self.one("SELECT COUNT(*) FROM fact_saved_album"), 1)
        name = self.one(
            "SELECT a.album_name FROM fact_saved_album f JOIN dim_album a ON f.album_sk = a.album_sk"
        )
        self.assertEqual(name, "Saved Album")
        artist = self.one(
            "SELECT a.artist_name FROM fact_saved_album f JOIN dim_artist a ON f.artist_sk = a.artist_sk"
        )
        self.assertEqual(artist, "Artist 1")

    def test_playlists_know_which_are_mine(self) -> None:
        mine = self.one("SELECT playlist_name FROM dim_playlist WHERE is_mine")
        self.assertEqual(mine, "Mine")
        self.assertEqual(self.one("SELECT COUNT(*) FROM dim_playlist WHERE NOT is_mine"), 1)

    def test_no_orphan_keys(self) -> None:
        for fact, key, dim in [
            ("fact_play", "track_sk", "dim_track"),
            ("fact_saved_album", "album_sk", "dim_album"),
            ("fact_saved_album", "artist_sk", "dim_artist"),
            ("bridge_track_artist", "artist_sk", "dim_artist"),
        ]:
            orphans = self.one(
                f"SELECT COUNT(*) FROM {fact} f LEFT JOIN {dim} d ON f.{key} = d.{key} WHERE d.{key} IS NULL"
            )
            self.assertEqual(orphans, 0, f"{fact}.{key}")


if __name__ == "__main__":
    unittest.main()
