import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// Тесты идут в часовом поясе колледжа: ошибки вида «даты сдвигаются на день из-за UTC» (toISOString)
// проявляются только при поясе восточнее UTC и ночью, поэтому без фиксированного пояса не ловятся.
process.env.TZ ??= 'Europe/Moscow'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    // Тесты лежат рядом с кодом (*.test.ts[x]) и в src/test (общие помощники).
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
