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
import './styles/theme.css'
import App from './App.tsx'
import { applyTheme, getThemePref } from './utils/theme'

// Тема — до первой отрисовки, чтобы страница не мигнула светлой.
applyTheme(getThemePref())

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
