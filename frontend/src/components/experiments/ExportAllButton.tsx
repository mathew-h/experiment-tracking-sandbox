import { useMutation } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import { Button, useToast } from '@/components/ui'

interface ExportAllButtonProps {
  /** Any experiment of the lineage; the server exports the whole lineage. */
  experimentId: string
  size?: 'xs' | 'sm' | 'md'
}

/** "Export all": downloads one Excel workbook for the experiment and its segments. */
export function ExportAllButton({ experimentId, size = 'sm' }: ExportAllButtonProps) {
  const { success, error } = useToast()
  const mutation = useMutation({
    mutationFn: () => experimentsApi.exportAll(experimentId),
    onSuccess: (filename) => success('Export downloaded', filename),
    onError: (err: Error) => error('Export failed', err.message),
  })
  return (
    <Button
      variant="secondary"
      size={size}
      loading={mutation.isPending}
      onClick={() => mutation.mutate()}
      title="Download an Excel workbook with this experiment and all its segments"
    >
      {mutation.isPending ? 'Exporting…' : 'Export all'}
    </Button>
  )
}
