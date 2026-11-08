#!/usr/bin/env python3
import os, sys, json, time
import urllib.request, urllib.parse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHANNELS_FILE = os.path.join(BASE_DIR, 'channels.json')
ENV_FILE = os.path.join(BASE_DIR, '.env')

BOT_TOKEN = ''
if os.path.exists(ENV_FILE):
    with open(ENV_FILE) as ef:
        for line in ef:
            if line.startswith('TELEGRAM_BOT_TOKEN='):
                BOT_TOKEN = line.split('=', 1)[1].strip()

if not BOT_TOKEN:
    BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')

WEBAPP_URL = os.environ.get('TELEGRAM_WEBAPP_URL', '')
TELEGRAM_API = f'https://api.telegram.org/bot{BOT_TOKEN}'

def load_channels():
    if os.path.exists(CHANNELS_FILE):
        with open(CHANNELS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

CHANNELS = load_channels()

def api_request(method, payload):
    if not BOT_TOKEN:
        return None
    url = f'{TELEGRAM_API}/{method}'
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        print(f'API Error ({method}): {e}')
        return None

def send_message(chat_id, text, reply_markup=None):
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    return api_request('sendMessage', payload)

def send_main_menu(chat_id):
    nl = chr(10)
    welcome_text = '📺 <b>Welcome to DERLENG TV Bot!</b>' + nl + nl + 'Watch 6,100+ live functional channels directly inside Telegram, including <b>Cambodian National TV</b>, 24/7 Global News, Sports, and Movies.' + nl + nl + '👇 Select a category below to browse channels:'
    keyboard = []
    if WEBAPP_URL:
        keyboard.append([{'text': '▶️ Open Live TV Player (Mini App)', 'web_app': {'url': WEBAPP_URL}}])
    keyboard.extend([
        [{'text': '🇰🇭 Cambodia Channels (12 Live)', 'callback_data': 'cat_Cambodia'}],
        [{'text': '⚽ Sports Channels', 'callback_data': 'cat_Sports'}, {'text': '📰 News Channels', 'callback_data': 'cat_News'}],
        [{'text': '🎬 Movies & Cinema', 'callback_data': 'cat_Movies'}, {'text': '🎵 Music Channels', 'callback_data': 'cat_Music'}],
        [{'text': '📊 Channel Stats', 'callback_data': 'all_info'}]
    ])
    send_message(chat_id, welcome_text, {'inline_keyboard': keyboard})

def handle_callback(cb_query):
    query_id = cb_query['id']
    chat_id = cb_query['message']['chat']['id']
    data = cb_query.get('data', '')
    api_request('answerCallbackQuery', {'callback_query_id': query_id})
    nl = chr(10)
    if data.startswith('cat_'):
        cat = data.replace('cat_', '')
        if cat == 'Cambodia':
            matches = [c for c in CHANNELS if c.get('country') == 'KH' or c.get('group') == 'Cambodia']
        else:
            matches = [c for c in CHANNELS if c.get('genre') == cat]
        text = f'📺 <b>{cat} Channels ({len(matches)} Available)</b>' + nl + 'Tap to watch:'
        kb = []
        for ch in matches[:10]:
            kb.append([{'text': f"▶️ {ch['name']}", 'url': ch['url']}])
        kb.append([{'text': '⬅️ Back to Main Menu', 'callback_data': 'main_menu'}])
        send_message(chat_id, text, {'inline_keyboard': kb})
    elif data == 'main_menu':
        send_main_menu(chat_id)
    elif data == 'all_info':
        text = f'📊 <b>Total Functional Channels:</b> {len(CHANNELS)}' + nl + '• <b>Cambodia:</b> 12 channels' + nl + '• <b>Sports:</b> 81 channels' + nl + '• <b>News:</b> 258 channels' + nl + '• <b>Movies:</b> 233 channels' + nl + '• <b>Entertainment:</b> 5,300+ channels'
        kb = [[{'text': '⬅️ Back to Main Menu', 'callback_data': 'main_menu'}]]
        send_message(chat_id, text, {'inline_keyboard': kb})

def run_bot():
    if not BOT_TOKEN:
        print('Error: TELEGRAM_BOT_TOKEN not found in .env or environment.')
        return
    print('[*] DERLENG TV Bot is running! Listening for updates on Telegram...')
    offset = 0
    while True:
        try:
            updates = api_request('getUpdates', {'offset': offset, 'timeout': 20})
            if updates and updates.get('ok') and updates.get('result'):
                for u in updates['result']:
                    offset = u['update_id'] + 1
                    if 'message' in u:
                        msg = u['message']
                        chat_id = msg['chat']['id']
                        text = msg.get('text', '')
                        if text.startswith('/start'):
                            send_main_menu(chat_id)
                    elif 'callback_query' in u:
                        handle_callback(u['callback_query'])
            time.sleep(1)
        except KeyboardInterrupt:
            print('Bot stopped by user.')
            break
        except Exception as e:
            print(f'Polling error: {e}')
            time.sleep(3)

if __name__ == '__main__':
    run_bot()
