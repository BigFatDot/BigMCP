# Security Policy

## Supported Versions

We release patches for security vulnerabilities in the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 1.x.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue, please report it responsibly.

### How to Report

**Email**: security@bigmcp.cloud

Please include the following information in your report:

1. **Description**: A detailed description of the vulnerability
2. **Impact**: What could an attacker achieve with this vulnerability?
3. **Steps to Reproduce**: Step-by-step instructions to reproduce the issue
4. **Affected Components**: Which part of BigMCP is affected (backend, frontend, MCP gateway, etc.)
5. **Suggested Fix**: (Optional) If you have a suggested fix, please include it

### What to Expect

- **Acknowledgment**: We will acknowledge your report within 48 hours
- **Initial Assessment**: We will provide an initial assessment within 7 days
- **Resolution Timeline**: We aim to resolve critical vulnerabilities within 30 days
- **Disclosure**: We will coordinate with you on disclosure timing

### Safe Harbor

We consider security research activities conducted in accordance with this policy to be:

- Authorized concerning any applicable anti-hacking laws
- Authorized concerning any relevant anti-circumvention laws
- Exempt from restrictions in our Terms of Service that would interfere with conducting security research

We will not pursue civil action or initiate a complaint to law enforcement for accidental, good-faith violations of this policy.

## Security Best Practices

When deploying BigMCP, please follow these security recommendations:

### Authentication & Secrets

- Use strong, unique values for `JWT_SECRET` (min 32 characters)
- Generate a secure `ENCRYPTION_KEY` using Fernet
- Rotate API keys periodically
- Never commit secrets to version control

### Network Security

- Always use HTTPS in production
- Configure CORS strictly for your domain
- Use a firewall to restrict database access
- Consider using a WAF (Web Application Firewall)

### Database Security

- Use a strong PostgreSQL password
- Enable SSL for database connections
- Restrict database access to application servers only
- Enable audit logging

### Monitoring

- Monitor for suspicious authentication attempts
- Set up alerts for unusual API usage patterns
- Review audit logs regularly
- Keep dependencies updated

## Security Features

BigMCP includes several security features:

- **Encrypted credentials at rest** (Fernet symmetric encryption)
- **bcrypt password hashing** with configurable cost factor
- **bcrypt API key hashing** with prefix-based lookup
- **OAuth 2.0 with PKCE** for secure third-party authentication
- **Rate limiting** (20-200 requests/minute depending on endpoint sensitivity)
- **Multi-tenant isolation** at database level
- **Parameterized SQL queries** to prevent injection
- **CORS validation** for cross-origin requests

## Acknowledgments

We thank the security research community for helping keep BigMCP secure.

---

*Last updated: February 2026*
