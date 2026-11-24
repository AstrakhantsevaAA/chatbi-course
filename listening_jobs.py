"""dltHub jobs: ingest, build the CDM, and act on approved playlist drafts.

Batch jobs run on the `prod` profile, which alone holds the Spotify secrets.
Approve a draft from the web UI or CLI by running `review_proposal` with the
config keys `proposal_id`, `decision` (approve or reject), and optional
`remove` (comma-separated track ids) or `note`.
"""

import dlt
from dlt.hub import run
from dlt.hub.run import trigger

import actions
import spotify_pipeline
from transformations import listening_activity_to_cdm


@run.pipeline("spotify_pipeline", trigger=trigger.every("3h"))
def ingest() -> None:
    spotify_pipeline.main()


@run.pipeline("listening_activity_cdm", trigger=ingest.success)
def build_cdm() -> None:
    listening_activity_to_cdm.main()


@run.job
def review_proposal(
    proposal_id: str = dlt.config.value,
    decision: str = dlt.config.value,
    remove: str = "",
    note: str = "",
) -> None:
    """Approve or reject one playlist draft."""
    if decision == "approve":
        actions.approve(proposal_id, [t.strip() for t in remove.split(",") if t.strip()])
    elif decision == "reject":
        actions.reject(proposal_id, note or "rejected in review")
    else:
        raise ValueError(f"decision must be 'approve' or 'reject', got {decision!r}")


@run.job(trigger=review_proposal.success)
def run_approved_actions() -> None:
    """Create the playlists of every approved draft."""
    actions.run()
