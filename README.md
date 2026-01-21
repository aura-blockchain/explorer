# AURA Block Explorer

A full-featured block explorer for the AURA blockchain with real-time indexing, WebSocket updates, comprehensive search, and REST API.

## Features

- **Real-time Block Indexing**: Sub-100ms block processing
- **Transaction Tracking**: Full transaction history with decoding
- **Account Analytics**: Balance history, transaction counts, rich list
- **Validator Dashboard**: Staking info, uptime, commission
- **Search**: Blocks, transactions, addresses, validators
- **WebSocket**: Real-time updates for new blocks and transactions
- **REST API**: Comprehensive programmatic access
- **Export**: CSV/JSON export for transactions
- **Caching**: Redis-backed caching for performance
- **Rate Limiting**: Configurable per-endpoint limits

## Quick Start

### Docker Compose (Recommended)

```bash
# Clone repository
git clone https://github.com/aura-blockchain/explorer.git
cd explorer

# Configure
cp .env.example .env
# Edit .env with your node endpoints

# Start
docker-compose up -d

# View logs
docker-compose logs -f
```

### Local Development

```bash
# Prerequisites: Python 3.10+, pip

# Install dependencies
pip install -r requirements.txt

# Configure environment
export NODE_RPC_URL="http://localhost:26657"
export NODE_API_URL="http://localhost:1317"
export CHAIN_ID="aura-mvp-1"

# Run
python explorer_backend.py
```

The explorer runs on `http://localhost:8082` by default.

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `NODE_RPC_URL` | Cosmos RPC endpoint | `http://localhost:26657` |
| `NODE_API_URL` | Cosmos REST API endpoint | `http://localhost:1317` |
| `NODE_GRPC_URL` | gRPC endpoint (optional) | `localhost:9090` |
| `CHAIN_ID` | Chain identifier | `aura-mvp-1` |
| `DENOM` | Native token denom | `uaura` |
| `DENOM_DECIMALS` | Token decimals | `6` |
| `EXPLORER_PORT` | Server port | `8082` |
| `EXPLORER_HOST` | Bind address | `0.0.0.0` |
| `DB_PATH` | SQLite database path | `./explorer.db` |
| `CACHE_TTL_SHORT` | Short cache TTL (seconds) | `60` |
| `CACHE_TTL_MEDIUM` | Medium cache TTL | `300` |
| `CACHE_TTL_LONG` | Long cache TTL | `600` |
| `RATE_LIMIT_ENABLED` | Enable rate limiting | `true` |
| `RATE_LIMIT_PER_MINUTE` | Requests per minute | `60` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `ADMIN_API_KEY` | Admin endpoint API key | Required in production |

### Configuration Classes

The explorer supports multiple environments via `config.py`:

- **DevelopmentConfig**: Debug mode, in-memory DB
- **ProductionConfig**: Rate limiting, API key required
- **TestConfig**: Fast cache TTLs for testing

Set `EXPLORER_ENV` to `development`, `production`, or `test`.

## API Reference

### Blocks

```bash
# Get latest blocks
GET /api/blocks?limit=20

# Get block by height
GET /api/blocks/{height}

# Get block by hash
GET /api/blocks/hash/{hash}
```

### Transactions

```bash
# Get recent transactions
GET /api/transactions?limit=20

# Get transaction by hash
GET /api/transactions/{hash}

# Get transactions for address
GET /api/transactions/address/{address}?limit=50&offset=0

# Search transactions
GET /api/transactions/search?q=memo:payment
```

### Accounts

```bash
# Get account info
GET /api/accounts/{address}

# Get account balances
GET /api/accounts/{address}/balances

# Get account transactions
GET /api/accounts/{address}/transactions?limit=50

# Get rich list
GET /api/accounts/richlist?limit=100
```

### Validators

```bash
# Get all validators
GET /api/validators

# Get validator by address
GET /api/validators/{operator_address}

# Get validator delegations
GET /api/validators/{operator_address}/delegations

# Get validator uptime
GET /api/validators/{operator_address}/uptime
```

### Governance

```bash
# Get proposals
GET /api/governance/proposals

# Get proposal details
GET /api/governance/proposals/{proposal_id}

# Get proposal votes
GET /api/governance/proposals/{proposal_id}/votes
```

### Statistics

```bash
# Get chain statistics
GET /api/stats

# Get transaction volume
GET /api/stats/volume?period=24h

# Get price history (if oracle available)
GET /api/stats/price?period=7d
```

### Search

```bash
# Universal search (blocks, txs, addresses)
GET /api/search?q={query}

# Autocomplete
GET /api/search/autocomplete?q={prefix}
```

### Export

```bash
# Export transactions as CSV
GET /api/export/transactions/{address}?format=csv

# Export transactions as JSON
GET /api/export/transactions/{address}?format=json
```

### Health

```bash
# Health check
GET /health

# Detailed status
GET /api/status
```

## WebSocket API

Connect to real-time updates:

```javascript
const ws = new WebSocket('ws://localhost:8082/ws');

// Subscribe to new blocks
ws.send(JSON.stringify({
  action: 'subscribe',
  channel: 'blocks'
}));

// Subscribe to new transactions
ws.send(JSON.stringify({
  action: 'subscribe',
  channel: 'transactions'
}));

// Subscribe to specific address
ws.send(JSON.stringify({
  action: 'subscribe',
  channel: 'address',
  address: 'aura1...'
}));

// Handle messages
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('New event:', data);
};
```

## Architecture

```
┌─────────────────┐     ┌─────────────────┐
│   AURA Node     │────▶│    Indexer      │
│  (RPC/REST)     │     │                 │
└─────────────────┘     └────────┬────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │    SQLite DB    │
                        └────────┬────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
        ▼                        ▼                        ▼
┌───────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   REST API    │      │   WebSocket     │      │     Cache       │
│   (Flask)     │      │   (Real-time)   │      │    (Redis)      │
└───────────────┘      └─────────────────┘      └─────────────────┘
```

### Components

| Component | File | Description |
|-----------|------|-------------|
| Backend | `explorer_backend.py` | Main Flask application |
| Indexer | `indexer.py` | Block/transaction indexer |
| SDK Client | `cosmos_sdk_client.py` | Cosmos SDK API client |
| TX Decoder | `tx_decoder.py` | Transaction message decoder |
| Search API | `search_api.py` | Search functionality |
| WebSocket | `websocket.py` | Real-time updates |
| Cache | `cache.py` | Redis caching layer |
| Rate Limiter | `rate_limiting.py` | Request rate limiting |

## Database Schema

The explorer uses SQLite with the following tables:

```sql
-- Blocks
CREATE TABLE blocks (
  height INTEGER PRIMARY KEY,
  hash TEXT UNIQUE,
  time TIMESTAMP,
  proposer TEXT,
  tx_count INTEGER,
  size INTEGER
);

-- Transactions
CREATE TABLE transactions (
  hash TEXT PRIMARY KEY,
  height INTEGER,
  index INTEGER,
  type TEXT,
  sender TEXT,
  recipient TEXT,
  amount TEXT,
  fee TEXT,
  memo TEXT,
  status TEXT,
  time TIMESTAMP,
  raw_log TEXT
);

-- Accounts
CREATE TABLE accounts (
  address TEXT PRIMARY KEY,
  balance TEXT,
  tx_count INTEGER,
  first_seen TIMESTAMP,
  last_seen TIMESTAMP
);

-- Validators
CREATE TABLE validators (
  operator_address TEXT PRIMARY KEY,
  moniker TEXT,
  tokens TEXT,
  commission TEXT,
  status TEXT,
  jailed BOOLEAN
);
```

## Monitoring

### Prometheus Metrics

Available at `/metrics`:

- `explorer_blocks_indexed` - Total blocks indexed
- `explorer_transactions_indexed` - Total transactions indexed
- `explorer_api_requests_total` - API requests by endpoint
- `explorer_api_latency_seconds` - API response latency
- `explorer_cache_hits` - Cache hit rate
- `explorer_websocket_connections` - Active WebSocket connections

### Health Endpoints

```bash
# Basic health
curl http://localhost:8082/health

# Detailed status
curl http://localhost:8082/api/status
```

## Production Deployment

### Requirements

- Python 3.10+
- Redis 7+ (for caching)
- Nginx (reverse proxy)
- Systemd (process management)

### Systemd Service

```ini
[Unit]
Description=AURA Block Explorer
After=network.target

[Service]
Type=simple
User=explorer
WorkingDirectory=/opt/aura-explorer
Environment=EXPLORER_ENV=production
Environment=NODE_RPC_URL=http://sentry:26657
Environment=NODE_API_URL=http://sentry:1317
ExecStart=/opt/aura-explorer/venv/bin/python explorer_backend.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Nginx Configuration

```nginx
server {
    listen 80;
    server_name explorer.aurablockchain.org;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name explorer.aurablockchain.org;

    ssl_certificate /etc/letsencrypt/live/explorer.aurablockchain.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/explorer.aurablockchain.org/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8082;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /ws {
        proxy_pass http://127.0.0.1:8082;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

### Security Checklist

- [ ] Set `ADMIN_API_KEY` for admin endpoints
- [ ] Enable rate limiting in production
- [ ] Configure CORS for your domain
- [ ] Use HTTPS with valid certificates
- [ ] Set up firewall rules
- [ ] Enable log rotation
- [ ] Configure monitoring alerts

## Development

### Running Tests

```bash
# Unit tests
python -m pytest test_explorer.py

# API endpoint tests
python -m pytest test_api_endpoints.py

# Cache tests
python -m pytest test_cache.py
```

### Code Structure

```
aura-explorer/
├── explorer_backend.py    # Main Flask app
├── indexer.py             # Block indexer
├── cosmos_sdk_client.py   # Cosmos SDK client
├── tx_decoder.py          # Transaction decoder
├── search_api.py          # Search functionality
├── websocket.py           # WebSocket handler
├── websocket_manager.py   # WS connection manager
├── cache.py               # Redis cache layer
├── rate_limiting.py       # Rate limiter
├── tracing.py             # Distributed tracing
├── config.py              # Configuration
├── requirements.txt       # Python dependencies
└── tests/
    ├── test_explorer.py
    ├── test_api_endpoints.py
    └── test_cache.py
```

## Troubleshooting

### Common Issues

**"Connection refused to node"**
- Verify `NODE_RPC_URL` and `NODE_API_URL` are correct
- Check if node is running and synced
- Ensure firewall allows connections

**"Database locked"**
- Only one indexer should run at a time
- Check for zombie processes

**"High memory usage"**
- Reduce `RICHLIST_MAX_SIZE`
- Enable database pruning
- Increase cache TTLs

**"Slow API responses"**
- Enable Redis caching
- Check database indexes
- Review rate limiting settings

## Links

- [AURA Documentation](https://docs.aurablockchain.org)
- [Live Explorer](https://testnet-explorer.aurablockchain.org)
- [API Documentation](https://docs.aurablockchain.org/api/rest)
- [Discord Support](https://discord.gg/RwQ8pma6)
- [GitHub Issues](https://github.com/aura-blockchain/explorer/issues)

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.
