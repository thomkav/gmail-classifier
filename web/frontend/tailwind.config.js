/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        gray: {
          950: "#0b0d14",
        },
      },
    },
  },
  plugins: [],
};
