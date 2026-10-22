import { defineConfig, devices } from '@playwright/test'

// Проверка мобильной вёрстки (аудит 21.10.2026, «Телефон»): главные экраны на ширине 375 px без горизонтальной
// прокрутки. Настоящий backend на временной SQLite с синтетическими данными + собранный интерфейс (e2e/server.py).
// Запуск: npm run build && npm run test:mobile. Python берётся из E2E_PYTHON (по умолчанию python3) — нужны
// зависимости backend; браузер — из PLAYWRIGHT_CHROMIUM, если задан (иначе: npx playwright install chromium).
const PORT = 4310

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  reporter: process.env.CI ? 'list' : 'line',
  use: {
    ...devices['iPhone SE'],
    // iPhone SE в Playwright — WebKit; проверяем той же шириной в Chromium (он есть и в CI, и в облачной среде).
    browserName: 'chromium',
    // E2E_WIDTH=1280 — тот же обход на ширине ноутбука (для ручной проверки снимков).
    viewport: { width: Number(process.env.E2E_WIDTH ?? 375), height: 667 },
    baseURL: `http://127.0.0.1:${PORT}`,
    locale: 'ru-RU',
    timezoneId: 'Europe/Moscow',
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM } : {},
  },
  webServer: {
    command: `${process.env.E2E_PYTHON ?? 'python3'} e2e/server.py ${PORT}`,
    url: `http://127.0.0.1:${PORT}/health`,
    timeout: 120_000,
    reuseExistingServer: false,
    stdout: 'pipe',
  },
})
