# Ontology: listening_activity

Source: `spotify_pipeline` (one pipeline, dataset `spotify_raw`).
Natural key strategy (all stitched entities): prefer whichever table has a value; include every entity.

```text
Playlist ──CONTAINS──▶ PlaylistItem ──OF_TRACK──┐
                                                ▼
Play ───────OF_TRACK──────────────────────▶  Track ──PERFORMED_BY──▶ Artist
SavedTrack ─OF_TRACK──────────────────────▶    │                       ▲
TopItemSnapshot ──RANKS (tracks)──────────▶    └──ON_ALBUM──▶ Album    │
TopItemSnapshot ──RANKS (artists)──────────────────────────────────────┘
```

## Track

A song or episode. No table holds tracks alone: track objects are embedded in every event table.

| Attribute | Type | Master source | Notes |
|---|---|---|---|
| track_id | text | saved_tracks.track_id | natural key |
| name | text | saved_tracks.track__name | |
| duration_ms | bigint | saved_tracks.track__duration_ms | |
| explicit | bool | saved_tracks.track__explicit | |
| is_local | bool | playlist_items.item__is_local | local files have no track_id |
| isrc | text | saved_tracks.track__external_ids__isrc | |
| album_id | text | saved_tracks.track__album__id | FK to Album |
| spotify_url | text | saved_tracks.track__external_urls__spotify | |

## Artist

| Attribute | Type | Master source | Notes |
|---|---|---|---|
| artist_id | text | top_items.id (item_type=artists) | natural key |
| name | text | top_items.name | |
| spotify_url | text | top_items.external_urls__spotify | |

## Album

| Attribute | Type | Master source | Notes |
|---|---|---|---|
| album_id | text | saved_tracks.track__album__id | natural key |
| name | text | saved_tracks.track__album__name | |
| album_type | text | saved_tracks.track__album__album_type | album, single, compilation |
| release_date | text | saved_tracks.track__album__release_date | mixed precision |
| release_date_precision | text | saved_tracks.track__album__release_date_precision | year, month, day |
| total_tracks | bigint | saved_tracks.track__album__total_tracks | |

## Playlist

| Attribute | Type | Source | Notes |
|---|---|---|---|
| playlist_id | text | playlists.id | natural key |
| name, description | text | playlists | |
| is_public, is_collaborative | bool | playlists.public, .collaborative | |
| items_total | bigint | playlists.items__total | |
| owner_id, owner_display_name | text | playlists.owner__* | |

## PlaylistItem

| Attribute | Type | Source | Notes |
|---|---|---|---|
| playlist_id | text | playlist_items._playlists_id | FK to Playlist |
| track_id | text | playlist_items.track_id | FK to Track |
| added_at | timestamp | playlist_items.added_at | |
| added_by_id | text | playlist_items.added_by__id | |

## Play

| Attribute | Type | Source | Notes |
|---|---|---|---|
| played_at | timestamp | plays.played_at | natural key |
| track_id | text | plays.track_id | FK to Track |
| context_type | text | plays.context__type | playlist, album, artist, or null |
| context_uri | text | plays.context__uri | |

## SavedTrack

| Attribute | Type | Source | Notes |
|---|---|---|---|
| track_id | text | saved_tracks.track_id | natural key, FK to Track |
| added_at | timestamp | saved_tracks.added_at | |

## TopItemSnapshot

| Attribute | Type | Source | Notes |
|---|---|---|---|
| snapshot_date | text | top_items.snapshot_date | key part |
| item_type | text | top_items.item_type | tracks or artists |
| time_range | text | top_items.time_range | short_term, medium_term, long_term |
| item_id | text | top_items.id | Track or Artist id |
| rank | bigint | top_items.rank | 1 = top |

## Relationships

| Edge | From → To | Via |
|---|---|---|
| PERFORMED_BY | Track → Artist | `*__track__artists._dlt_parent_id` = event row `_dlt_id` |
| ON_ALBUM | Track → Album | `album_id` |
| CONTAINS | Playlist → PlaylistItem | `playlist_items._playlists_id = playlists.id` |
| OF_TRACK | PlaylistItem, Play, SavedTrack → Track | `track_id` |
| RANKS | TopItemSnapshot → Track / Artist | `top_items.id` by `item_type` |

## Assumptions, exclusions, and gaps

- Album artists are excluded: track artists cover the use cases.
- dlt internal tables are excluded.
- **Gap — Genre:** Spotify returns no artist genres for Development Mode apps.
- **Gap — Play history:** only the last 50 plays exist in the API. Schedule the pipeline to build history.
