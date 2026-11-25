/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#1A1917',
        sidebar: '#141311',
        card: '#252421',
        cardHover: '#2C2A26',
        borderSubtle: '#2F2D29',
        borderStrong: '#3E3B35',
        accent: '#D97757',
        accentHover: '#E48667',
        ink: '#ECEAE4',
        inkMuted: '#A19E95',
        inkDim: '#6F6C64',
        studioCyan: '#38BDF8',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono: ['JetBrains Mono', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
};
