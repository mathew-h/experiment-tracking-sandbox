import { useParams } from 'react-router-dom'

/** Placeholder for the core flood run page; the body is filled in by Task 4. */
export function CoreFloodRunPage() {
  const { baseId } = useParams<{ baseId: string }>()
  return <h1 className="text-lg font-semibold text-ink-primary font-mono-data">{baseId}</h1>
}
