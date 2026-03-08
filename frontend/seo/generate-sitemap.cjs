#!/usr/bin/env node
/**
 * Sitemap Generator for BigMCP
 *
 * Generates:
 *   dist/sitemap.xml       → sitemapindex referencing all sub-sitemaps
 *   dist/sitemap-docs.xml  → docs + app pages urlset
 * Run after build: node seo/generate-sitemap.js
 */

const fs = require('fs')
const path = require('path')

const BASE_URL = process.env.SITE_URL || 'https://bigmcp.cloud'

// Mirror of docs navigation structure (section id + item slugs)
const docsStructure = [
  { id: 'getting-started', items: ['introduction', 'quickstart', 'first-server'] },
  { id: 'guides', items: ['marketplace', 'credentials', 'tool-groups', 'api-keys', 'compositions', 'team-services'] },
  { id: 'integrations', items: ['claude-desktop', 'mistral-lechat', 'n8n', 'custom-clients'] },
  { id: 'concepts', items: ['mcp-overview', 'servers', 'tools', 'security'] },
  { id: 'api', items: ['api-overview', 'api-marketplace', 'api-credentials', 'api-mcp', 'api-tools'] },
  { id: 'self-hosting', items: ['self-host-overview', 'docker-setup', 'configuration', 'llm-providers', 'custom-servers', 'scaling', 'monitoring', 'backup'] },
]

const today = new Date().toISOString().split('T')[0]

// Build docs URL entries
const urls = [
  { loc: `${BASE_URL}/docs/getting-started/introduction`, priority: '0.9', changefreq: 'weekly' },
]

for (const section of docsStructure) {
  for (const slug of section.items) {
    if (section.id === 'getting-started' && slug === 'introduction') continue
    urls.push({
      loc: `${BASE_URL}/docs/${section.id}/${slug}`,
      priority: '0.7',
      changefreq: 'monthly',
    })
  }
}

// sitemap-docs.xml — docs pages urlset
const docsXml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls.map(u => `  <url>
    <loc>${u.loc}</loc>
    <lastmod>${today}</lastmod>
    <changefreq>${u.changefreq}</changefreq>
    <priority>${u.priority}</priority>
  </url>`).join('\n')}
</urlset>
`

// sitemap.xml — sitemapindex referencing all sub-sitemaps
const indexXml = `<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap>
    <loc>${BASE_URL}/sitemap-main.xml</loc>
  </sitemap>
  <sitemap>
    <loc>${BASE_URL}/sitemap-docs.xml</loc>
  </sitemap>
  <sitemap>
    <loc>${BASE_URL}/sitemap-blog.xml</loc>
  </sitemap>
  <sitemap>
    <loc>${BASE_URL}/sitemap-integrations.xml</loc>
  </sitemap>
</sitemapindex>
`

// Write to dist/
const distDir = path.join(__dirname, '..', 'dist')
if (!fs.existsSync(distDir)) {
  console.warn('Warning: dist/ not found. Run after build.')
  process.exit(0)
}

fs.writeFileSync(path.join(distDir, 'sitemap-docs.xml'), docsXml, 'utf-8')
fs.writeFileSync(path.join(distDir, 'sitemap.xml'), indexXml, 'utf-8')
console.log(`Sitemap generated: ${urls.length} docs URLs -> dist/sitemap-docs.xml`)
console.log(`Sitemap index generated -> dist/sitemap.xml`)
