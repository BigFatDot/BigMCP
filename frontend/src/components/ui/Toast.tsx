/**
 * Toast - Toast notification system using React Hot Toast
 */

import { Toaster, toast as hotToast } from 'react-hot-toast'
import {
  CheckCircleIcon,
  XCircleIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
} from '@heroicons/react/24/outline'

/**
 * Toast Provider Component
 * Add this to your App root
 */
export function ToastProvider() {
  return (
    <Toaster
      position="top-right"
      toastOptions={{
        duration: 4000,
        style: {
          background: '#fff',
          color: '#171717',
          padding: '16px',
          borderRadius: '12px',
          boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.1)',
          fontFamily: 'Plus Jakarta Sans, sans-serif',
        },
        success: {
          iconTheme: {
            primary: '#10B981',
            secondary: '#fff',
          },
        },
        error: {
          iconTheme: {
            primary: '#EF4444',
            secondary: '#fff',
          },
        },
      }}
    />
  )
}

/**
 * Custom toast functions with BigMCP styling
 */
export const toast = {
  /**
   * Success toast
   */
  success: (message: string, description?: string) => {
    return hotToast.custom(
      (t) => (
        <div
          className={`${
            t.visible ? 'animate-fade-in' : 'opacity-0'
          } bg-white rounded-xl shadow-lg p-4 flex items-start gap-3 max-w-md`}
        >
          <div className="flex-shrink-0">
            <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center">
              <CheckCircleIcon className="w-6 h-6 text-green-600" />
            </div>
          </div>
          <div className="flex-1 pt-0.5">
            <p className="font-medium text-gray-900">{message}</p>
            {description && (
              <p className="text-sm text-gray-600 font-serif mt-1">{description}</p>
            )}
          </div>
          <button
            onClick={() => hotToast.dismiss(t.id)}
            className="flex-shrink-0 text-gray-400 hover:text-gray-600"
          >
            <XCircleIcon className="w-5 h-5" />
          </button>
        </div>
      ),
      { duration: 4000 }
    )
  },

  /**
   * Error toast
   */
  error: (message: string, description?: string) => {
    return hotToast.custom(
      (t) => (
        <div
          className={`${
            t.visible ? 'animate-fade-in' : 'opacity-0'
          } bg-white rounded-xl shadow-lg p-4 flex items-start gap-3 max-w-md`}
        >
          <div className="flex-shrink-0">
            <div className="w-10 h-10 rounded-lg bg-red-100 flex items-center justify-center">
              <XCircleIcon className="w-6 h-6 text-red-600" />
            </div>
          </div>
          <div className="flex-1 pt-0.5">
            <p className="font-medium text-gray-900">{message}</p>
            {description && (
              <p className="text-sm text-gray-600 font-serif mt-1">{description}</p>
            )}
          </div>
          <button
            onClick={() => hotToast.dismiss(t.id)}
            className="flex-shrink-0 text-gray-400 hover:text-gray-600"
          >
            <XCircleIcon className="w-5 h-5" />
          </button>
        </div>
      ),
      { duration: 5000 }
    )
  },

  /**
   * Warning toast
   */
  warning: (message: string, description?: string) => {
    return hotToast.custom(
      (t) => (
        <div
          className={`${
            t.visible ? 'animate-fade-in' : 'opacity-0'
          } bg-white rounded-xl shadow-lg p-4 flex items-start gap-3 max-w-md`}
        >
          <div className="flex-shrink-0">
            <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center">
              <ExclamationTriangleIcon className="w-6 h-6 text-amber-600" />
            </div>
          </div>
          <div className="flex-1 pt-0.5">
            <p className="font-medium text-gray-900">{message}</p>
            {description && (
              <p className="text-sm text-gray-600 font-serif mt-1">{description}</p>
            )}
          </div>
          <button
            onClick={() => hotToast.dismiss(t.id)}
            className="flex-shrink-0 text-gray-400 hover:text-gray-600"
          >
            <XCircleIcon className="w-5 h-5" />
          </button>
        </div>
      ),
      { duration: 4500 }
    )
  },

  /**
   * Info toast
   */
  info: (message: string, description?: string) => {
    return hotToast.custom(
      (t) => (
        <div
          className={`${
            t.visible ? 'animate-fade-in' : 'opacity-0'
          } bg-white rounded-xl shadow-lg p-4 flex items-start gap-3 max-w-md`}
        >
          <div className="flex-shrink-0">
            <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
              <InformationCircleIcon className="w-6 h-6 text-blue-600" />
            </div>
          </div>
          <div className="flex-1 pt-0.5">
            <p className="font-medium text-gray-900">{message}</p>
            {description && (
              <p className="text-sm text-gray-600 font-serif mt-1">{description}</p>
            )}
          </div>
          <button
            onClick={() => hotToast.dismiss(t.id)}
            className="flex-shrink-0 text-gray-400 hover:text-gray-600"
          >
            <XCircleIcon className="w-5 h-5" />
          </button>
        </div>
      ),
      { duration: 4000 }
    )
  },

  /**
   * Loading toast
   */
  loading: (message: string) => {
    return hotToast.loading(message, {
      style: {
        fontFamily: 'Plus Jakarta Sans, sans-serif',
      },
    })
  },

  /**
   * Promise toast (auto success/error based on promise)
   */
  promise: <T,>(
    promise: Promise<T>,
    messages: {
      loading: string
      success: string | ((data: T) => string)
      error: string | ((error: any) => string)
    }
  ) => {
    return hotToast.promise(promise, messages, {
      style: {
        fontFamily: 'Plus Jakarta Sans, sans-serif',
      },
    })
  },

  /**
   * Dismiss a toast
   */
  dismiss: (toastId?: string) => {
    hotToast.dismiss(toastId)
  },

  /**
   * Dismiss all toasts
   */
  dismissAll: () => {
    hotToast.dismiss()
  },
}
