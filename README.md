# CodeCritique Backend

AI-Powered Code Mentorship Platform - FastAPI Backend

## 🚀 Quick Start

### Prerequisites
- Python 3.9+
- Supabase account
- GitHub OAuth App
- Anthropic API key

### Setup

1. **Clone and install dependencies**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Configure environment variables**
```bash
cp .env.example .env
# Edit .env with your actual credentials
```

3. **Set up Supabase**
- Create project at https://supabase.com
- Go to SQL Editor
- Run `database_schema.sql`
- Copy project URL and anon key to `.env`

4. **Create GitHub OAuth App**
- Go to https://github.com/settings/developers
- New OAuth App
- Homepage URL: `http://localhost:3000`
- Callback URL: `http://localhost:3000/auth/callback`
- Copy Client ID and Secret to `.env`

5. **Get Anthropic API Key**
- Go to https://console.anthropic.com/
- Create API key
- Add to `.env`

6. **Run the server**
```bash
uvicorn main:app --reload --port 8000
```

API will be available at `http://localhost:8000`

## 📚 API Documentation

Once running:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 🔑 API Endpoints

### Authentication
- `POST /auth/github/callback` - GitHub OAuth callback

### User
- `GET /user/me` - Get current user
- `GET /user/stats` - Get user statistics

### Repositories
- `GET /repositories` - Get user's GitHub repos

### Reviews
- `POST /reviews` - Create new review
- `GET /reviews` - Get all user reviews
- `GET /reviews/{id}` - Get specific review

### Health
- `GET /` - API info
- `GET /health` - Health check

## 📂 Project Structure

```
codecritique-backend/
├── main.py              # FastAPI application
├── models.py            # Pydantic models
├── database.py          # Database operations
├── github_service.py    # GitHub API integration
├── ai_service.py        # AI code analysis
├── auth.py              # JWT authentication
├── requirements.txt     # Dependencies
├── .env                 # Environment variables (create from .env.example)
├── .env.example         # Environment template
├── database_schema.sql  # Database setup
└── README.md           # This file
```

## 🔧 Environment Variables

| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_KEY` | Supabase anon key |
| `GITHUB_CLIENT_ID` | GitHub OAuth Client ID |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth Secret |
| `ANTHROPIC_API_KEY` | Anthropic/Claude API key |
| `JWT_SECRET` | Secret for JWT signing |

## 🧪 Testing

Test the API:
```bash
# Health check
curl http://localhost:8000/health

# API docs
open http://localhost:8000/docs
```

## 🐳 Docker (Optional)

```bash
docker build -t codecritique-backend .
docker run -p 8000:8000 --env-file .env codecritique-backend
```

## 🚨 Troubleshooting

**"Module not found" errors**
```bash
pip install -r requirements.txt
```

**"Database connection failed"**
- Check Supabase URL and key in `.env`
- Ensure SQL schema was run
- Verify RLS policies are correct

**"GitHub OAuth failed"**
- Verify callback URL matches
- Check Client ID and Secret

**"AI review timeout"**
- Large repos take 30-60 seconds
- Check Anthropic API key
- Review processes in background

## 📝 Development

```bash
# Run with auto-reload
uvicorn main:app --reload --port 8000

# Format code
black .

# Type checking
mypy .
```

## 🚀 Deployment

### Railway / Render / Fly.io
1. Set environment variables in dashboard
2. Deploy from GitHub
3. Update GitHub OAuth callback URL

### AWS / Google Cloud
1. Use Docker container
2. Set environment variables
3. Configure load balancer + SSL

## 📄 License

MIT License

## 🤝 Contributing

This is a learning project - feel free to fork and improve!

## 💬 Support

For issues:
- Check `/docs` endpoint
- Review logs
- Open GitHub issue