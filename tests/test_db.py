# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

import sqlite3

from twittermcp.core import db


def test_schema_version():
    with db.connect() as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION


def test_init_is_idempotent_and_keeps_data():
    db.save_image_note("1", "0:photo", "m", "a cat")
    db.init_db()
    assert db.get_image_note("1", "0:photo", "m") == "a cat"
    assert not list(db.DB_PATH.parent.glob("*-backup-*"))


def test_upgrade_backs_up_first(monkeypatch):
    # pretend the current file is version 1 and a version 2 step exists
    monkeypatch.setattr(db, "SCHEMA_VERSION", 2)
    monkeypatch.setitem(db.MIGRATIONS, 2, lambda con: con.execute("CREATE TABLE extra (x)"))
    db.init_db()
    assert len(list(db.DB_PATH.parent.glob("test-backup-v1-*.db"))) == 1
    with sqlite3.connect(db.DB_PATH) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 2
        con.execute("SELECT x FROM extra")
