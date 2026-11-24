"""dltHub jobs: ingest Spotify every 3 hours, then rebuild the CDM.

Both run on the `prod` profile, which alone holds the Spotify secrets.
"""

from dlt.hub import run
from dlt.hub.run import trigger

import spotify_pipeline
from transformations import listening_activity_to_cdm


@run.pipeline("spotify_pipeline", trigger=trigger.every("3h"))
def ingest() -> None:
    spotify_pipeline.main()


@run.pipeline("listening_activity_cdm", trigger=ingest.success)
def build_cdm() -> None:
    listening_activity_to_cdm.main()
