# Quickstart: OI Regime Lab v0

**Date**: 2026-04-26
**Feature**: 001-oi-regime-lab

## Prerequisites

- Python 3.11 or higher
- Node.js 18 or higher
- npm or yarn
- Git

## Setup

### 1. Clone the repository

```bash
git clone <repository-url>
cd elpis
git checkout feature/001-oi-regime-lab
```

### 2. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -e .

# Verify installation
python -c "import fastapi; import polars; import duckdb; print('Backend dependencies installed')"
```

### 3. Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Verify installation
npm run build
```

### 4. Create data directories

```bash
# From repository root
mkdir -p data/raw data/processed data/reports
```

## Running the Application

### 1. Start Backend Server

```bash
cd backend
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`
API documentation at `http://localhost:8000/docs`

### 2. Start Frontend Server

```bash
cd frontend
npm run dev
```

The dashboard will be available at `http://localhost:3000`

### 3. Download Data

Using curl:
```bash
curl -X POST http://localhost:8000/api/v1/download \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTCUSDT", "interval": "15m", "days": 30}'
```

Or using the dashboard:
1. Open `http://localhost:3000`
2. Click "Download Data" button
3. Wait for download to complete

### 4. Process Data

Using curl:
```bash
curl -X POST http://localhost:8000/api/v1/process \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTCUSDT", "interval": "15m"}'
```

Or using the dashboard:
1. Click "Process Data" button
2. Wait for processing to complete

### 5. View Results

Open `http://localhost:3000` in your browser to see:
- Candlestick chart with range levels
- Open interest chart
- Funding rate chart
- Volume chart
- Regime labels
- Data quality panel

## API Usage Examples

### Get OHLCV Data

```bash
curl "http://localhost:8000/api/v1/market-data/ohlcv?symbol=BTCUSDT&interval=15m&limit=100"
```

### Get Features

```bash
curl "http://localhost:8000/api/v1/features?symbol=BTCUSDT&interval=15m&limit=100"
```

### Get Regimes

```bash
curl "http://localhost:8000/api/v1/regimes?symbol=BTCUSDT&interval=15m&regime=BREAKOUT_UP"
```

### Get Data Quality

```bash
curl "http://localhost:8000/api/v1/data-quality?symbol=BTCUSDT"
```

## Testing

### Backend Tests

```bash
cd backend
pytest tests/ -v
```

### Frontend Tests

```bash
cd frontend
npm test
```

## Troubleshooting

### Binance API Rate Limit

If you see 429 errors, wait 1 minute and try again. The system implements exponential backoff.

### Missing Data

Check data quality endpoint:
```bash
curl "http://localhost:8000/api/v1/data-quality?symbol=BTCUSDT"
```

If missing timestamps are high, re-download data:
```bash
curl -X POST http://localhost:8000/api/v1/download \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTCUSDT", "interval": "15m", "days": 30}'
```

### DuckDB Errors

Delete the DuckDB file and reprocess:
```bash
rm data/elpis.duckdb
curl -X POST http://localhost:8000/api/v1/process \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTCUSDT", "interval": "15m"}'
```

### Frontend Not Loading

1. Check backend is running: `curl http://localhost:8000/health`
2. Check browser console for errors
3. Restart frontend: `npm run dev`

## Configuration

### Backend Configuration

Create `backend/.env` file:
```env
# Binance API
BINANCE_BASE_URL=https://fapi.binance.com
BINANCE_RATE_LIMIT=1200

# Data paths
DATA_RAW_PATH=data/raw
DATA_PROCESSED_PATH=data/processed
DATA_DUCKDB_PATH=data/elpis.duckdb

# Feature computation
ATR_PERIOD=14
RANGE_PERIOD=20
VOLUME_RATIO_PERIOD=20
```

### Frontend Configuration

Create `frontend/.env.local` file:
```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

## Development

### Adding New Features

1. Create feature branch
2. Add tests
3. Implement feature
4. Run tests
5. Submit pull request

### Code Style

Backend:
- Black for formatting
- isort for imports
- mypy for type checking

Frontend:
- Prettier for formatting
- ESLint for linting
- TypeScript strict mode

### Project Structure

```
backend/
├── src/
│   ├── main.py          # FastAPI app
│   ├── config.py        # Configuration
│   ├── models/          # Pydantic models
│   ├── services/        # Business logic
│   ├── repositories/    # Data access
│   └── api/             # API routes
└── tests/

frontend/
├── src/
│   ├── app/             # Next.js pages
│   ├── components/      # React components
│   ├── services/        # API client
│   ├── hooks/           # React hooks
│   └── types/           # TypeScript types
└── tests/

data/
├── raw/                 # Raw Parquet files
├── processed/           # Processed features
├── reports/             # Generated reports
└── elpis.duckdb         # DuckDB database
```

## Next Steps

After v0 is working:

1. Add more symbols (ETHUSDT, etc.)
2. Add more timeframes (1h, 4h, 1d)
3. Add more features (RSI, MACD, Bollinger Bands)
4. Add backtesting engine
5. Add parameter optimization
6. Add export functionality
7. Add historical data comparison

## Support

For issues or questions:
1. Check the troubleshooting section
2. Review API documentation at `/docs`
3. Check data quality endpoint
4. Review logs in console
