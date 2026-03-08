/**
 * Shared QueryClient instance
 *
 * Exported separately to avoid circular imports between main.tsx and AuthContext.
 * Used by:
 * - main.tsx: QueryClientProvider
 * - AuthContext: Clear cache on logout
 */

import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 5 * 60 * 1000, // 5 minutes
    },
  },
})
