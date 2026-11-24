"""Build the listening_activity CDM from the raw Spotify tables.

Run `uv run python transformations/listening_activity_to_cdm.py` after the pipeline.
Each CDM table is one SQL query below. The CDM loads through its own pipeline into its
own dataset, so raw and modelled tables never mix.
"""

import sys
from pathlib import Path

import dlt

# Running this file as a script puts transformations/ on the path, not the project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from destinations import destination  # noqa: E402

KEY = {"data_type": "text", "nullable": False}
DATE = {"data_type": "date", "nullable": True}

# Every table that embeds a track, with the column prefix of that track and a priority.
TRACK_TABLES = [("saved_tracks", "track__", 1), ("plays", "track__", 2),
                ("playlist_items", "item__", 3)]


def union_tracks(columns):
    """Union the same track columns from every table that embeds a track."""
    parts = [f"SELECT track_id, {', '.join(f'{p}{c} AS {c}' for c in columns)}, {n} AS priority "
             f"FROM {t}" for t, p, n in TRACK_TABLES]
    parts.append(f"SELECT id AS track_id, {', '.join(columns)}, 4 FROM top_items "
                 "WHERE item_type = 'tracks'")
    return " UNION ALL ".join(parts)


def best(sources, key):
    """Keep one row per key, from the source with the lowest priority number."""
    return f"""SELECT * FROM (SELECT u.*, ROW_NUMBER() OVER (PARTITION BY {key} ORDER BY priority) AS rn
               FROM ({sources}) u WHERE {key} IS NOT NULL) r WHERE rn = 1"""


TRACKS = union_tracks(["name", "duration_ms", "explicit", "external_ids__isrc", "album__id",
                       "external_urls__spotify"])
ALBUMS = ("SELECT album__id, album__name, album__album_type, album__release_date, "
          "album__release_date_precision, album__total_tracks, 0 AS priority FROM saved_albums "
          "UNION ALL SELECT album__id, album__name, album__album_type, album__release_date, "
          "album__release_date_precision, album__total_tracks, priority FROM ("
          + union_tracks(["album__id", "album__name", "album__album_type", "album__release_date",
                          "album__release_date_precision", "album__total_tracks"]) + ") t")
TRACK_ARTISTS = " UNION ALL ".join(
    [f"SELECT p.track_id, a.id AS artist_id, a.name AS artist_name, a.external_urls__spotify AS url, "
     f"a._dlt_list_idx AS artist_position FROM {t}__{prefix.rstrip('_')}__artists a "
     f"JOIN {t} p ON a._dlt_parent_id = p._dlt_id" for t, prefix, _ in TRACK_TABLES]
    + ["SELECT t.id, a.id, a.name, a.external_urls__spotify, a._dlt_list_idx FROM top_items__artists a "
       "JOIN top_items t ON a._dlt_parent_id = t._dlt_id WHERE t.item_type = 'tracks'"])

# table name -> (SQL, column hints). Dimensions first, then the bridge, then facts.
TABLES = {
    "dim_track": (f"""
        SELECT * FROM (
          SELECT MD5(track_id) AS track_sk, track_id AS source_id, 'spotify_pipeline' AS source_pipeline,
                 name AS track_name, duration_ms, explicit AS is_explicit, external_ids__isrc AS isrc,
                 COALESCE(MD5(album__id), 'UNKNOWN') AS album_sk, external_urls__spotify AS spotify_url
          FROM ({best(TRACKS, "track_id")}) t
          UNION ALL SELECT 'UNKNOWN', 'UNKNOWN', 'spotify_pipeline', 'Unknown track (local file)',
                           NULL, NULL, NULL, 'UNKNOWN', NULL) u""",
        {"track_sk": KEY, "album_sk": KEY, "source_pipeline": {"data_type": "text"}}),
    "dim_album": (f"""
        SELECT * FROM (
          SELECT MD5(album__id) AS album_sk, album__id AS source_id, 'spotify_pipeline' AS source_pipeline,
                 album__name AS album_name, album__album_type AS album_type,
                 album__release_date AS release_date, album__release_date_precision AS release_date_precision,
                 CAST(SUBSTRING(album__release_date, 1, 4) AS BIGINT) AS release_year,
                 album__total_tracks AS total_tracks
          FROM ({best(ALBUMS, "album__id")}) a
          UNION ALL SELECT 'UNKNOWN', 'UNKNOWN', 'spotify_pipeline', 'Unknown album',
                           NULL, NULL, NULL, NULL, NULL) u""",
        {"album_sk": KEY, "release_year": {"data_type": "bigint", "nullable": True}}),
    "dim_artist": (f"""
        SELECT * FROM (
          SELECT MD5(artist_id) AS artist_sk, artist_id AS source_id, 'spotify_pipeline' AS source_pipeline,
                 artist_name, url AS spotify_url
          FROM ({best(f'''SELECT id AS artist_id, name AS artist_name, external_urls__spotify AS url,
                                 0 AS priority FROM top_items WHERE item_type = 'artists'
                          UNION ALL SELECT artist_id, artist_name, url, 1 FROM ({TRACK_ARTISTS}) ta
                          UNION ALL SELECT id, name, external_urls__spotify, 2
                                    FROM saved_albums__album__artists''', "artist_id")}) a
          UNION ALL SELECT 'UNKNOWN', 'UNKNOWN', 'spotify_pipeline', 'Unknown artist', NULL) u""",
        {"artist_sk": KEY}),
    "dim_playlist": ("""
        SELECT MD5(id) AS playlist_sk, id AS source_id, 'spotify_pipeline' AS source_pipeline,
               name AS playlist_name, description, public AS is_public, collaborative AS is_collaborative,
               items__total AS items_total, owner__id AS owner_id, owner__display_name AS owner_display_name,
               owner__id = (SELECT MAX(id) FROM profile) AS is_mine
        FROM playlists""",
        {"playlist_sk": KEY, "is_mine": {"data_type": "bool", "nullable": True}}),
    "bridge_track_artist": (f"""
        SELECT DISTINCT MD5(track_id) AS track_sk, MD5(artist_id) AS artist_sk, artist_position
        FROM ({TRACK_ARTISTS}) ta WHERE track_id IS NOT NULL AND artist_id IS NOT NULL""",
        {"track_sk": KEY, "artist_sk": KEY, "artist_position": {"data_type": "bigint"}}),
    "fact_play": ("""
        SELECT MD5(CAST(played_at AS VARCHAR)) AS play_sk, played_at, CAST(played_at AS DATE) AS played_date,
               COALESCE(MD5(track_id), 'UNKNOWN') AS track_sk,
               COALESCE(MD5(track__album__id), 'UNKNOWN') AS album_sk,
               COALESCE(context__type, 'UNKNOWN') AS context_type, context__uri AS context_uri,
               track__duration_ms AS duration_ms
        FROM plays""",
        {"play_sk": KEY, "track_sk": KEY, "album_sk": KEY, "played_date": DATE,
         "context_type": {"data_type": "text"}, "context_uri": {"data_type": "text", "nullable": True}}),
    "fact_saved_track": ("""
        SELECT MD5(track_id) AS saved_track_sk, MD5(track_id) AS track_sk, added_at,
               CAST(added_at AS DATE) AS added_date
        FROM saved_tracks WHERE track_id IS NOT NULL""",
        {"saved_track_sk": KEY, "track_sk": KEY, "added_date": DATE}),
    "fact_playlist_item": ("""
        SELECT MD5(_playlists_id || '|' || COALESCE(track_id, _dlt_id) || '|'
                   || COALESCE(CAST(added_at AS VARCHAR), '')) AS playlist_item_sk,
               MD5(_playlists_id) AS playlist_sk, COALESCE(MD5(track_id), 'UNKNOWN') AS track_sk,
               added_at, CAST(added_at AS DATE) AS added_date, added_by__id AS added_by_id
        FROM playlist_items""",
        {"playlist_item_sk": KEY, "playlist_sk": KEY, "track_sk": KEY, "added_date": DATE}),
    "fact_top_item": ("""
        SELECT MD5(snapshot_date || '|' || item_type || '|' || time_range || '|' || id) AS top_item_sk,
               CAST(snapshot_date AS DATE) AS snapshot_date, item_type, time_range, rank,
               CASE WHEN item_type = 'tracks' THEN MD5(id) ELSE 'UNKNOWN' END AS track_sk,
               CASE WHEN item_type = 'artists' THEN MD5(id) ELSE 'UNKNOWN' END AS artist_sk
        FROM top_items""",
        {"top_item_sk": KEY, "track_sk": KEY, "artist_sk": KEY, "snapshot_date": DATE,
         "rank": {"data_type": "bigint"}}),
    "fact_saved_album": ("""
        SELECT MD5(s.album_id) AS saved_album_sk, MD5(s.album_id) AS album_sk,
               COALESCE(MD5(a.id), 'UNKNOWN') AS artist_sk, s.added_at, CAST(s.added_at AS DATE) AS added_date
        FROM saved_albums s
        LEFT JOIN saved_albums__album__artists a ON a._dlt_parent_id = s._dlt_id AND a._dlt_list_idx = 0
        WHERE s.album_id IS NOT NULL""",
        {"saved_album_sk": KEY, "album_sk": KEY, "artist_sk": KEY, "added_date": DATE}),
}


def cdm_table(name, sql, columns):
    """Turn one SQL query into a dlt transformation that replaces its table."""
    @dlt.hub.transformation(name=name, write_disposition="replace", columns=columns)
    def build(dataset: dlt.Dataset):
        yield dataset(sql)
    return build


@dlt.source
def listening_activity_to_cdm(dataset: dlt.Dataset):
    """Every CDM table, in dependency order."""
    for name, (sql, columns) in TABLES.items():
        yield cdm_table(name, sql, columns)(dataset)


def main():
    # Pass the destination and the dataset: a dltHub run has no local pipeline state.
    source = dlt.attach("spotify_pipeline", destination=destination(), dataset_name="spotify_raw")
    # On DuckDB the pipeline name sets the file name; it must differ from the dataset name.
    cdm = dlt.pipeline("listening_activity_cdm", destination=destination(), dataset_name="listening_activity")
    print(cdm.run(listening_activity_to_cdm(source.dataset())))


if __name__ == "__main__":
    main()
