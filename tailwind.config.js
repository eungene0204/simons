/** @type {import('tailwindcss').Config} */
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
      },
      colors: {
        background: 'var(--background)',
        foreground: 'var(--foreground)',
        white: 'rgb(224, 224, 224)',
        blue: {
          500: 'rgb(59, 134, 247)',
        },
        'brand-blue': 'rgb(59, 134, 247)',
        'main-blue': 'rgb(55, 122, 244)',
        'main-red': 'rgb(239, 68, 68)',
        'main-green': 'rgb(34, 197, 94)',
        tab_black: 'rgb(37, 38, 46)',
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


