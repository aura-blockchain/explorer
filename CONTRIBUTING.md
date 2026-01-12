# Contributing to AURA Explorer

Thank you for your interest in contributing to the AURA Explorer! This document provides guidelines for contributing to this project.

## Getting Started

1. Fork the repository
2. Clone your fork locally
3. Set up the development environment (see README.md)
4. Create a feature branch from `main`

## Development Setup

```bash
# Backend (Python/Flask)
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Frontend (Ping.pub)
cd ping-pub-explorer
npm install
```

## How to Contribute

### Reporting Bugs

- Use GitHub Issues with the bug report template
- Include browser/environment details
- Provide steps to reproduce
- Include screenshots if applicable

### Suggesting Features

- Open an issue with the feature request template
- Explain the use case and expected behavior
- Discuss in the issue before implementing

### Pull Requests

1. Ensure your code follows the existing style
2. Write/update tests as needed
3. Update documentation for any API changes
4. Keep commits atomic and well-described
5. Reference related issues in PR description

## Code Style

### Python (Backend)
- Follow PEP 8
- Use type hints where possible
- Document functions with docstrings
- Run `black` and `flake8` before committing

### JavaScript/Vue (Frontend)
- Follow existing Ping.pub conventions
- Use ES6+ syntax
- Run `npm run lint` before committing

## Testing

```bash
# Backend tests
pytest

# Frontend tests
cd ping-pub-explorer && npm test
```

## Commit Messages

Use conventional commit format:
- `feat:` new features
- `fix:` bug fixes
- `docs:` documentation changes
- `test:` test additions/changes
- `refactor:` code refactoring

## Review Process

1. All PRs require at least one approval
2. CI checks must pass
3. Maintainers may request changes
4. Squash merge into main

## Questions?

Open a discussion on GitHub or reach out to the maintainers.

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.
