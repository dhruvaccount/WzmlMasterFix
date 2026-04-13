# WZML-X Deployment Guide

## Overview

WZML-X is a scalable, API-first file processing platform v4.0.0 with modular architecture, supporting multiple clients (Telegram, Discord) and multiple database backends.

## Requirements

- Docker & Docker Compose
- MongoDB (included in docker-compose)
- Telegram Bot Token

## Quick Start

```bash
# Clone
git clone https://github.com/yourrepo/wzml-x.git
cd wzml-x

# Copy and edit config
cp config_sample.yml config.yml
# Edit config.yml with your settings

# Start with Docker
docker-compose up -d
```

## Configuration

### config.yml (Primary)

```bash
# Copy sample config
cp config_sample.yml config.yml

# Edit with your settings - see config_sample.yml for all options
```

### Environment Variables

All config.yml options can be set via environment variables:

```bash
# Required
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_API=12345
TELEGRAM_HASH=your_api_hash
TELEGRAM_OWNER_ID=123456789

# Database
DB_DATABASE_URL=mongodb://mongodb:27017

# API
LIMIT_API_PORT=8080
LIMIT_MAX_WORKERS=4
```

### All Environment Variables

| Prefix | Variables |
|--------|-----------|
| TELEGRAM_ | BOT_TOKEN, API, HASH, OWNER_ID, BASE_URL, BOT_USERNAME, TIMEZONE, DEFAULT_LANG, HYDRA_IP, HYDRA_API_KEY, USER_SESSION_STRING, HELPER_TOKENS, CMD_SUFFIX |
| DB_ | DATABASE_URL, MONGO_DB_NAME, DATABASE_CLIENT |
| LIMIT_ | MAX_WORKERS, API_HOST, API_PORT, DIRECT, MEGA, TORRENT, GD_DL, RC_DL, CLONE, JD, NZB, YTDLP, PLAYLIST, LEECH, EXTRACT, ARCHIVE, STORAGE, BOT_MAX_TASKS, USER_MAX_TASKS, STATUS_LIMIT, QUEUE_ALL, QUEUE_DOWNLOAD, QUEUE_UPLOAD |
| BOT_ | BOT_PM, SET_COMMANDS, INCOMPLETE_TASK_NOTIFIER |
| GDRIVE_ | GDRIVE_ID, GD_DESP, IS_TEAM_DRIVE, STOP_DUPLICATE, INDEX_URL, USE_SERVICE_ACCOUNTS |
| RCLONE_ | RCLONE_PATH, RCLONE_FLAGS, RCLONE_SERVE_URL, SHOW_CLOUD_LINK, RCLONE_SERVE_PORT, RCLONE_SERVE_USER, RCLONE_SERVE_PASS |
| MEGA_ | MEGA_EMAIL, MEGA_PASSWORD |
| JD_ | JD_EMAIL, JD_PASS |
| LEECH_ | LEECH_SPLIT_SIZE, AS_DOCUMENT, EQUAL_SPLITS, MEDIA_GROUP, USER_TRANSMISSION, HYBRID_LEECH, LEECH_PREFIX, LEECH_SUFFIX, DELETE_LINKS |
| LOG_ | LEECH_DUMP_CHAT, LINKS_LOG_ID, MIRROR_LOG_ID, CLEAN_LOG_MSG |
| RSS_ | RSS_DELAY, RSS_CHAT, RSS_SIZE_LIMIT |
| SEARCH_ | SEARCH_API_LINK, SEARCH_LIMIT, FILELION_API, STREAMWISH_API, INSTADL_API, EXCLUDED_EXTENSIONS |
| DISABLE_ | TORRENTS, LEECH, BULK, MULTI, SEED, FF_MODE |
| TELEGRAPH_ | AUTHOR_NAME, AUTHOR_URL |
| YT_ | YT_DESP, YT_TAGS, YT_CATEGORY_ID, YT_PRIVACY_STATUS |
| UPDATE_ | UPSTREAM_REPO, UPSTREAM_BRANCH, UPDATE_PKGS |

## Docker Deployment

### Quick Start

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f app

# Stop
docker-compose down
```

### Services

- **app**: WZML-X application (port 8080)
- **mongodb**: MongoDB database (port 27017)

### Volumes

```yaml
- ./downloads:/usr/src/app/downloads
- ./tokens:/usr/src/app/tokens
- ./accounts:/usr/src/app/accounts
- ./rclone:/usr/src/app/rclone
- ./thumbnails:/usr/src/app/thumbnails
```

### Healthchecks

Both app and MongoDB have healthchecks configured.

## API Endpoints

- `GET /` - API info
- `GET /health` - Health check
- `GET /docs` - Swagger docs
- `POST /tasks` - Create task
- `GET /tasks/{task_id}` - Get task status
- `POST /files` - Upload file
- `GET /status/queue` - Queue status

## Architecture

```
main.py              # Entry point
├── config/          # Configuration (yaml/env)
├── db/              # Database layer
├── core/            # Task, Pipeline, Executor, Queue
├── plugins/         # Downloaders, Uploaders, Processors
├── bots/            # Client adapters (Telegram, Discord)
└── api/             # REST API
```

## Plugins

### Downloaders
- `yt_dlp` - YouTube/audio downloads
- `qbit` - qBittorrent
- `aria2` - Aria2
- `mega` - Mega.nz
- `gdrive` - Google Drive

### Uploaders
- `telegram` - Telegram files
- `gdrive` - Google Drive

### Processors
- `zip` - Zip archive
- `unzip` - Extract archive
- `split` - Split files
- `merge` - Merge files

## Testing

```bash
# Run all tests
pytest tests/ -v
```

## Troubleshooting

### Bot Not Starting
- Check TELEGRAM_BOT_TOKEN is valid
- Check TELEGRAM_API and TELEGRAM_HASH

### Database Connection Failed
- Verify MongoDB is running: `docker-compose ps`
- Check DB_DATABASE_URL

### Permissions
- Ensure volumes have proper permissions
- Check docker logs: `docker-compose logs app`