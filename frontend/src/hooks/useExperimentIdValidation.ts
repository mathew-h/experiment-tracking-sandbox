import { useState, useEffect } from 'react'
import { experimentsApi } from '@/api/experiments'

export type IdValidationStatus = 'idle' | 'checking' | 'available' | 'taken' | 'error'

export interface IdValidationState {
  status: IdValidationStatus
  message: string
}

/**
 * Debounced hook that checks whether an experiment ID is available via
 * GET /api/experiments/{id}/exists.
 *
 * @param value       The current input value to validate.
 * @param currentId   The existing ID on the record being edited. When value
 *                    equals currentId the hook returns 'available' immediately
 *                    so the "Save" button stays enabled without an API call.
 */
export function useExperimentIdValidation(
  value: string,
  currentId?: string,
): IdValidationState {
  const [state, setState] = useState<IdValidationState>({ status: 'idle', message: '' })

  useEffect(() => {
    const trimmed = value.trim()

    if (!trimmed) {
      setState({ status: 'idle', message: '' })
      return
    }

    if (currentId !== undefined && trimmed === currentId) {
      setState({ status: 'available', message: 'Current ID' })
      return
    }

    setState({ status: 'checking', message: '' })

    const timer = setTimeout(async () => {
      try {
        const { exists } = await experimentsApi.checkExists(trimmed)
        setState(
          exists
            ? { status: 'taken', message: `'${trimmed}' is already in use` }
            : { status: 'available', message: 'Available' },
        )
      } catch {
        setState({ status: 'error', message: 'Could not validate ID' })
      }
    }, 300)

    return () => clearTimeout(timer)
  }, [value, currentId])

  return state
}
