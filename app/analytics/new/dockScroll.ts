// 하단에 고정된 되묻기 카드가 뜨는 동안, 초안 그래프가 카드에 가리지 않고 보이도록 얼마나 스크롤할지 계산한다.
// 좌표는 모두 화면(viewport) 기준이다. 양수 = 아래로 스크롤(내용이 위로 올라간다).

export interface DockScrollInput {
  /** 그래프(카드) 윗변·아랫변. */
  graphTop: number;
  graphBottom: number;
  /** 하단 고정 카드의 윗변. */
  cardTop: number;
  /** 상단 메뉴바 높이 — 그래프 윗변이 이 아래에 남아야 한다. */
  navHeight: number;
  margin?: number;
}

export function computeDockScrollDelta({ graphTop, graphBottom, cardTop, navHeight, margin = 16 }: DockScrollInput): number {
  const topLimit = navHeight + margin;
  // 그래프 아랫변이 카드 윗변 위에 오도록 올릴 양.
  const toClearCard = graphBottom - (cardTop - margin);
  if (toClearCard > 0) {
    // 그래프가 보이는 영역보다 크면 아랫부분을 포기하고 윗변이 메뉴바 밑에 닿는 데까지만 올린다.
    const roomAbove = graphTop - topLimit;
    return Math.max(0, Math.min(toClearCard, roomAbove));
  }
  // 이미 카드 위에 있다. 윗변이 메뉴바에 가려졌으면 내용을 내리되(음수), 아랫변이 카드 밑으로 가지 않는 만큼만.
  if (graphTop < topLimit) return -Math.min(topLimit - graphTop, -toClearCard);
  return 0;
}
