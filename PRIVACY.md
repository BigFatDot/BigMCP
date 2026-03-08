# Privacy Policy

**Last Updated:** February 2026

BigMCP ("we", "our", "us") is committed to protecting your privacy. This Privacy Policy explains how we collect, use, disclose, and safeguard your information when you use our services.

## 1. Information We Collect

### 1.1 Account Information
When you create an account, we collect:
- Email address
- Password (hashed, never stored in plain text)
- Display name (optional)

### 1.2 Service Data
When you use BigMCP, we process:
- **MCP Server Configurations**: Server names, connection settings
- **Credentials**: API keys, tokens, and secrets you provide for external services (encrypted with Fernet symmetric encryption)
- **Tool Execution Logs**: Metadata about tool usage (timestamps, tool names, success/failure status)
- **Compositions**: Workflow configurations you create

### 1.3 Technical Data
We automatically collect:
- IP addresses
- Browser type and version
- Device information
- Usage statistics and analytics

### 1.4 Payment Information
For paid plans, payment processing is handled by **LemonSqueezy**. We do not store your credit card information. We only receive:
- Transaction confirmation
- Subscription status
- Customer ID for billing association

## 2. How We Use Your Information

We use collected information to:
- Provide and maintain the BigMCP service
- Process your transactions
- Send service-related communications
- Improve our services
- Ensure security and prevent fraud
- Comply with legal obligations

## 3. Data Security

### 3.1 Encryption
- **Credentials at Rest**: All sensitive credentials are encrypted using Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256)
- **Data in Transit**: All communications use TLS 1.3
- **Password Storage**: Passwords are hashed using bcrypt with appropriate work factors

### 3.2 Access Control
- Role-based access control (RBAC) for team features
- API key scoping for granular permissions
- Session management with secure JWT tokens

### 3.3 Infrastructure
- Self-hosted edition: You control all data on your infrastructure
- Cloud edition: Data hosted on secure European infrastructure

## 4. Data Sharing

We do **not** sell your personal information. We may share data with:

### 4.1 Service Providers
- **LemonSqueezy**: Payment processing
- **Email provider**: Transactional emails (account verification, password reset)

### 4.2 Legal Requirements
We may disclose information when required by:
- Law enforcement requests
- Legal proceedings
- Protection of our rights or safety

### 4.3 External Services (User-Controlled)
When you connect MCP servers (GitHub, Slack, etc.), your credentials are used solely to authenticate with those services on your behalf. We do not access or store data from those services beyond what's necessary for tool execution.

## 5. Data Retention

| Data Type | Retention Period |
|-----------|-----------------|
| Account data | Until account deletion |
| Credentials | Until you remove them |
| Execution logs | 90 days (configurable for Enterprise) |
| Analytics | 12 months (aggregated) |

## 6. Your Rights

### 6.1 GDPR Rights (EU Users)
You have the right to:
- **Access**: Request a copy of your data
- **Rectification**: Correct inaccurate data
- **Erasure**: Request deletion of your data
- **Portability**: Export your data
- **Objection**: Object to certain processing
- **Restriction**: Limit how we use your data

### 6.2 CCPA Rights (California Users)
You have the right to:
- Know what personal information we collect
- Delete your personal information
- Opt-out of sale (we do not sell data)
- Non-discrimination for exercising your rights

### 6.3 Exercising Your Rights
To exercise any of these rights, contact us at: **privacy@bigmcp.cloud**

We will respond within 30 days.

## 7. Cookies and Tracking

### 7.1 Essential Cookies
We use essential cookies for:
- Authentication (session tokens)
- Security (CSRF protection)

### 7.2 Analytics
We use privacy-respecting analytics to understand service usage. No personal data is shared with third-party advertisers.

### 7.3 Managing Cookies
You can disable cookies in your browser settings. Note that disabling essential cookies will prevent authentication.

## 8. Children's Privacy

BigMCP is not intended for users under 16 years of age. We do not knowingly collect information from children.

## 9. International Data Transfers

For Cloud edition users:
- Data is primarily processed in the European Union
- Any transfers outside the EU comply with appropriate safeguards (Standard Contractual Clauses)

For Self-hosted editions:
- Data remains on your infrastructure under your control

## 10. Self-Hosted Editions

If you use BigMCP Community or Enterprise (self-hosted):
- All data remains on your infrastructure
- We do not have access to your data
- License validation uses only your license key (no personal data transmitted)
- You are responsible for your own privacy compliance

## 11. Changes to This Policy

We may update this Privacy Policy periodically. We will notify you of material changes by:
- Email notification
- Prominent notice on our website
- Update to the "Last Updated" date above

## 12. Contact Us

For privacy-related inquiries:

**Data Protection Contact**
Email: privacy@bigmcp.cloud

**BigFatDot**
Marseille, France

---

## Edition-Specific Privacy Notes

### Community Edition (Self-Hosted)
- All data stored locally on your servers
- No telemetry or data collection by BigMCP
- You are the data controller

### Cloud Edition (SaaS)
- Data hosted on BigMCP infrastructure
- Subject to this full privacy policy
- BigMCP is the data processor

### Enterprise Edition (Self-Hosted)
- All data stored on your infrastructure
- Optional telemetry (disabled by default)
- License validation only (no personal data)
- You are the data controller
