# BigMCP Licensing

BigMCP follows an **Open Core** licensing model, making the complete platform available for self-hosting while offering commercial options for teams and enterprises.

## License Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         LICENSE OPTIONS                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐   │
│  │    Community     │  │   Cloud SaaS     │  │   Enterprise     │   │
│  │   (Self-Hosted)  │  │    (Managed)     │  │  (Self-Hosted)   │   │
│  ├──────────────────┤  ├──────────────────┤  ├──────────────────┤   │
│  │ ELv2 License     │  │ Commercial       │  │ Commercial       │   │
│  │ Free forever     │  │ €4.99+/month     │  │ One-time fee     │   │
│  │ 1 user limit     │  │ Unlimited users  │  │ Unlimited users  │   │
│  │ Full platform    │  │ Full platform    │  │ Full platform    │   │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 1. Community Edition (Self-Hosted)

**License**: Elastic License 2.0 (ELv2) - See [LICENSE](LICENSE)

### What's Included
- Complete platform (backend + frontend)
- MCP Gateway with full protocol support
- AI-powered orchestration
- Dynamic marketplace access
- All security features (JWT, OAuth 2.0, encryption)
- Limited to **1 user**

### Permitted Uses
- Personal use and learning
- Internal business use (single user)
- Non-commercial projects
- Contributing to the project
- Building integrations

### Restrictions (ELv2)
- Cannot provide BigMCP as a managed service to third parties
- Cannot remove or modify license notices
- Cannot use to compete with BigMCP's commercial offerings

### Quick Start
```bash
git clone https://github.com/bigfatdot/bigmcp.git
cd bigmcp && docker compose up -d
```

---

## 2. Cloud SaaS (Managed Service)

**License**: Commercial subscription

### Plans
| Plan | Price | Users | Features |
|------|-------|-------|----------|
| **Individual** | €4.99/month | 1 | All features, no infrastructure to manage |
| **Team** | €4.99/month + €4.99/user/month | 2-20 | Organizations, RBAC, shared credentials |

### What's Included
- Fully managed hosting at [app.bigmcp.cloud](https://app.bigmcp.cloud)
- Automatic updates and maintenance
- 99.9% uptime SLA
- Technical support
- Marketplace API access

**[Start Free Trial →](https://app.bigmcp.cloud)**

---

## 3. Enterprise Edition (Self-Hosted)

**License**: Commercial license (one-time fee)

### What's Included
- Complete platform (backend + frontend)
- **Unlimited users**
- Organizations & RBAC
- SSO/SAML integration
- Air-gapped deployment support
- Offline marketplace sync
- Priority support
- Custom integrations

### Ideal For
- Large organizations
- Regulated industries
- On-premise requirements
- Data sovereignty needs

**[Contact Sales →](mailto:enterprise@bigmcp.cloud)**

---

## Public Sector Program

Enterprise licenses are provided **free of charge** to public sector entities worldwide.

### Eligible Organizations
- Government ministries and agencies (e.g., `*.gouv.fr`, `*.gov.uk`)
- Local and regional authorities (e.g., `*.paris.fr`, `*.berlin.de`)
- Public establishments and institutions
- Public hospitals and healthcare systems
- Public educational institutions (e.g., `*.edu`, `*.ac-*.fr`)
- Non-profit organizations serving the public

### How It Works

1. **Automatic Detection**: Register with your official public sector email
2. **Instant Access**: If your domain is in our whitelist, you get a free Enterprise license automatically
3. **New Domains**: Not whitelisted yet? Contact us to add your organization

### Request Domain Addition

If your public sector domain isn't recognized:

1. Contact [enterprise@bigmcp.cloud](mailto:enterprise@bigmcp.cloud)
2. Provide:
   - Your organization's official name
   - Email domain to whitelist
   - Brief description of public service mission
3. We verify and add your domain (usually within 24-48 hours)
4. All users from your domain can then get free Enterprise licenses

### Security

- Verification is performed server-side against our curated whitelist
- Parent domain matching (e.g., `education.gouv.fr` → recognized under `gouv.fr`)
- Discount applied automatically during checkout - no coupon codes exposed

---

## Third-Party Licenses

BigMCP integrates with open source components. Key dependencies:

| Component | License | Usage |
|-----------|---------|-------|
| FastAPI | MIT | Backend framework |
| SQLAlchemy | MIT | ORM |
| React | MIT | Frontend framework |
| PostgreSQL | PostgreSQL | Database |

Full dependency licenses are listed in:
- `mcp-registry/requirements.txt` (Python)
- `frontend/package.json` (Node.js)

---

## Contributor License Agreement (CLA)

By contributing to BigMCP:

1. **Community contributions** are licensed under ELv2
2. **Enterprise feature contributions** grant BigFatDot a non-exclusive license to include them in commercial editions

See [CONTRIBUTING.md](CONTRIBUTING.md) for full contribution guidelines.

---

## Questions?

| Topic | Contact |
|-------|---------|
| Licensing | [licensing@bigmcp.cloud](mailto:licensing@bigmcp.cloud) |
| Enterprise | [enterprise@bigmcp.cloud](mailto:enterprise@bigmcp.cloud) |
| Support | [support@bigmcp.cloud](mailto:support@bigmcp.cloud) |

---

*BigMCP is developed and maintained by [BigFatDot](https://bigfatdot.org).*
