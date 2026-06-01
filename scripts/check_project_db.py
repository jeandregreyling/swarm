#!/usr/bin/env python3
from __future__ import annotations

import sqlite3

DBS = [
    r"\\wsl$\Ubuntu\mnt\wsl\PHYSICALDRIVE0p1\home\seven\swarm\swarm_memory.db",
    r"\\wsl$\Ubuntu\mnt\wsl\PHYSICALDRIVE0p1\home\seven\swarm\swarm_memory.db.recovered",
    r"\\wsl$\Ubuntu\mnt\wsl\PHYSICALDRIVE0p1\home\seven\swarm\swarm_memory.db.backup.20260422-141708.pre-shell-noise-cleanup",
]

for db in DBS:
    try:
        con = sqlite3.connect(db)
        cur = con.cursor()
        has_projects = cur.execute(
            "select count(*) from sqlite_master where type='table' and name='projects'"
        ).fetchone()[0]
        if not has_projects:
            print(f"{db} -> no projects table")
            continue
        found = cur.execute(
            "select count(*) from projects where project_id='P-00221285D1'"
        ).fetchone()[0]
        print(f"{db} -> has_project={found}")
    except Exception as e:
        print(f"{db} -> error={e}")
