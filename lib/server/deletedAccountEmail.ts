// 본인 삭제 계정의 이메일 해제.
//
// 계정 삭제는 soft delete(status=DELETED)라 행이 남는다. email이 @unique이므로 원래 주소를
// 그대로 두면 같은 이메일로 다시 가입할 수 없다. 본인 삭제 시 이메일을 아래 형식으로 바꿔
// 원래 주소를 비우고, 원래 주소는 접미사로 남겨 기록 추적을 유지한다.
// 관리자 삭제(제재)는 이 함수를 쓰지 않는다 — 원래 주소를 계속 점유해 재가입을 막는다.

const RELEASED_PREFIX = "deleted-";

export function releasedDeletedEmail(userId: number, email: string): string {
  if (isReleasedDeletedEmail(email)) return email;
  return `${RELEASED_PREFIX}${userId}:${email}`;
}

export function isReleasedDeletedEmail(email: string): boolean {
  return /^deleted-\d+:/.test(email);
}
