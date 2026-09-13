/** @type {import('tailwindcss').Config} */
const colors = require('tailwindcss/colors')

module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      // 본문 폰트는 Arial로 되돌린다(2026-07-25). Inter/Outfit 웹폰트를 스택
      // 앞에 세웠더니 수치 자형이 눈에 띄게 달라져 이전 렌더로 복귀시켰다.
      // 한글 글리프는 Arial에 없으므로 시스템 한글 폰트로 폴백된다 —
      // 폴백 순서(Apple SD Gothic Neo → 맑은 고딕)는 브라우저 기본 동작과 같다.
      //
      // font-inter·font-outfit은 22개 파일이 쓰고 있다. 스택에서 웹폰트를 빼도
      // 클래스 정의는 남겨둔다 — fontFamily 확장을 통째로 지우면 정의되지 않은
      // 죽은 클래스로 되돌아가 어떤 폰트가 적용되는지 코드에서 읽을 수 없게 된다.
      fontFamily: {
        sans: [
          'Arial',
          'Helvetica',
          'Apple SD Gothic Neo',
          'Malgun Gothic',
          'Pretendard Variable',
          'Pretendard',
          'sans-serif',
        ],
        inter: [
          'Arial',
          'Helvetica',
          'Apple SD Gothic Neo',
          'Malgun Gothic',
          'Pretendard Variable',
          'Pretendard',
          'sans-serif',
        ],
        outfit: [
          'Arial',
          'Helvetica',
          'Apple SD Gothic Neo',
          'Malgun Gothic',
          'Pretendard Variable',
          'Pretendard',
          'sans-serif',
        ],
        // 큰 제목(display) 전용 — app/layout.tsx가 next/font로 --font-serif를 채운다.
        // 본문·수치에는 쓰지 않는다(수치 자형이 바뀐다). 2026-09-13 전단지 테마.
        serif: [
          'var(--font-serif)',
          'Noto Serif KR',
          'Apple Myungjo',
          'Georgia',
          'serif',
        ],
      },
      colors: {
        background: 'var(--background)',
        foreground: 'var(--foreground)',
        // 따뜻한 다크 팔레트(2026-09-13): text-white/bg-white는 순백이 아니라 크림(#f4f1ea)이고,
        // gray-*는 푸른 기가 도는 기본 gray 대신 갈색빛 stone 스케일이다. 배경 #141413과
        // 같은 온도를 맞추기 위한 것으로, 컴포넌트의 gray-* 클래스는 그대로 두면 된다.
        white: '#f4f1ea',
        gray: colors.stone,
        blue: {
          500: 'rgb(59, 134, 247)',
        },
        'brand-blue': 'rgb(59, 134, 247)',
        'main-blue': 'rgb(55, 122, 244)',
        'main-red': 'rgb(239, 68, 68)',
        'main-green': 'rgb(34, 197, 94)',
        tab_black: '#262522',
      },
      animation: {
        shimmer: 'shimmer 2s infinite',
        fadeIn: 'fadeIn 0.35s ease-in-out',
      },
      keyframes: {
        shimmer: {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(100%)' },
        },
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(-4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}


