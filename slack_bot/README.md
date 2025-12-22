# AI Engineering Maintenance Bot - Slack Integration

A Slack bot that provides information about the AI Engineering Maintenance Bot through slash commands.

## Features

- `/aieng-bot version` - Display version and metadata information about the bot
- Responds to @mentions with helpful information
- Rich formatted responses with links to repository and dashboard

## Prerequisites

- Python 3.12 or higher
- A Slack workspace where you have permission to install apps
- Access to the Slack API dashboard

## Installation Instructions

### Step 1: Create a Slack App

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps)
2. Click **"Create New App"**
3. Select **"From an app manifest"**
4. Choose your workspace from the dropdown
5. Click **"Next"**

### Step 2: Configure with Manifest

1. Select the **YAML** tab
2. Copy the contents of `manifest.yaml` from this directory
3. Paste it into the text field
4. Click **"Next"**
5. Review the configuration summary
6. Click **"Create"**

### Step 3: Enable Socket Mode

1. In your app settings, go to **"Socket Mode"** in the left sidebar
2. Toggle **"Enable Socket Mode"** to **On**
3. You'll be prompted to create an app-level token:
   - Token Name: `socket-token` (or any name you prefer)
   - Add scope: `connections:write`
4. Click **"Generate"**
5. **Copy the app-level token** (starts with `xapp-`) - you'll need this later
6. Click **"Done"**

### Step 4: Get Bot Token

1. In your app settings, go to **"OAuth & Permissions"** in the left sidebar
2. Under **"OAuth Tokens for Your Workspace"**, click **"Install to Workspace"**
3. Review the permissions and click **"Allow"**
4. **Copy the Bot User OAuth Token** (starts with `xoxb-`) - you'll need this later

### Step 5: Get Signing Secret

1. In your app settings, go to **"Basic Information"** in the left sidebar
2. Scroll down to **"App Credentials"**
3. **Copy the Signing Secret** - you'll need this later

### Step 6: Set Up Environment Variables

Create a `.env` file in the `slack_bot` directory with your tokens:

```bash
# Required for Slack bot
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_APP_TOKEN=xapp-your-app-level-token-here
SLACK_SIGNING_SECRET=your-signing-secret-here
```

**Important:** Never commit the `.env` file to version control. Add it to `.gitignore`.

### Step 7: Install Dependencies

This project uses [uv](https://github.com/astral-sh/uv) for dependency management:

```bash
cd slack_bot
uv sync
```

### Step 8: Run the Bot

```bash
python app.py
```

You should see:
```
⚡️ AI Engineering Maintenance Bot is running!
```

## Usage

Once the bot is running and installed in your workspace:

### Slash Command

In any Slack channel where the bot is present:

```
/aieng-bot version
```

This will display:
- Bot version
- Project name and description
- Links to the GitHub repository
- Link to the dashboard

### Mention the Bot

You can also mention the bot in a channel:

```
@AI Engineering Maintenance Bot
```

The bot will respond with usage instructions.

## Deployment

### Running as a Service

For production use, you should run the bot as a systemd service or in a container.

#### Docker (Recommended)

Create a `Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml .

# Install dependencies
RUN uv pip install --system -e .

# Copy application
COPY app.py .

CMD ["python", "app.py"]
```

Build and run:

```bash
docker build -t aieng-bot-slack .
docker run -d --name aieng-bot-slack \
  --env-file .env \
  aieng-bot-slack
```

#### Systemd Service

Create `/etc/systemd/system/aieng-bot-slack.service`:

```ini
[Unit]
Description=AI Engineering Maintenance Bot Slack Integration
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/aieng-bot-maintain/slack_bot
Environment="SLACK_BOT_TOKEN=xoxb-your-token"
Environment="SLACK_APP_TOKEN=xapp-your-token"
Environment="SLACK_SIGNING_SECRET=your-secret"
ExecStart=/usr/bin/python3 app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable aieng-bot-slack
sudo systemctl start aieng-bot-slack
```

## Troubleshooting

### Bot doesn't respond to commands

1. Check that the bot is running (`python app.py` should show "⚡️ AI Engineering Maintenance Bot is running!")
2. Verify Socket Mode is enabled in your app settings
3. Confirm all environment variables are set correctly
4. Check that the app is installed in your workspace

### "Invalid token" errors

- Make sure you're using the correct token types:
  - `SLACK_BOT_TOKEN` should start with `xoxb-`
  - `SLACK_APP_TOKEN` should start with `xapp-`
- Regenerate tokens if needed from the Slack API dashboard

### Command not found in Slack

1. Go to your app settings → Slash Commands
2. Verify `/aieng-bot` is listed
3. Try reinstalling the app to your workspace

## Security Notes

- **Never commit tokens or secrets to version control**
- Add `.env` to your `.gitignore` file
- Use environment variables or a secrets manager for production deployments
- Rotate tokens regularly following your organization's security policies
- Limit app installation to only necessary workspaces

## Architecture

The bot uses:
- **Slack Bolt for Python** - Official Slack framework for building apps
- **Socket Mode** - Eliminates need for public URLs and webhook endpoints
- **aieng-bot-maintain package** - Imports version information from the main project

## Links

- [Slack API Documentation](https://api.slack.com/)
- [Slack Bolt Python Documentation](https://docs.slack.dev/tools/bolt-python/)
- [Socket Mode Guide](https://api.slack.com/apis/connections/socket)
- [App Manifests Reference](https://api.slack.com/reference/manifests)

## Support

For issues or questions:
- Open an issue at [GitHub Issues](https://github.com/VectorInstitute/aieng-bot-maintain/issues)
- Check the main project [README](../README.md)
- Review the [CLAUDE.md](../CLAUDE.md) for project architecture details
