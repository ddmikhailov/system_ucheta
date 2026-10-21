import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

// Учётные данные одноразовой базы из e2e/server.py (синтетика, к реальной платформе отношения не имеют).
const ADMIN = { username: 'admin', password: 'Vt4#Wq8nXs2!kL' }
const CURATOR = { username: 'e2e.curator', password: 'Pm6#Hy3rGc7!zN' }
const HEADERS = { 'X-Requested-With': 'kait20' }

/** Ширина документа не больше ширины окна: на телефоне ничего не уезжает вбок. Если уезжает — какие элементы. */
async function expectNoHorizontalScroll(page: Page, screen: string) {
  const overflow = await page.evaluate(() => {
    const width = document.documentElement.clientWidth
    const wide = [...document.querySelectorAll<HTMLElement>('body *')]
      .filter((el) => el.getBoundingClientRect().right > width + 1 && el.offsetParent !== null)
      // Внутри полос с собственной прокруткой (вкладки, широкие таблицы в обёртке) выход за край — норма.
      .filter((el) => !el.parentElement?.closest('.tabbar, .table-scroll, [data-scroll-x]'))
      .slice(0, 5)
      .map((el) => `${el.tagName.toLowerCase()}.${[...el.classList].join('.')}`)
    return { scrollWidth: document.documentElement.scrollWidth, width, wide }
  })
  expect(overflow.scrollWidth, `${screen}: горизонтальная прокрутка, выходят за край: ${overflow.wide.join(', ')}`).toBeLessThanOrEqual(overflow.width)
}

async function open(page: Page, path: string, ready: string) {
  await page.goto(path)
  await expect(page.locator(ready).first()).toBeVisible()
  await page.waitForLoadState('networkidle')
}

test.beforeAll(async ({ request }) => {
  // Задача куратору — чтобы «Мои задачи» и «Мой день» были не пустыми.
  const login = await request.post('/auth/login', { data: ADMIN })
  expect(login.ok()).toBeTruthy()
  const headers = { ...HEADERS, Authorization: `Bearer ${(await login.json()).access_token}` }
  const due = new Date(Date.now() + 3 * 86_400_000).toISOString().slice(0, 10)
  const task = await request.post('/tasks', {
    headers,
    data: {
      title: 'Сведения о занятости студентов во внеурочное время (кружки, секции, волонтёрство)',
      collect_mode: 'student', due_date: due, scope: { all_groups: true },
      fields: [{ label: 'Кружок или секция', type: 'text' }],
    },
  })
  expect(task.ok(), await task.text()).toBeTruthy()
})

test('главные экраны куратора на 375 px без горизонтальной прокрутки', async ({ page }) => {
  await page.goto('/login')
  await expectNoHorizontalScroll(page, 'Вход')
  await page.getByLabel('Логин').fill(CURATOR.username)
  await page.getByLabel('Пароль', { exact: true }).fill(CURATOR.password)
  await page.getByRole('button', { name: 'Войти' }).click()
  await page.waitForURL('**/my-day')

  const groups = await (await page.request.get('/curator/groups', { headers: HEADERS })).json()
  const groupId = groups[0].id
  const today = new Date().toISOString().slice(0, 10)
  const roster = await (await page.request.get(`/curator/groups/${groupId}/day?date=${today}`, { headers: HEADERS })).json()
  const studentId = roster.entries[0].student_id

  const screens: [string, string, string][] = [
    ['Мой день', '/my-day', '.app-main h2, .app-main h3'],
    ['Мои группы', '/cabinet', '.app-main a[href^="/cabinet/groups/"]'],
    ['Журнал группы', `/cabinet/groups/${groupId}`, '[role="tabpanel"]'],
    ['Карточка студента', `/students/${studentId}`, '.app-main h2'],
    ['Мои задачи', '/my-tasks', '.app-main a[href^="/tasks/assignment/"]'],
  ]
  await test.step('Панель уведомлений', async () => {
    await open(page, '/my-day', '.app-main h2, .app-main h3')
    await page.getByRole('button', { name: 'Уведомления' }).click()
    const box = await page.getByRole('dialog', { name: 'Уведомления' }).boundingBox()
    expect(box, 'панель колокольчика открылась').not.toBeNull()
    // Панель целиком на экране: раньше на телефоне она уходила за левый край.
    expect(box!.x).toBeGreaterThanOrEqual(0)
    expect(box!.x + box!.width).toBeLessThanOrEqual(375)
    if (process.env.E2E_SCREENSHOTS) await page.screenshot({ path: `${process.env.E2E_SCREENSHOTS}/Уведомления.png` })
    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: 'Уведомления' }).click()
  })

  for (const [name, path, ready] of screens) {
    await test.step(name, async () => {
      await open(page, path, ready)
      await expectNoHorizontalScroll(page, name)
      // E2E_SCREENSHOTS=<каталог> — сохранить снимки экранов, чтобы посмотреть вёрстку глазами.
      const dir = process.env.E2E_SCREENSHOTS
      const shot = await page.screenshot({ fullPage: true, ...(dir ? { path: `${dir}/${name}.png` } : {}) })
      await test.info().attach(`${name}.png`, { body: shot, contentType: 'image/png' })
    })
  }
})
