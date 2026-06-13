import { createContext, useCallback, useContext, useState } from 'react'
import { Modal } from './Modal'
import { Button } from './Button'

/**
 * Accessible, in-app replacement for window.confirm().
 *
 * Built on the Headless-UI Modal primitive (role=dialog, aria-modal,
 * focus-trap, Escape-to-close), so it's keyboard- and screen-reader-friendly
 * and styled in-app — unlike the browser-native confirm, which can't be
 * translated or themed.
 *
 * Usage:
 *   const confirm = useConfirm()
 *   if (await confirm({ title: '…', message: '…', danger: true })) { … }
 */
export interface ConfirmOptions {
  title: string
  message?: React.ReactNode
  confirmLabel?: string
  cancelLabel?: string
  /** Red confirm button for destructive actions. */
  danger?: boolean
}

type ConfirmFn = (options: ConfirmOptions) => Promise<boolean>

const ConfirmContext = createContext<ConfirmFn | null>(null)

export function useConfirm(): ConfirmFn {
  const ctx = useContext(ConfirmContext)
  if (!ctx) {
    throw new Error('useConfirm must be used within a <ConfirmProvider>')
  }
  return ctx
}

interface State {
  open: boolean
  options: ConfirmOptions
  resolve?: (value: boolean) => void
}

const EMPTY: ConfirmOptions = { title: '' }

export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<State>({ open: false, options: EMPTY })

  const confirm = useCallback<ConfirmFn>((options) => {
    return new Promise<boolean>((resolve) => {
      setState({ open: true, options, resolve })
    })
  }, [])

  const settle = useCallback((value: boolean) => {
    setState((s) => {
      s.resolve?.(value)
      return { ...s, open: false, resolve: undefined }
    })
  }, [])

  const { open, options } = state

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <Modal
        isOpen={open}
        onClose={() => settle(false)}
        title={options.title}
        size="sm"
        showClose={false}
      >
        {options.message && (
          <div className="text-sm text-gray-600">{options.message}</div>
        )}
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="secondary" onClick={() => settle(false)}>
            {options.cancelLabel || 'Cancel'}
          </Button>
          <Button
            variant={options.danger ? 'danger' : 'primary'}
            onClick={() => settle(true)}
            autoFocus
          >
            {options.confirmLabel || 'Confirm'}
          </Button>
        </div>
      </Modal>
    </ConfirmContext.Provider>
  )
}
