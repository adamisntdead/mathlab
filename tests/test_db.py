from pathlib import Path

from mathlab.db import Blackboard


def test_blackboard_roundtrip(tmp_path: Path):
    db = Blackboard(tmp_path / "state.sqlite")
    db.create_task("T1", "Try", "Do maths", "EXPLORE", "a", 0.8, "test")
    assert db.open_tasks()[0]["id"] == "T1"
    db.update_task("T1", "DONE")
    assert db.open_tasks() == []
    db.create_claim("C1", "CONJECTURE", "x is irrational", "CONJECTURED", 0.7, "a", "test", ["n<=20"])
    assert db.claims()[0]["statement"] == "x is irrational"


def test_messages(tmp_path: Path):
    db = Blackboard(tmp_path / "state.sqlite")
    db.send_message("M1", "A1", "island:x", "question", "hello")
    msgs = db.unread_messages("A2", "x")
    assert len(msgs) == 1
    db.mark_messages_read("A2", ["M1"])
    assert db.unread_messages("A2", "x") == []
