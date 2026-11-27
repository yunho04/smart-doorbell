"""시나리오 실행: 방문 1건의 전체 흐름을 단계별로 수행하고 검증한다."""
import time
from dataclasses import dataclass

from . import scenarios as sc
from . import vision
from .report import Abort

INACTIVITY_SECONDS = 10   # backend EventService.INACTIVITY_SECONDS


@dataclass
class Env:
    rep: object
    api: object
    pi: object
    llm: object
    db: object
    device_id: int
    visit_seconds: int


@dataclass
class Ctx:
    visit: sc.Visit
    event_id: int
    image: bytes
    mark: int              # CREATED 이후 MQTT 메시지 위치
    last_presence: float = 0.0


def body_of(response):
    try:
        return response.json()
    except ValueError:
        return None


def http_detail(response):
    return "HTTP %s" % response.status_code


def visit_until_ended(env, visit, label=""):
    """1~4단계: 센서 발행 → CREATED → 방문 중 감지 유지 → 무감지 후 ENDED."""
    rep, pi, api = env.rep, env.pi, env.api
    start = pi.mark()
    created, began = None, time.monotonic()
    while created is None and time.monotonic() - began < 10:
        pi.publish_presence()
        created = pi.wait_event("CREATED", 1.0, since=start)
    rep.require(label + "Pi1 센서 메시지 발행 → Spring CREATED 수신", created is not None,
                "eventId=%s (%.1fs)" % (created.data.get("eventId"), created.at - began) if created
                else "10초 내 CREATED 없음 (해당 device 에 진행 중인 DETECTED 이벤트가 있거나 백엔드 MQTT 미연결)")
    event_id = created.data["eventId"]
    rep.event(event_id)
    ctx = Ctx(visit, event_id, vision.make_test_image(event_id, visit.risk), start)
    env.llm.plan(event_id, visit.result(), ctx.image)

    detail = body_of(api.get_event(event_id)) or {}
    rep.check(label + "이벤트 생성 확인 (status=DETECTED, deviceId 일치)",
              detail.get("status") == "DETECTED" and detail.get("deviceId") == env.device_id,
              "status=%s deviceId=%s" % (detail.get("status"), detail.get("deviceId")))

    sent = 0
    for second in range(env.visit_seconds):
        time.sleep(1)
        pi.publish_presence()
        sent += 1
        if visit.live_response and second == env.visit_seconds // 2:
            live_response(env, ctx, label)
    ctx.last_presence = time.monotonic()
    extra = [m.data for m in pi.since(start) if m.topic == pi.event_topic and m is not created]
    rep.check(label + "방문 중 센서 감지 %d회 전송, 이벤트 유지 (추가 CREATED/ENDED 없음)" % sent, not extra,
              "예상 밖 메시지: %s" % extra if extra else "")

    ended = pi.wait_event("ENDED", INACTIVITY_SECONDS + 15, since=start, event_id=event_id)
    rep.require(label + "방문 종료 → Spring 종료 로직이 ENDED 발행", ended is not None,
                "마지막 감지 후 %.1fs" % (ended.at - ctx.last_presence) if ended else "ENDED 미수신")
    rep.check(label + "무감지 %d초 이후에만 종료" % INACTIVITY_SECONDS,
              ended.at - ctx.last_presence >= INACTIVITY_SECONDS - 1)
    return ctx


def live_response(env, ctx, label):
    """방문 중 LLM 실시간 응답: POST /response → Spring 이 doorbell/{id}/response 로 Pi1 에 전달."""
    code, text = ctx.visit.live_response
    mark = env.pi.mark()
    response = env.api.post_response(ctx.event_id, code, text)
    message = env.pi.wait_for(lambda m: m.topic == env.pi.response_topic and m.data.get("eventId") == ctx.event_id,
                              5, since=mark)
    expected = {"eventId": ctx.event_id, "responseCode": code, "responseText": text}
    env.rep.check(label + "방문 중 LLM 실시간 응답 저장(201) → Pi1 MQTT 수신", response.status_code == 201
                  and message is not None and message.data == expected,
                  "%s, MQTT=%s" % (http_detail(response), message.data if message else None))


def verify_completion(env, ctx, label=""):
    """5~8단계: finalize 수신 → 대표 이미지/최종 결과 전송 → 상세 조회 검증."""
    rep, api, llm, eid, visit = env.rep, env.api, env.llm, ctx.event_id, ctx.visit
    finalize = llm.wait_requests("finalize", eid, 10)
    rep.require(label + "가상 LLM 이 Spring finalize 요청 수신", bool(finalize),
                "POST /api/v1/events/%d/finalize" % eid if finalize else "10초 내 미수신 (백엔드 llm.base-url 확인)")
    rep.check(label + "finalize 본문 규격 {\"eventId\": %d}" % eid, finalize[0]["body"] == {"eventId": eid},
              "" if finalize[0]["body"] == {"eventId": eid} else "받은 본문: %s" % finalize[0]["body"])

    outcome = llm.wait_outcome(eid, 20)
    rep.require(label + "가상 Vision/LLM 전송 완료", outcome is not None and "error" not in outcome,
                "" if outcome and "error" not in outcome else str(outcome))
    image_body = body_of(outcome["image"]) or {}
    rep.check(label + "가상 Vision 대표 이미지 업로드 (201, SAVED)",
              outcome["image"].status_code == 201 and image_body.get("status") == "SAVED",
              "%s mediaId=%s" % (http_detail(outcome["image"]), image_body.get("mediaId")))
    result_body = body_of(outcome["result"]) or {}
    rep.require(label + "가상 LLM 최종 결과 전송 (200, COMPLETED)",
                outcome["result"].status_code == 200 and result_body.get("status") == "COMPLETED",
                "%s status=%s" % (http_detail(outcome["result"]), result_body.get("status")))
    rep.check(label + "finalize 는 이벤트당 1회만 호출", len(llm.requests_for("finalize", eid)) == 1)
    verify_detail(env, ctx, label)


def verify_detail(env, ctx, label="", suffix=""):
    rep, api, eid, expected = env.rep, env.api, ctx.event_id, ctx.visit.result()
    response = api.get_event(eid)
    detail = body_of(response) or {}
    rep.require(label + "이벤트 상세 조회" + suffix, response.status_code == 200 and detail.get("eventId") == eid,
                http_detail(response))
    fields = ("riskLevel", "summary", "responseCode", "responseText", "purpose", "conversationSummary")
    wrong = {k: detail.get(k) for k in fields if detail.get(k) != expected[k]}
    rep.check(label + "분석 결과 저장 (status=COMPLETED, riskLevel=%s 외 5개 필드)%s" % (expected["riskLevel"], suffix),
              detail.get("status") == "COMPLETED" and detail.get("endedAt") and not wrong,
              "status=%s 불일치=%s" % (detail.get("status"), wrong) if wrong or detail.get("status") != "COMPLETED" else "")
    conversation = detail.get("conversation") or []
    rep.check(label + "대화 기록 %d턴 저장 (순서·내용 일치)%s" % (len(expected["conversation"]), suffix),
              conversation == expected["conversation"],
              "" if conversation == expected["conversation"] else "받은 값: %s" % conversation)
    responses = detail.get("responses") or []
    rep.check(label + "응답 이력 행 수 = 대화 턴 수 (%d)%s" % (len(expected["conversation"]), suffix),
              len(responses) == len(expected["conversation"]), "responses=%d" % len(responses))
    rows = env.db.count("event_responses", eid)
    if rows is None:
        rep.skip(label + "DB event_responses 행 수 직접 확인" + suffix, "psql 사용 불가")
    else:
        rep.check(label + "DB event_responses 행 수 = %d%s" % (len(expected["conversation"]), suffix),
                  rows == len(expected["conversation"]), "rows=%d" % rows)

    image_url = "/api/v1/events/%d/image" % eid
    image = api.get_image(eid)
    rep.check(label + "대표 이미지 저장 (URL 노출, 다운로드 바이트 일치)" + suffix,
              detail.get("representativeImageUrl") == image_url and image.status_code == 200
              and image.content == ctx.image and image.headers.get("Content-Type", "").startswith("image/png"),
              "url=%s %s %d bytes" % (detail.get("representativeImageUrl"), http_detail(image), len(image.content)))
    listed = next((e for e in body_of(api.list_events()) or [] if e.get("eventId") == eid), None)
    rep.check(label + "대시보드 목록 API 에 노출 (GET /api/v1/events)" + suffix,
              listed is not None and listed.get("status") == "COMPLETED" and listed.get("riskLevel") == expected["riskLevel"]
              and listed.get("summary") == expected["summary"] and listed.get("representativeImageUrl") == image_url)
    return detail


def send_feedback(env, ctx, level, label="", nth=1):
    """9단계: 사용자 피드백 → DB 저장 + LLM 전달."""
    rep, api, eid = env.rep, env.api, ctx.event_id
    response = api.send_feedback(eid, level)
    rep.check(label + "사용자 피드백 전송 (%s)" % level,
              response.status_code == 200 and body_of(response) == {"eventId": eid, "accuracyLevel": level},
              http_detail(response))
    saved = (body_of(api.get_event(eid)) or {}).get("feedback")
    rows = env.db.count("feedbacks", eid)
    rep.check(label + "피드백 DB 저장 (상세 조회 feedback=%s%s)" % (level, "" if rows is None else ", feedbacks 행 1개"),
              saved == level and rows in (None, 1), "feedback=%s rows=%s" % (saved, rows))
    received = env.llm.wait_requests("feedback", eid, 5, count=nth)
    expected = {"eventId": eid, "summary": ctx.visit.result()["summary"], "accuracyLevel": level}
    rep.check(label + "피드백 LLM 전달 (eventId, summary, accuracyLevel)",
              len(received) == nth and received[-1]["body"] == expected,
              "" if received and received[-1]["body"] == expected else "받은 요청: %s" % [r["body"] for r in received])


def analyzing_check(env, ctx, label=""):
    status = (body_of(env.api.get_event(ctx.event_id)) or {}).get("status")
    env.rep.check(label + "ENDED 직후 상태 ANALYZING (결과 대기)", status == "ANALYZING", "status=%s" % status)


def single_visit(env, visit):
    ctx = visit_until_ended(env, visit)
    analyzing_check(env, ctx)
    verify_completion(env, ctx)
    send_feedback(env, ctx, visit.feedback)
    return ctx


def consecutive(env):
    first = visit_until_ended(env, sc.DELIVERY, "[방문1] ")
    # 방문1 의 결과가 아직 오지 않은(ANALYZING) 상태에서 곧바로 다음 방문자가 감지된다.
    second = visit_until_ended(env, sc.ACQUAINTANCE, "[방문2] ")
    env.rep.check("연속 방문 시 새 이벤트 생성 (eventId %d → %d)" % (first.event_id, second.event_id),
                  second.event_id > first.event_id)
    verify_completion(env, first, "[방문1] ")
    verify_completion(env, second, "[방문2] ")


def duplicate(env):
    ctx = visit_until_ended(env, sc.UNCLEAR)
    verify_completion(env, ctx)
    before = body_of(env.api.get_event(ctx.event_id)) or {}
    statuses = [env.api.post_result(ctx.event_id, ctx.visit.result()).status_code for _ in range(2)]
    env.rep.check("동일 결과 2회 재전송 수락 (200)", statuses == [200, 200], "HTTP %s" % statuses)
    after = verify_detail(env, ctx, suffix=" — 재전송 후")
    env.rep.check("재전송 후 종료 시각·상태 유지", after.get("endedAt") == before.get("endedAt")
                  and after.get("status") == "COMPLETED")
    send_feedback(env, ctx, "HIGH")
    send_feedback(env, ctx, "LOW", label="[수정] ", nth=2)


RUNNERS = {
    "delivery": lambda env: single_visit(env, sc.DELIVERY),
    "unclear": lambda env: single_visit(env, sc.UNCLEAR),
    "high-risk": lambda env: single_visit(env, sc.HIGH_RISK),
    "consecutive": consecutive,
    "duplicate": duplicate,
}


def run(env, keys):
    for index, key in enumerate(keys, 1):
        env.rep.section("시나리오 %d/%d: %s (%s)" % (index, len(keys), sc.SCENARIOS[key], key))
        try:
            RUNNERS[key](env)
        except Abort:
            print("  → 이 시나리오의 남은 단계를 건너뜁니다.", flush=True)
            # 남은 방문이 다음 시나리오에 섞이지 않도록 무감지 종료 시간만큼 기다린다.
            time.sleep(INACTIVITY_SECONDS + 2)
        except Exception as exc:
            env.rep.check("예기치 않은 오류", False, repr(exc))
            time.sleep(INACTIVITY_SECONDS + 2)
