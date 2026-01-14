# AI Engineering Bot Dashboard

Next.js dashboard for monitoring and analyzing bot PR fixes across Vector Institute repositories.

## Features

- **Overview Dashboard**: Summary metrics, success rates, recent PRs
- **Agent Observability**: Detailed traces of agent executions (tool calls, reasoning, actions)
- **Authentication**: Google OAuth restricted to @vectorinstitute.ai emails
- **GCS Integration**: Fetches data from Cloud Storage

## Development

```bash
# Install dependencies
npm install

# Run development server
npm run dev

# Visit http://localhost:3001/aieng-bot
```

## Environment Variables

Create `.env.local`:

```
NEXT_PUBLIC_GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
SESSION_SECRET=random_32_character_string
NEXT_PUBLIC_APP_URL=http://localhost:3001
REDIRECT_URI=http://localhost:3001/aieng-bot/api/auth/callback
ALLOWED_DOMAINS=vectorinstitute.ai
```

## Production Deployment

Deployed to GCP Cloud Run via `.github/workflows/deploy-dashboard.yml`:

```bash
# Manual deployment
gh workflow run deploy-dashboard.yml
```

**Production URL**: https://platform.vectorinstitute.ai/aieng-bot

## Architecture

- **Framework**: Next.js 15 with App Router
- **Auth**: Google OAuth 2.0 + Iron Session
- **Styling**: Tailwind CSS
- **Data Source**: GCS bucket (`gs://bot-dashboard-vectorinstitute/`)
- **Hosting**: Cloud Run (serverless containers)

## Data Flow

1. Bot fixes PR → generates trace JSON
2. Workflow uploads trace to GCS
3. Weekly workflow aggregates metrics
4. Dashboard fetches from GCS (client-side)
5. Mock data used if GCS unavailable (development)

## Key Files

- `app/page.tsx` - Main dashboard (protected)
- `app/login/page.tsx` - Login page
- `app/api/auth/*` - OAuth routes
- `lib/data-fetcher.ts` - GCS data fetching
- `lib/types.ts` - TypeScript definitions
- `lib/session.ts` - Session management
