"use client";

import { NodeResizer, useStore } from "@xyflow/react";

// 노드 모서리·가장자리를 끌어 크기를 바꾸는 손잡이 — 노드에 마우스를 올렸을 때만 보인다(globals.css .lab-flow).
// 내용은 폭에 비례해 확대·축소되고 높이는 내용을 따라가므로, 손잡이는 폭만 정한다(캔버스가 높이를 버린다).
export default function NodeSizer({ minWidth }: { minWidth: number }) {
  return <NodeResizer minWidth={minWidth} handleClassName="lab-resize-handle" lineClassName="lab-resize-line" />;
}

// 노드 폭과 내용 배율 — 사용자가 손잡이로 정한 폭 ÷ 기본 폭. 내용은 기본 폭으로 배치한 뒤 CSS zoom으로 키운다
// (zoom은 배치 크기에도 반영돼 잰 높이·연결점이 커진 내용을 따른다). NodeProps의 width는 잰 크기라 첫 렌더에 0이 오므로 쓰지 않는다.
export function useNodeScale(id: string, baseWidth: number): { width: number; zoom: number } {
  const userWidth = useStore((s) => s.nodeLookup.get(id)?.width);
  const width = userWidth ?? baseWidth;
  return { width, zoom: width / baseWidth };
}
