import { createContext, useCallback, useContext, useEffect, useState } from 'react'
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
 *
 * For irreversible actions, pass `requireText` to force the user to type
 * a phrase (e.g. "DELETE") before the confirm button is enabled — replaces
 * the native window.prompt pattern.
 */
export interface ConfirmOptions {
  title: string
  message?: React.ReactNode
  confirmLabel?: string
  cancelLabel?: string
  /** Red confirm button for destructive actions. */
  danger?: boolean
  /**
   * If set, an input field is rendered and the confirm button stays disabled
   * until the user types this exact value (case-sensitive). The label above
   * the input is taken from `requireTextLabel`, falling back to a generic
   * "Type X to confirm" string.
   */
  requireText?: string
  requireTextLabel?: React.ReactNode
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
  const [typed, setTyped] = useState('')

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

  // Reset the typed-to-confirm input each time the dialog opens.
  useEffect(() => {
    if (open) setTyped('')
  }, [open])

  const needsText = !!options.requireText
  const textOk = !needsText || typed === options.requireText

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
        {needsText && (
          <div className="mt-4">
            {options.requireTextLabel && (
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {options.requireTextLabel}
              </label>
            )}
            <input
              type="text"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoFocus
              autoComplete="off"
              spellCheck={false}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-orange font-mono"
              placeholder={options.requireText}
            />
          </div>
        )}
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="secondary" onClick={() => settle(false)}>
            {options.cancelLabel || 'Cancel'}
          </Button>
          <Button
            variant={options.danger ? 'danger' : 'primary'}
            onClick={() => settle(true)}
            autoFocus={!needsText}
            disabled={!textOk}
          >
            {options.confirmLabel || 'Confirm'}
          </Button>
        </div>
      </Modal>
    </ConfirmContext.Provider>
  )
}
