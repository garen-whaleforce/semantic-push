# Strategy Engine API Service

S&P500 財報日回報策略引擎 API 服務。用於偵測財報日大跌的股票，自動產生進場/出場訊號，供 n8n 排程拉取並推送至 LINE。

## 策略規則

### 進場條件
- **Universe**: S&P500 成分股
- **條件**:
  1. 當天是該股票財報日
  2. 財報日當日報酬 (`close(asOf) / close(prevTradingDay) - 1`) 介於 **-30% ~ -5%**
  3. 用當天收盤價進場

### 出場條件
- **停損**: PnL <= -10% → 以收盤價出場
- **到期**: 持有 >= 50 個曆日 → 以收盤價出場

## 專案結構

```
semantic-push/
├── app/
│   ├── api/
│   │   └── routes.py          # FastAPI endpoints
│   ├── core/
│   │   └── config.py          # Pydantic settings
│   ├── db/
│   │   ├── database.py        # SQLAlchemy async setup
│   │   └── models.py          # ORM models
│   ├── models/
│   │   └── schemas.py         # Pydantic schemas
│   ├── services/
│   │   ├── fmp_client.py      # FMP API client
│   │   └── strategy_engine.py # Strategy logic
│   └── main.py                # FastAPI app entry
├── alembic/
│   ├── versions/
│   │   └── 001_initial_schema.py
│   └── env.py
├── tests/
│   ├── test_api.py
│   ├── test_fmp_client.py
│   └── test_strategy.py
├── alembic.ini
├── Dockerfile
├── pyproject.toml
└── README.md
```

## 環境變數

| 變數名稱 | 說明 | 範例 |
|---------|------|------|
| `FMP_API_KEY` | FMP API Key (Premium) | `your_fmp_api_key` |
| `DATABASE_URL` | PostgreSQL 連線字串 (asyncpg) | `postgresql+asyncpg://user:pass@host:5432/db` |
| `DEBUG` | Debug 模式 (選填) | `false` |
| `SP500_CACHE_TTL_HOURS` | SP500 清單快取時間 (選填) | `24` |

## 本機開發

### 1. 安裝相依套件

```bash
# 建立虛擬環境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安裝套件
pip install -e ".[dev]"
```

### 2. 設定環境變數

```bash
cp .env.example .env
# 編輯 .env 填入你的 FMP_API_KEY 和 DATABASE_URL
```

### 3. 執行資料庫 Migration

```bash
# 確保 PostgreSQL 已啟動並可連線
alembic upgrade head
```

### 4. 啟動服務

```bash
# 開發模式 (hot reload)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 或直接執行
python -m app.main
```

### 5. 執行測試

```bash
# 執行所有測試
pytest

# 執行測試並顯示覆蓋率
pytest --cov=app --cov-report=html
```

## API 端點

### Health Check
```http
GET /health
```
回傳：`{ "ok": true }`

### 執行每日掃描
```http
POST /jobs/daily?asOf=2025-01-15
```
- 執行指定日期的進場與出場掃描
- **冪等性**：重複執行同一天不會產生重複的 positions 或 alerts
- 回傳：
```json
{
  "as_of": "2025-01-15",
  "new_entry_alerts": 2,
  "new_exit_alerts": 1
}
```

### 取得待發送通知
```http
GET /alerts/pending?limit=200
```
- 回傳 `sent_at IS NULL` 的 alerts，按 `created_at` 升冪排序
- 回傳：
```json
[
  {
    "id": "uuid-...",
    "alert_type": "ENTRY",
    "symbol": "AAPL",
    "as_of": "2025-01-15",
    "message": "[ENTRY] AAPL 2025-01-15\nEarnings day return: -12.34%\nEntry price (close): 123.45"
  }
]
```

### 標記通知已發送
```http
POST /alerts/{id}/mark-sent
```
- **冪等性**：已標記的 alert 再次呼叫也會回傳 200
- 回傳：
```json
{
  "success": true,
  "id": "uuid-...",
  "sent_at": "2025-01-15T10:30:00Z"
}
```

## n8n 整合範例

### 工作流程設計

1. **Schedule Trigger**: 每日固定時間觸發（例如美股收盤後 UTC 22:00）
2. **HTTP Request**: `POST /jobs/daily?asOf={{$today}}`
3. **HTTP Request**: `GET /alerts/pending?limit=100`
4. **Loop**: 對每個 alert
   - **LINE Notify**: 發送 `message` 內容
   - **HTTP Request**: `POST /alerts/{id}/mark-sent`

### n8n HTTP Request 設定

```yaml
# 每日掃描
Method: POST
URL: https://your-zeabur-domain.zeabur.app/jobs/daily
Query Parameters:
  asOf: {{ $today.format('YYYY-MM-DD') }}

# 取得待發送通知
Method: GET
URL: https://your-zeabur-domain.zeabur.app/alerts/pending
Query Parameters:
  limit: 100

# 標記已發送
Method: POST
URL: https://your-zeabur-domain.zeabur.app/alerts/{{ $json.id }}/mark-sent
```

## Zeabur 部署

### 1. 建立 PostgreSQL 服務
在 Zeabur 控制台建立 PostgreSQL 服務，取得連線字串。

### 2. 部署應用
1. 連結 GitHub repo 或上傳程式碼
2. Zeabur 會自動偵測 Dockerfile 並建置
3. 設定環境變數：
   - `FMP_API_KEY`
   - `DATABASE_URL`（使用 Zeabur 提供的連線字串，記得加上 `+asyncpg`）

### 3. 執行 Migration
部署完成後，透過 Zeabur Console 或本機連線執行：
```bash
alembic upgrade head
```

## 資料庫 Schema

### positions
| 欄位 | 類型 | 說明 |
|------|------|------|
| id | UUID | PK |
| symbol | TEXT | 股票代碼 |
| entry_date | DATE | 進場日期 |
| entry_price | NUMERIC(18,6) | 進場價格 |
| status | TEXT | OPEN / CLOSED |
| exit_date | DATE | 出場日期 |
| exit_price | NUMERIC(18,6) | 出場價格 |
| exit_reason | TEXT | STOP_LOSS / TIME_EXIT |
| created_at | TIMESTAMPTZ | 建立時間 |
| updated_at | TIMESTAMPTZ | 更新時間 |

**唯一約束**: `(symbol, entry_date)`

### alerts
| 欄位 | 類型 | 說明 |
|------|------|------|
| id | UUID | PK |
| event_key | TEXT | 唯一事件識別碼 |
| alert_type | TEXT | ENTRY / EXIT |
| symbol | TEXT | 股票代碼 |
| as_of | DATE | 事件日期 |
| message | TEXT | LINE 推播訊息 |
| created_at | TIMESTAMPTZ | 建立時間 |
| sent_at | TIMESTAMPTZ | 已發送時間 |

**唯一約束**: `event_key`

### symbols_cache
| 欄位 | 類型 | 說明 |
|------|------|------|
| symbol | TEXT | PK, S&P500 成分股代碼 |
| updated_at | TIMESTAMPTZ | 快取更新時間 |

## Event Key 格式

確保冪等性的關鍵設計：

- **ENTRY**: `ENTRY|{symbol}|{entry_date}`
  - 例: `ENTRY|AAPL|2025-12-01`

- **EXIT**: `EXIT|{symbol}|{entry_date}|{exit_date}|{exit_reason}`
  - 例: `EXIT|AAPL|2025-12-01|2025-12-20|STOP_LOSS`

## 訊息格式

### 進場訊息
```
[ENTRY] AAPL 2025-12-01
Earnings day return: -12.34%
Entry price (close): 123.45
```

### 出場訊息
```
[EXIT-STOP_LOSS] AAPL 2025-12-20
PnL: -10.12%
Exit price (close): 111.11
Holding days: 19
```

## License

MIT
