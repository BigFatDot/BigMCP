/**
 * Terms of Service Page
 */

import { Link } from 'react-router-dom'
import { ArrowLeftIcon } from '@heroicons/react/24/outline'
import { usePageMeta } from '@/hooks/usePageMeta'

export function TermsPage() {
  usePageMeta({
    title: 'Terms of Service - BigMCP',
    description: 'BigMCP Terms of Service. Read our terms and conditions for using the platform.',
  })

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-3xl mx-auto px-4 py-12">
        <Link
          to="/login"
          className="inline-flex items-center text-sm text-gray-500 hover:text-gray-700 mb-8"
        >
          <ArrowLeftIcon className="w-4 h-4 mr-1" />
          Back
        </Link>

        <article className="prose prose-gray max-w-none">
          <h1>Terms of Service</h1>
          <p className="text-sm text-gray-500">Last Updated: February 2026</p>

          <h2>1. Acceptance of Terms</h2>
          <p>
            By accessing or using BigMCP ("Service"), you agree to be bound by these Terms of Service.
            If you do not agree, do not use the Service. BigMCP is operated by <strong>BigFatDot</strong>,
            based in Marseille, France.
          </p>

          <h2>2. Service Description</h2>
          <p>
            BigMCP provides a unified gateway for managing and orchestrating MCP (Model Context Protocol)
            servers. The Service is available in multiple editions: Community (free, self-hosted),
            Enterprise (self-hosted, perpetual license), and Cloud (managed SaaS).
          </p>

          <h2>3. User Accounts</h2>
          <ul>
            <li>You must provide accurate information when creating an account</li>
            <li>You are responsible for maintaining the security of your account</li>
            <li>You must be at least 16 years old to use the Service</li>
          </ul>

          <h2>4. Acceptable Use</h2>
          <p>You agree not to:</p>
          <ul>
            <li>Use the Service for illegal purposes</li>
            <li>Attempt to gain unauthorized access to other accounts or systems</li>
            <li>Interfere with the operation of the Service</li>
            <li>Reverse engineer or decompile the software (except as permitted by law)</li>
          </ul>

          <h2>5. Data & Privacy</h2>
          <ul>
            <li>You retain ownership of your data</li>
            <li>Your credentials are encrypted with Fernet symmetric encryption</li>
            <li>We access credentials only to connect to your authorized services</li>
            <li>See our <Link to="/privacy" className="text-orange hover:text-orange-dark">Privacy Policy</Link> for details</li>
          </ul>

          <h2>6. Pricing & Payments</h2>
          <ul>
            <li>Free trial period is 15 days for Cloud plans</li>
            <li>Payments are processed by LemonSqueezy</li>
            <li>Enterprise licenses are perpetual with optional annual support</li>
            <li>Prices may change with 30 days notice</li>
          </ul>

          <h2>7. Limitation of Liability</h2>
          <p>
            The Service is provided "as is" without warranties of any kind. BigFatDot shall not be liable
            for any indirect, incidental, or consequential damages arising from use of the Service.
          </p>

          <h2>8. Governing Law</h2>
          <p>
            These Terms are governed by the laws of France. Any disputes shall be subject to the
            exclusive jurisdiction of the courts of Marseille, France.
          </p>

          <h2>9. Contact</h2>
          <p>
            For questions about these Terms, contact us at:{' '}
            <a href="mailto:legal@bigmcp.cloud" className="text-orange hover:text-orange-dark">
              legal@bigmcp.cloud
            </a>
          </p>
        </article>
      </div>
    </div>
  )
}
