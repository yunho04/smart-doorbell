#!/usr/bin/env bash
# 맥 기본 한국어 음성으로 자연스러운 테스트 음성을 만든다. (macOS 전용)
#   ./samples/make_samples_mac.sh
# 결과: samples/mac_*.wav (16kHz mono, Groq Whisper가 받는 형식)
#
# say로 wav를 바로 만들면 빈 파일(0초)이 나오는 경우가 있어서
# AIFF로 먼저 만든 뒤 afconvert로 wav 변환한다. 소리가 비면 다른 한국어 음성으로 다시 시도한다.
cd "$(dirname "$0")"
VOICES=()
# 고품질 음성(Premium·Enhanced·프리미엄·고품질)을 먼저 쓴다
while IFS= read -r v; do VOICES+=("$v"); done < <(say -v '?' | grep ko_KR | sed -E 's/ +ko_KR.*//' \
  | awk '{p = ($0 ~ /Premium|Enhanced|프리미엄|고품질/) ? 0 : 1; print p "\t" $0}' | sort -s -k1,1 | cut -f2-)
RATE=${RATE:-160}   # 말하기 속도 (낮을수록 천천히). 예: RATE=150 ./samples/make_samples_mac.sh
if [ ${#VOICES[@]} -eq 0 ]; then
  echo "한국어 음성이 없어요. 시스템 설정 > 손쉬운 사용 > 읽어 주기 > 시스템 음성 > 관리에서 한국어 Yuna를 내려받으세요."
  exit 1
fi
echo "찾은 한국어 음성: ${VOICES[*]}"

make() {
  local name="$1" text="$2" tmp="/tmp/doorbell_$1.aiff"
  for v in "${VOICES[@]}"; do
    rm -f "$tmp"
    say -v "$v" -r "$RATE" -o "$tmp" "[[slnc 300]]$text[[slnc 300]]" 2>/dev/null
    if [ -s "$tmp" ] && [ "$(stat -f%z "$tmp")" -gt 20000 ]; then
      afconvert -f WAVE -d LEI16@16000 -c 1 "$tmp" "mac_$name.wav" && rm -f "$tmp"
      printf "  mac_%-11s %5s초  [%s] \"%s\"\n" "$name.wav" \
        "$(afinfo "mac_$name.wav" | awk '/estimated duration/{printf "%.1f", $3}')" "$v" "$text"
      return 0
    fi
  done
  echo "  실패: $name (모든 한국어 음성이 빈 파일을 만들었어요)"
}

make delivery   "택배 왔습니다. 문 앞에 두고 갈게요."
make repair     "가스 점검 나왔습니다."
make visit      "안녕하세요. 옆집 사는 사람인데요."
make suspicious "집에 아무도 없어요? 알림 보내지 마세요."
make other      "교회에서 나왔는데요, 잠깐 이야기 좀 하실래요?"
echo "들어 보기: afplay samples/mac_delivery.wav"
