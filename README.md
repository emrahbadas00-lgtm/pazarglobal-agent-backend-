# Pazarglobal Agent Backend

Python agent backend implementing Agent Builder workflow from OpenAI.

## Architecture

```
WhatsApp (Twilio)
      ↓
WhatsApp Bridge (Railway)
      ↓
Agent Backend (this project) ← You are here
      ↓
MCP Server (Railway) → Supabase
```

## Features

- **RouterAgent**: Classifies user intent (create, update, delete, search, etc.)
- **CreateListingAgent**: Prepares new listing
- **PublishAgent**: Inserts listing to database
- **UpdateListingAgent**: Updates existing listings
- **DeleteListingAgent**: Deletes listings
- **SearchAgent**: Searches products
- **SmallTalkAgent**: Handles greetings
- **CancelAgent**: Cancels operations

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in:

```env
OPENAI_API_KEY=sk-proj-...
MCP_SERVER_URL=https://pazarglobal-production.up.railway.app
PORT=8000
```

### 3. Run Locally

```bash
uvicorn main:app --reload --port 8000
```

### 4. Test API

```bash
# Health check
curl http://localhost:8000

# Run agent
curl -X POST http://localhost:8000/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user_123",
    "message": "iPhone 13 satıyorum 25 bin TL",
    "conversation_history": []
  }'
```

## API Endpoints

### `POST /agent/run`

Run agent workflow.

**Request:**
```json
{
  "user_id": "string",
  "message": "string",
  "conversation_history": []
}
```

**Response:**
```json
{
  "response": "string",
  "intent": "create_listing",
  "success": true
}
```

## Deployment to Railway

### 1. Create GitHub Repo

```bash
git init
git add .
git commit -m "Initial commit: Agent backend"
git branch -M main
git remote add origin https://github.com/emrahbadas00-lgtm/pazarglobal-agent-backend.git
git push -u origin main
```

### 2. Deploy to Railway

1. Go to Railway dashboard
2. New Project → Deploy from GitHub
3. Select `pazarglobal-agent-backend` repo
4. Add environment variables:
   - `OPENAI_API_KEY`
   - `MCP_SERVER_URL`
5. Deploy!

### 3. Get Railway URL

Railway will give you: `https://pazarglobal-agent-backend-production.up.railway.app`

### 4. Update WhatsApp Bridge

Update WhatsApp bridge to call agent backend instead of OpenAI directly.

## How It Works

### Agent Flow

1. **User sends message** → WhatsApp Bridge receives
2. **Bridge calls Agent Backend** → `/agent/run` endpoint
3. **RouterAgent classifies intent** → Returns intent type
4. **Route to specialized agent** → Based on intent
5. **Agent calls MCP tools** → If needed (DB operations)
6. **Return response** → Back to WhatsApp Bridge → Twilio → User

### Example Flow: Create Listing

```
User: "iPhone 13 satıyorum 25 bin TL"
   ↓
RouterAgent: intent = "create_listing"
   ↓
CreateListingAgent:
   - Extracts: title="iPhone 13", price_text="25 bin TL"
   - Calls clean_price_tool(price_text="25 bin TL") → 25000
   - Shows preview
   ↓
Response: "📝 İlan önizlemesi:
📱 iPhone 13
💰 25,000 TL
✅ Onaylamak için 'onayla' yazın"
```

### Example Flow: Publish Listing

```
User: "onayla"
   ↓
RouterAgent: intent = "publish_listing"
   ↓
PublishAgent:
   - Checks conversation history for prepared listing
   - Calls insert_listing_tool(user_id, title, price, ...)
   ↓
MCP Server → Supabase INSERT
   ↓
Response: "✅ İlanınız başarıyla yayınlandı!"
```

## Tools

All tools are called via MCP Server HTTP endpoint:

```python
POST {MCP_SERVER_URL}/mcp/call-tool
{
  "tool_name": "insert_listing_tool",
  "arguments": {
    "user_id": "...",
    "title": "...",
    "price": 25000
  }
}
```

Available tools:
- `clean_price_tool`
- `insert_listing_tool`
- `update_listing_tool`
- `delete_listing_tool`
- `list_user_listings_tool`
- `search_listings_tool`

## Conversation State

Agent maintains conversation history to track:
- Prepared listings (before publish)
- Which listing to update/delete
- User context

History is passed in `conversation_history` array.

## Error Handling

- Tool call failures → Return friendly error message
- Missing fields → Ask user for missing info
- No listings found → Guide user to create one
- Timeout → Retry logic in MCP calls

## Testing

### Test RouterAgent

```bash
curl -X POST http://localhost:8000/agent/run \
  -d '{"user_id":"test","message":"merhaba","conversation_history":[]}'
# Should return: small_talk intent
```

### Test CreateListingAgent

```bash
curl -X POST http://localhost:8000/agent/run \
  -d '{"user_id":"test","message":"iPhone 13 satıyorum 25 bin TL","conversation_history":[]}'
# Should return: listing preview
```

### Test SearchAgent

```bash
curl -X POST http://localhost:8000/agent/run \
  -d '{"user_id":"test","message":"MacBook arıyorum","conversation_history":[]}'
# Should return: search results
```

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | `sk-proj-...` |
| `MCP_SERVER_URL` | MCP server base URL | `https://pazarglobal-production.up.railway.app` |
| `PORT` | Server port | `8000` |

## License

MIT

## Author

Emrah Badas
