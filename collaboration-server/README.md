# collaboration-server

Real-time collaborative editing server using Yjs and WebSocket.

## Tech Stack

- Node.js 20 / WebSocket / Yjs
- LevelDB (document state persistence)

## Port

- **1234** (internal)

## Features

- Real-time document synchronization via Yjs CRDT
- WebSocket-based multi-user editing
- JWT authentication
- LevelDB persistence for document state
- 30-minute idle timeout
- 10 max connections per document

## Configuration

Supports two methods:

1. **`.env` file** — Copy `.env.example` to `.env` and fill in values.
2. **HashiCorp Vault** — Delete `.env`, set `VAULT_ADDR` + auth credentials. The `vault_env_loader.js` module loads secrets from Vault at startup.

Key variables:

```env
PORT=1234
PERSISTENCE_DIR=./y-leveldb-storage
JWT_SECRET=your-secret
AUTH_SERVICE_URL=http://localhost:7004
```

## Local Development

```bash
npm install
npm start
```

## Docker

```bash
docker build -t collaboration-server .
docker run -p 1234:1234 --env-file .env collaboration-server
```

## Health Check

```
GET /health   — returns active room count
GET /stats    — per-room connection details
```
