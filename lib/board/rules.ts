export const categories = ["공지", "정보", "질문", "건의", "자유"] as const;
export const reasons = ["광고·스팸", "음란물", "혐오·차별", "기타"] as const;

export class BoardError extends Error {
  constructor(message: string, public status = 400) { super(message); }
}

export function field(value: unknown, name: string, max: number, min = 1): string {
  if (typeof value !== "string" || value.trim().length < min || value.length > max) {
    throw new BoardError(`${name}: ${min}~${max}자 이내로 입력해 주세요.`);
  }
  return value.trim();
}

export function password(value: unknown): string {
  if (typeof value !== "string" || value.length < 4 || value.length > 64 || Buffer.byteLength(value) > 72) {
    throw new BoardError("비밀번호는 4~64자, UTF-8 72바이트 이내로 입력해 주세요.");
  }
  return value;
}

export function moderate(text: string): void {
  const normalized = text.normalize("NFKC").replace(/[\u200B-\u200D\uFEFF]/g, "");
  const links = normalized.match(/https?:\/\/|www\./gi) ?? [];
  if (links.length > 3 || /(.)\1{19}/u.test(normalized)) throw new BoardError("과도한 링크 또는 반복 문자는 게시할 수 없습니다.");
  if (/<\/?[a-z][^>]*>/i.test(normalized)) throw new BoardError("HTML 입력은 지원하지 않습니다.");
  const commercial = /(?:무료|수익|대출|카지노|도박|성인)[\s\S]{0,20}(?:가입|홍보|문의|입장|보장)/iu.test(normalized);
  const sexual = /(?:아동|미성년)[\s\S]{0,15}(?:음란|성매매|성착취)/u.test(normalized);
  const hate = /(?:여성|남성|장애인|외국인|인종)[\s\S]{0,15}(?:죽여|말살|박멸)/u.test(normalized);
  if (sexual || hate || commercial) throw new BoardError("운영 원칙에 위반되는 콘텐츠는 게시할 수 없습니다.");
}
