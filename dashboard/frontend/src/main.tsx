import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import { ErrorBoundary } from './components/shared/ErrorBoundary'

// 서비스 워커(크롬 '앱 설치' 조건)는 배포 빌드에서만 쓴다. 개발 서버에서는 같은 주소에 남아 있던 것을 지워 HMR과 섞이지 않게 한다
if ('serviceWorker' in navigator) {
  if (import.meta.env.PROD)
    window.addEventListener('load', () => void navigator.serviceWorker.register("/sw.js").then((r) => r.update()).catch(() => {}))
  else void navigator.serviceWorker.getRegistrations().then((list) => list.forEach((r) => r.unregister()))
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </BrowserRouter>
  </StrictMode>,
)
