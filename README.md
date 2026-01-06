# Explorer

Block explorer service for Aura.

## Run locally

```bash
cd explorer
pip install -r requirements.txt
export NODE_RPC_URL="http://localhost:26657"
export NODE_API_URL="http://localhost:1317"
export CHAIN_ID="aura-testnet-1"
python explorer_backend.py
```

The service listens on `http://localhost:8082` by default.
