/**
 * 404 Not Found Page
 */

import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { HomeIcon } from '@heroicons/react/24/outline'
import { Button } from '@/components/ui'
import { usePageMeta } from '@/hooks/usePageMeta'

export function NotFoundPage() {
  const { t } = useTranslation('common')

  usePageMeta({
    title: 'Page not found',
    description: 'The page you are looking for does not exist or has been moved.',
  })

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="text-center max-w-md">
        <p className="text-8xl font-bold text-orange mb-4">404</p>
        <h1 className="text-2xl font-bold text-gray-900 mb-2">
          {t('notFound.title', 'Page not found')}
        </h1>
        <p className="text-gray-600 font-serif mb-8">
          {t('notFound.description', 'The page you are looking for does not exist or has been moved.')}
        </p>
        <Link to="/app">
          <Button variant="primary" size="lg">
            <HomeIcon className="w-5 h-5 mr-2" />
            {t('notFound.backHome', 'Back to Home')}
          </Button>
        </Link>
      </div>
    </div>
  )
}
