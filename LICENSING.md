# BigMCP Licensing

BigMCP is **free and open source software** licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPLv3).

## What This Means

- **Use** BigMCP for any purpose, personal or commercial
- **Deploy** on your own infrastructure with no restrictions
- **Modify** the source code to fit your needs
- **Distribute** your own versions
- **No user limits** — unlimited users, organizations, and features
- **No license keys** — just `docker compose up` and you're running

## AGPLv3 Requirements

If you modify BigMCP and expose it as a network service, you must make your modified source code available under the same license. This protects the open source ecosystem while allowing full freedom of use.

## BigMCP Cloud (bigmcp.cloud)

[bigmcp.cloud](https://app.bigmcp.cloud) is a **free demo platform** operated by BigFatDot. Use it to try BigMCP before deploying on your own infrastructure.

## Self-Hosted (Recommended for Production)

Self-hosted is the primary deployment model. All features are included:

- MCP Gateway with full protocol support (MCP 2025-03-26)
- Custom MCP server registration & auto-discovery
- Marketplace access (180+ servers)
- Unlimited users & organizations
- RBAC (Owner/Admin/Member/Viewer)
- OAuth 2.0 with PKCE
- Encrypted credential vault
- AI-powered orchestration & compositions
- Tool Groups with scoped API keys
- Audit logging

```bash
git clone https://github.com/bigfatdot/bigmcp.git
cd bigmcp && docker compose up -d
```

## Third-Party Licenses

BigMCP integrates with open source components:

| Component | License | Usage |
|-----------|---------|-------|
| FastAPI | MIT | Backend framework |
| SQLAlchemy | MIT | ORM |
| React | MIT | Frontend framework |
| PostgreSQL | PostgreSQL | Database |

Full dependency licenses are listed in:
- `mcp-registry/requirements.txt` (Python)
- `frontend/package.json` (Node.js)

## Contributing

Contributions are welcome under the AGPLv3 license. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Questions?

| Topic | Contact |
|-------|---------|
| General | [contact@bigmcp.cloud](mailto:contact@bigmcp.cloud) |
| Support | [support@bigmcp.cloud](mailto:support@bigmcp.cloud) |

---

*BigMCP is developed and maintained by [BigFatDot](https://bigfatdot.org).*
