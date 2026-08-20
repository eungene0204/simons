// 널스탁 로고 마크 — `/nullStock.png`을 SVG <image>로 얹고, 어두운 배경 위에서
// 원본 이미지의 검은 배경을 지우는 색 필터를 씌운다(내비게이션 로고와 동일한 방식).
//
// 필터 id는 인스턴스마다 달라야 한다 — 한 화면에 두 개가 놓이면 같은 id가 충돌한다.
export default function NullstockLogoMark({
  className = "h-[1.125rem] w-[1.375rem]",
  filterId = "nullstock-transparent-background",
}: {
  className?: string;
  filterId?: string;
}) {
  return (
    <svg
      aria-hidden="true"
      viewBox="510 215 400 330"
      className={`overflow-hidden ${className}`}
      data-testid="nullstock-logo-mark"
    >
      <defs>
        <filter
          id={filterId}
          x="-10%"
          y="-10%"
          width="120%"
          height="120%"
          colorInterpolationFilters="sRGB"
        >
          <feColorMatrix
            type="matrix"
            values="
              1 0 0 0 0
              0 1 0 0 0
              0 0 1 0 0
              0.2126 0.7152 0.0722 0 -0.2
            "
          />
          <feComponentTransfer>
            <feFuncA type="linear" slope="2.2" intercept="0" />
          </feComponentTransfer>
        </filter>
      </defs>
      <image
        href="/nullStock.png"
        width="1408"
        height="768"
        filter={`url(#${filterId})`}
      />
    </svg>
  );
}
