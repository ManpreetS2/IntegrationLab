import { errorMessage } from '../hooks'

interface SectionStatusProps {
  loading: boolean
  error: unknown
  hasData: boolean
  onRetry: () => void
  loadingText?: string
}

/** Per-section loading / error line so one failing request never blanks the whole page. */
function SectionStatus({ loading, error, hasData, onRetry, loadingText = 'Loading…' }: SectionStatusProps) {
  if (error) {
    return (
      <div className="section-error" role="alert">
        <span>{errorMessage(error)}</span>
        <button type="button" className="secondary-button small-button" onClick={onRetry}>
          Retry
        </button>
      </div>
    )
  }
  if (loading && !hasData) return <p className="loading-text">{loadingText}</p>
  return null
}

export default SectionStatus
