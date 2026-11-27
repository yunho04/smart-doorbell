# Frontend

Smart Doorbell MVP v2 사용자용 Web Dashboard입니다. (React + TypeScript + Vite)

실행 방법, 환경변수, 연동 API는 저장소 루트의 [README.md](../README.md)를 참고하세요.

## 화면

| 주소 | 내용 |
| --- | --- |
| `/login` | 공용 비밀번호 입력 |
| `/events` | 방문 Event 목록 (3초마다 자동 갱신) |
| `/events/:eventId` | 대표사진, 위험도, 상황 요약, AI 응대 기록, 정확도 피드백 |

## 구조

```text
src/
├── api/          REST 호출 (client.ts 가 credentials: 'include' 와 오류 처리를 담당)
├── auth/         로그인 상태 (AuthProvider, useAuth)
├── components/   ProtectedRoute, AppLayout, RiskBadge, StatusLabel, EventImage, FeedbackPanel
├── hooks/        usePolling (자동 새로고침, unmount 시 정리)
├── pages/        LoginPage, EventListPage, EventDetailPage
├── types/        API 응답 타입
├── utils/        시간 표시, 상태·위험도 문구
└── styles.css    전체 스타일
```
