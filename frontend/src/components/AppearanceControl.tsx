import { useEffect, useState } from 'react'
import { APPEARANCE_KEY, applyAppearance, readAppearance, type Appearance } from '../theme'

const OPTIONS: { id: Appearance; label: string }[] = [
  { id: 'system', label: 'System' },
  { id: 'light', label: 'Light' },
  { id: 'dark', label: 'Dark' },
]

function AppearanceControl() {
  const [appearance, setAppearance] = useState<Appearance>(() => readAppearance(window.localStorage))

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const apply = () => applyAppearance(appearance, media.matches)
    apply()
    if (appearance !== 'system') return
    media.addEventListener('change', apply)
    return () => media.removeEventListener('change', apply)
  }, [appearance])

  function choose(next: Appearance) {
    window.localStorage.setItem(APPEARANCE_KEY, next)
    setAppearance(next)
  }

  return (
    <div className="appearance" role="group" aria-label="Appearance">
      {OPTIONS.map((option) => (
        <button
          key={option.id}
          type="button"
          className={appearance === option.id ? 'appearance-option is-selected' : 'appearance-option'}
          aria-pressed={appearance === option.id}
          onClick={() => choose(option.id)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

export default AppearanceControl
