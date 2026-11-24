"""Pick the destination by profile: DuckDB locally, the dltHub playground deployed.

Local runs use the `dev` (or `tests`) profile and write DuckDB files. dltHub runs
batch jobs on `prod` and apps and agents on `access`, where the platform provides
the managed `playground` destination. Set SPOTIFY_DESTINATION to override both.
"""

import os

import dlt

LOCAL_PROFILES = ("dev", "tests")


def destination() -> str:
    """Return the destination name for the active profile."""
    override = os.getenv("SPOTIFY_DESTINATION")
    if override:
        return override
    profile = dlt.current.run_context().profile
    return "duckdb" if profile in LOCAL_PROFILES else "playground"


def cdm_dataset() -> dlt.Dataset:
    """Return the CDM dataset; attach needs both names, as a run has no state."""
    return dlt.attach(
        "listening_activity_cdm", destination=destination(), dataset_name="listening_activity"
    ).dataset()
