import { t } from "@/lib/i18n";
import type { ConfirmOptions } from "@/components/ui/ConfirmDialog";

// 구독 해지 확인 대화 — 요금제 페이지(FREE 카드)와 설정 모달이 같은 문구를 쓴다.
// 해지는 즉시 종료가 아니라 해지 예약이라(약관 제12조 8항) 언제까지 쓸 수 있는지를 날짜로
// 못 박아 보여준다. 문구가 한 곳에 있어야 두 진입점이 서로 다른 말을 하지 않는다.
export function cancelSubscriptionPrompt(planName: string, endDateLabel: string): ConfirmOptions {
  return {
    title: t("플랜 취소"),
    message: t(
      "취소하면 정기 결제가 중단됩니다. {0}까지는 {1} 플랜을 계속 사용하실 수 있습니다.",
      endDateLabel,
      planName
    ),
    confirmLabel: t("플랜 취소"),
    // 제목이 '플랜 취소'라 기본 취소 버튼('취소')과 뜻이 겹친다 — 되돌아가는 쪽을 분명히 적는다.
    cancelLabel: t("계속 이용"),
    danger: true,
  };
}
