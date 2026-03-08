/**
 * Privacy Policy Page
 */

import { Link } from 'react-router-dom'
import { ArrowLeftIcon } from '@heroicons/react/24/outline'
import { usePageMeta } from '@/hooks/usePageMeta'

export function PrivacyPage() {
  usePageMeta({
    title: 'Privacy Policy - BigMCP',
    description: 'BigMCP Privacy Policy. Learn how we collect, use, and protect your data.',
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
          <h1>Privacy Policy</h1>
          <p className="text-sm text-gray-500">Last Updated: February 2026</p>

          <h2>1. Information We Collect</h2>
          <h3>Account Information</h3>
          <ul>
            <li>Email address</li>
            <li>Password (hashed, never stored in plain text)</li>
            <li>Display name (optional)</li>
          </ul>

          <h3>Service Data</h3>
          <ul>
            <li><strong>MCP Server Configurations</strong>: Server names, connection settings</li>
            <li><strong>Credentials</strong>: API keys and tokens for external services (encrypted with Fernet symmetric encryption)</li>
            <li><strong>Tool Execution Logs</strong>: Metadata about tool usage</li>
            <li><strong>Compositions</strong>: Workflow configurations you create</li>
          </ul>

          <h3>Payment Information</h3>
          <p>
            Payments are processed by <strong>LemonSqueezy</strong>. We do not store your credit card information.
          </p>

          <h2>2. How We Use Your Information</h2>
          <ul>
            <li>Provide and maintain the BigMCP service</li>
            <li>Process transactions</li>
            <li>Send service-related communications</li>
            <li>Ensure security and prevent fraud</li>
          </ul>

          <h2>3. Data Security</h2>
          <ul>
            <li><strong>Credentials at Rest</strong>: Encrypted using Fernet (AES-128-CBC + HMAC-SHA256)</li>
            <li><strong>Data in Transit</strong>: All communications use TLS 1.3</li>
            <li><strong>Passwords</strong>: Hashed using bcrypt</li>
            <li><strong>Access Control</strong>: RBAC for team features, scoped API keys</li>
          </ul>

          <h2>4. Data Sharing</h2>
          <p>We do <strong>not</strong> sell your personal information. We share data only with:</p>
          <ul>
            <li><strong>LemonSqueezy</strong>: Payment processing</li>
            <li><strong>Email provider</strong>: Transactional emails</li>
          </ul>

          <h2>5. Your Rights (GDPR)</h2>
          <p>EU users have the right to:</p>
          <ul>
            <li>Access, rectify, or delete your data</li>
            <li>Export your data (portability)</li>
            <li>Object to or restrict processing</li>
          </ul>
          <p>
            To exercise these rights, contact:{' '}
            <a href="mailto:privacy@bigmcp.cloud" className="text-orange hover:text-orange-dark">
              privacy@bigmcp.cloud
            </a>
          </p>

          <h2>6. Self-Hosted Editions</h2>
          <p>
            For Community and Enterprise editions: all data remains on your infrastructure.
            We do not have access to your data. You are the data controller.
          </p>

          <h2>7. Cookies</h2>
          <p>
            We use only essential cookies for authentication and security.
            No personal data is shared with third-party advertisers.
          </p>

          <h2>8. Contact</h2>
          <p>
            <strong>Data Protection Contact</strong><br />
            Email:{' '}
            <a href="mailto:privacy@bigmcp.cloud" className="text-orange hover:text-orange-dark">
              privacy@bigmcp.cloud
            </a>
          </p>
          <p>
            <strong>BigFatDot</strong><br />
            Marseille, France
          </p>

          <p className="text-sm text-gray-500 mt-8">
            See also our <Link to="/terms" className="text-orange hover:text-orange-dark">Terms of Service</Link>.
          </p>
        </article>
      </div>
    </div>
  )
}
