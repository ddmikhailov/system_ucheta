import { readFileSync } from 'node:fs'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// Номер версии — из package.json (держится в паре с backend, см. backend/tests/test_versions.py): показывается
// в меню пользователя, уходит с сообщениями о проблемах и ошибках, по нему решается, показывать ли «Что нового».
const { version } = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf-8')) as { version: string }

// Тесты идут в часовом поясе колледжа: ошибки вида «даты сдвигаются на день из-за UTC» (toISOString)
// проявляются только при поясе восточнее UTC и ночью, поэтому без фиксированного пояса не ловятся.
process.env.TZ ??= 'Europe/Moscow'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  define: {
    'import.meta.env.VITE_APP_VERSION': JSON.stringify(version),
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    // Тесты лежат рядом с кодом (*.test.ts[x]) и в src/test (общие помощники).
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
