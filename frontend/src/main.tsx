import { StrictMode, Suspense, lazy, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import OperatorGate from './components/OperatorGate.tsx'
import './index.css'
import './ledger/ledger.css'

const DesignPreview = import.meta.env.DEV
  ? lazy(() => import('./design-preview/DesignPreview.tsx'))
  : null

function isDesignPreviewHash() {
  return window.location.hash.replace(/^#\/?/, '').startsWith('design-preview')
}

function Root() {
  const [preview, setPreview] = useState(() => import.meta.env.DEV && isDesignPreviewHash())

  useEffect(() => {
    if (!import.meta.env.DEV) return
    const sync = () => setPreview(isDesignPreviewHash())
    window.addEventListener('hashchange', sync)
    return () => window.removeEventListener('hashchange', sync)
  }, [])

  if (preview && DesignPreview) {
    return (
      <StrictMode>
        <Suspense fallback={null}>
          <DesignPreview />
        </Suspense>
      </StrictMode>
    )
  }

  return (
    <StrictMode>
      <OperatorGate>
        <App />
      </OperatorGate>
    </StrictMode>
  )
}

createRoot(document.getElementById('root')!).render(<Root />)
