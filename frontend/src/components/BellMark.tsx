/** 황동 초인종 버튼 모양의 로고 */
export function BellMark({ size = 22 }: { size?: number }) {
  return (
    <svg
      className="bell-mark"
      width={size}
      height={size}
      viewBox="0 0 32 32"
      aria-hidden="true"
      focusable="false"
    >
      <circle cx="16" cy="16" r="13" fill="none" stroke="currentColor" strokeWidth="2.5" />
      <circle cx="16" cy="16" r="6" fill="currentColor" />
    </svg>
  )
}
