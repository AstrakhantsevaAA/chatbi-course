"""Test the ChatBI loop with a stub Claude client: no API key, no warehouse."""

import json
import unittest
from types import SimpleNamespace

import pandas as pd

import chatbi

GOOD_SQL = "SELECT COUNT(saved_album_sk) AS saved_albums FROM fact_saved_album LIMIT 1"


def plan_json(sql: str = GOOD_SQL, status: str = "answer", metrics=("saved_albums",)) -> str:
    return json.dumps({
        "status": status, "clarifying_question": "", "concepts": ["SavedAlbum"],
        "metrics": list(metrics), "group_by": [], "filters": [], "assumptions": [], "sql": sql,
    })


class StubClient:
    """Return queued replies and record every request."""

    def __init__(self, replies: list[str]) -> None:
        self.replies, self.requests = list(replies), []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        text = SimpleNamespace(type="text", text=self.replies.pop(0))
        return SimpleNamespace(stop_reason="end_turn", content=[text])


def runner(sql: str) -> pd.DataFrame:
    return pd.DataFrame([{"saved_albums": 11}])


class ChatbiTest(unittest.TestCase):
    def test_answers_with_gated_sql_and_fallback(self) -> None:
        client = StubClient([plan_json(), "You have **11** saved albums."])
        turn = chatbi.ask("How many albums have I saved?", [], client, runner)
        self.assertEqual(turn.status, "answered")
        self.assertIn("11", turn.answer)
        self.assertEqual(turn.sql, GOOD_SQL)
        first = client.requests[0]
        self.assertEqual(first["fallbacks"], "default")
        self.assertEqual(first["output_config"]["format"]["type"], "json_schema")

    def test_gate_rejection_gets_one_repair(self) -> None:
        bad = "SELECT * FROM saved_albums"
        client = StubClient([plan_json(bad), plan_json(), "11 saved albums."])
        turn = chatbi.ask("How many albums have I saved?", [], client, runner)
        self.assertEqual(turn.status, "answered")
        self.assertIn("rejected by the gate", client.requests[1]["messages"][0]["content"])

    def test_write_is_rejected_after_repair(self) -> None:
        delete = "DELETE FROM fact_play"
        client = StubClient([plan_json(delete), plan_json(delete)])
        turn = chatbi.ask("delete my old plays", [], client, runner)
        self.assertEqual(turn.status, "rejected")
        self.assertIn("read-only", turn.answer)

    def test_write_request_is_refused_without_sql(self) -> None:
        client = StubClient([plan_json("", status="write_request", metrics=())])
        turn = chatbi.ask("delete my old plays", [], client, runner)
        self.assertEqual(turn.status, "rejected")
        self.assertEqual(len(client.requests), 1)

    def test_out_of_scope_runs_no_sql(self) -> None:
        client = StubClient([plan_json("", status="out_of_scope", metrics=())])
        turn = chatbi.ask("What's the weather in Berlin?", [], client, runner)
        self.assertEqual(turn.status, "out_of_scope")
        self.assertEqual(len(client.requests), 1)

    def test_follow_up_sends_the_earlier_plan(self) -> None:
        earlier = chatbi.Turn("How many albums?", "answered", "11", plan={"metrics": ["saved_albums"]})
        client = StubClient([plan_json(), "11."])
        chatbi.ask("and which artist has the most?", [earlier], client, runner)
        self.assertIn("Earlier questions", client.requests[0]["messages"][0]["content"])


if __name__ == "__main__":
    unittest.main()
