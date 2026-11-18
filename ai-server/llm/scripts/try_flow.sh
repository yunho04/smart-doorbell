#!/usr/bin/env bash
# 방문 이벤트 1건을 명세서 순서대로 흉내 낸다.
# 먼저 LLM 서버(8001)와 가짜 Spring(8080)을 띄워 둘 것.
#   사용: ./scripts/try_flow.sh <eventId> <음성종류>
#   음성종류: delivery | visit | repair | suspicious | noise
set -e
AI=${AI_BASE_URL:-http://127.0.0.1:8001}
EID=${1:-15}
AUDIO=${2:-delivery}
PKG=$([ "$AUDIO" = delivery ] && echo true || echo false)
TMP=$(mktemp -d); printf 'fake' > "$TMP/$AUDIO.wav"

echo "== 0. AI 서버 상태";                curl -s $AI/health; echo
echo "== 1. Vision -> LLM (Vision 담당 코드와 같은 형식, 바뀔 때만 전송)"
REASONS=$([ "$AUDIO" = delivery ] && echo '["택배 상자 보임"]' || echo '[]')
for F in 1 2; do
  curl -s -H 'Content-Type: application/json' \
    -d "{\"event_id\":$EID,\"frame_no\":$F,\"person_detected\":true,\"person_count\":1,\"objects\":[{\"label\":\"person\",\"confidence\":0.9$F,\"bbox\":[0,0,10,10]}],\"processing_ms\":500,\"person_visible_sec\":$F,\"package_detected\":$PKG,\"face_covered\":false,\"weapon_labels\":[],\"vision_risk_level\":\"LOW\",\"vision_reasons\":$REASONS}" \
    $AI/vision/result; echo
  sleep 1
done
echo "== 2. Pi B -> AI 음성 (STT -> 대사 선택 -> Spring /response)"
curl -s -F file=@"$TMP/$AUDIO.wav" $AI/api/v1/events/$EID/audio; echo
echo "== 3. 보관 상태 확인";              curl -s $AI/api/v1/events/$EID/state; echo
echo "== 4. Spring -> AI finalize";       curl -s -H 'Content-Type: application/json' -d "{\"eventId\":$EID}" $AI/api/v1/events/$EID/finalize; echo
echo "   (AI가 분석 후 Spring /result로 전송 -> 가짜 Spring 터미널 확인)"
