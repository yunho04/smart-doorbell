"""(선택) psql 로 행 수를 직접 확인한다. SELECT 만 실행하며, psql 이 없거나 접속이 안 되면 None(SKIP)."""
import os
import re
import shutil
import subprocess

from .settings import resolve

TABLES = ("event_responses", "feedbacks", "media_files")


class Db:
    def __init__(self, props):
        match = re.match(r"jdbc:postgresql://([^:/]+)(?::(\d+))?/([^?]+)", resolve(props.get("spring.datasource.url")))
        self.args = None
        if match and shutil.which("psql"):
            self.args = ["psql", "-h", match.group(1), "-p", match.group(2) or "5432", "-d", match.group(3),
                         "-U", resolve(props.get("spring.datasource.username")), "-w", "-Atc"]
            self.env = dict(os.environ, PGPASSWORD=resolve(props.get("spring.datasource.password")))

    def count(self, table, event_id):
        if self.args is None or table not in TABLES:
            return None
        try:
            done = subprocess.run(self.args + ["select count(*) from %s where event_id = %d" % (table, int(event_id))],
                                  capture_output=True, text=True, env=self.env, timeout=10)
            return int(done.stdout.strip()) if done.returncode == 0 else None
        except (OSError, ValueError, subprocess.SubprocessError):
            return None
