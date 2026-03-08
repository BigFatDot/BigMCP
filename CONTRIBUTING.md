# Contributing to BigMCP

Thank you for your interest in contributing to BigMCP! This document provides guidelines and instructions for contributing.

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment for everyone.

## Getting Started

### Development Setup

```bash
# Clone the repository
git clone https://github.com/bigfatdot/bigmcp.git
cd bigmcp/mcp-registry

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install

# Start development server
uvicorn app.main:app --reload --port 8001
```

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html
```

## Code Style

We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
# Check and fix code style
ruff check --fix --select I .

# Format code
ruff format .
```

Ruff integrates with most code editors. You can automate linting with git pre-commit hooks:

```bash
pre-commit install
```

## Pull Request Process

1. **Fork the repository** and create your branch from `main`
2. **Write clear commit messages** following conventional commits
3. **Add tests** for new functionality
4. **Update documentation** if needed
5. **Ensure all tests pass** before submitting
6. **Submit a pull request** with a clear description

### Commit Message Format

```
type(scope): description

[optional body]

[optional footer]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Examples:
- `feat(auth): add OAuth 2.0 PKCE support`
- `fix(gateway): resolve connection timeout issue`
- `docs(api): update REST API reference`

## Reporting Issues

When reporting bugs, please include:
- BigMCP version
- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs or error messages

## Feature Requests

Feature requests are welcome! Please:
- Check existing issues first
- Clearly describe the use case
- Explain why this would benefit other users

## Contributor License Agreement (CLA)

By contributing to BigMCP, you agree to the following:

### Community Contributions
Contributions to the Community Edition are licensed under the Elastic License 2.0 (ELv2).

### Enterprise Contributions
If you wish to contribute features that may be included in the Enterprise Edition, you agree to grant BigFatDot a non-exclusive, perpetual, royalty-free license to use, modify, and redistribute your contribution under any license, including commercial licenses.

See [LICENSE](LICENSE) for full licensing details.

## Questions?

- **API Docs**: https://bigmcp.cloud/docs (or `/docs` on your instance)
- **Issues**: https://github.com/bigfatdot/bigmcp/issues
- **Email**: support@bigmcp.cloud

---

*Thank you for contributing to BigMCP!*
