import { identifierParts } from '../../ledger/identifier'

function IdentifierText({ value }: { value: string }) {
  const parts = identifierParts(value)
  return (
    <>
      {parts.map((part, index) => (
        <span key={`${part}-${index}`}>
          {index > 0 ? '_' : null}
          {part}
          {index < parts.length - 1 ? <wbr /> : null}
        </span>
      ))}
    </>
  )
}

export default IdentifierText
