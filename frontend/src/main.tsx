import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './fonts.css'
import './index.css'
import './styles/feedback.css'
import './styles/inbox.css'
import './styles/assignment.css'
import './styles/tasks-admin.css'
import './styles/wizard.css'
import './styles/shell.css'
import './styles/my-day.css'
import './styles/a11y.css'
import './styles/meals.css'
import './styles/theme.css'
import './styles/profile.css'
import './styles/journal.css'
import './styles/dossier.css'
import './styles/controls.css'
import './styles/support.css'
import './styles/folder.css'
import App from './App.tsx'
import { installErrorReporting } from './utils/errorReporting'
import { applyTheme, getThemePref } from './utils/theme'

// Тема — до первой отрисовки, чтобы страница не мигнула светлой.
applyTheme(getThemePref())
// Необработанные ошибки страницы — на сервер (журнал и Sentry), чтобы о них узнавать не только со слов кураторов.
installErrorReporting()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
