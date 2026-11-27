"""단계별 PASS / FAIL / SKIP 출력과 최종 요약."""
import sys

COLORS = {"PASS": "\033[32m", "FAIL": "\033[31m", "SKIP": "\033[33m"}


class Abort(Exception):
    """이후 단계를 진행할 수 없는 실패. 해당 시나리오만 중단한다."""


class Reporter:
    def __init__(self):
        self.tty = sys.stdout.isatty()
        self.scenario = "사전 점검"
        self.rows = []          # (scenario, status, name)
        self.event_ids = {}     # scenario -> [eventId]

    def section(self, title):
        self.scenario = title
        print("\n━━ %s" % title, flush=True)

    def _line(self, status, name, detail):
        self.rows.append((self.scenario, status, name))
        tag = "[%s]" % status
        if self.tty:
            tag = COLORS[status] + tag + "\033[0m"
        print("  %s %s%s" % (tag, name, "  — %s" % detail if detail else ""), flush=True)

    def check(self, name, ok, detail=""):
        self._line("PASS" if ok else "FAIL", name, detail)
        return bool(ok)

    def require(self, name, ok, detail=""):
        if not self.check(name, ok, detail):
            raise Abort(name)

    def skip(self, name, detail=""):
        self._line("SKIP", name, detail)

    def event(self, event_id):
        self.event_ids.setdefault(self.scenario, []).append(event_id)

    def summary(self):
        print("\n━━ 결과 요약")
        scenarios = []
        for scenario, _, _ in self.rows:
            if scenario not in scenarios:
                scenarios.append(scenario)
        for scenario in scenarios:
            statuses = [s for sc, s, _ in self.rows if sc == scenario]
            ids = ", ".join(str(i) for i in self.event_ids.get(scenario, [])) or "-"
            print("  %-4s %s  (PASS %d / FAIL %d / SKIP %d)  eventId: %s" % (
                "FAIL" if "FAIL" in statuses else "PASS", scenario,
                statuses.count("PASS"), statuses.count("FAIL"), statuses.count("SKIP"), ids))
        failed = [(sc, n) for sc, s, n in self.rows if s == "FAIL"]
        for scenario, name in failed:
            print("  실패: [%s] %s" % (scenario, name))
        total = [s for _, s, _ in self.rows]
        print("  합계: PASS %d / FAIL %d / SKIP %d" % (total.count("PASS"), total.count("FAIL"), total.count("SKIP")))
        return not failed
