#!/bin/bash
cd ""/bin"
if [ -f .env ]; then
  export 
fi
if [ -z "" ]; then
  echo 'Error: TELEGRAM_BOT_TOKEN is not set.'
  echo 'Please add TELEGRAM_BOT_TOKEN=... to .env'
  exit 1
fi
echo 'Starting DERLENG TV Bot...'
python3 bot.py
