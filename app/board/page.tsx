import Board from "./Board";

export const metadata = {
  title: "자유게시판",
  description: "널스탁 사용자들이 백테스트·전략 연구에 관한 이야기를 나누는 자유게시판입니다.",
  robots: { index: false, follow: true },
};
export default function Page() { return <Board />; }
