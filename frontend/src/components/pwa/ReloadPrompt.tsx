import { useRegisterSW } from 'virtual:pwa-register/react'
import { Button } from '@/components/ui'

export function ReloadPrompt() {
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW()

  if (!needRefresh) return null

  return (
    <div className="fixed bottom-4 left-4 right-4 sm:left-auto sm:right-4 sm:w-96 z-50 bg-white border border-gray-200 rounded-lg shadow-lg p-4">
      <p className="text-sm text-gray-700 font-medium">
        A new version is available
      </p>
      <div className="flex gap-2 mt-3">
        <Button
          variant="primary"
          size="sm"
          onClick={() => updateServiceWorker(true)}
        >
          Update
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setNeedRefresh(false)}
        >
          Later
        </Button>
      </div>
    </div>
  )
}
