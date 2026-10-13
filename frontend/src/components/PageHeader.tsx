import type { ReactNode } from 'react'

interface PageHeaderProps {
  title: string
  description?: string
  actions?: ReactNode
}

function PageHeader({ title, description, actions }: PageHeaderProps) {
  return (
    <header className="page-header">
      <div className="page-header-text">
        <h1 className="page-title">{title}</h1>
        {description ? <p className="page-description">{description}</p> : null}
      </div>
      {actions ? <div className="page-header-actions">{actions}</div> : null}
    </header>
  )
}

export default PageHeader
