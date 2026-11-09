#!/usr/bin/env python3
import os, sys, json, time, math
import urllib.request, urllib.parse, urllib.error
import html
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHANNELS_FILE = os.environ.get('DERLENG_CATALOG_FILE', os.path.join(BASE_DIR, 'dist', 'hostinger', 'channels_public.json'))
ENV_FILE = os.path.join(BASE_DIR, '.env')

PAGE_SIZE = 8

def get_env_config():
    token = ''
    app_url = ''
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, 'r', encoding='utf-8') as ef:
            for line in ef:
                if line.startswith('TELEGRAM_BOT_TOKEN='):
                    token = line.split('=', 1)[1].strip()
                elif line.startswith('TELEGRAM_WEBAPP_URL='):
                    app_url = line.split('=', 1)[1].strip()
                elif line.startswith('MINI_APP_URL=') and not app_url:
                    app_url = line.split('=', 1)[1].strip()
    if not token:
        token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    if not app_url:
        app_url = os.environ.get('TELEGRAM_WEBAPP_URL', '') or os.environ.get('MINI_APP_URL', '')
    return token, app_url

BOT_TOKEN, WEBAPP_URL = get_env_config()
TELEGRAM_API = f'https://api.telegram.org/bot{BOT_TOKEN}'

def load_channels():
    """Consume only the published compact catalog; never fall back to raw sources."""
    try:
        with open(CHANNELS_FILE, 'r', encoding='utf-8') as f:
            published = json.load(f)
        if not isinstance(published, list):
            return []
        return [{'id': c['id'], 'name': c['n'], 'url': c['u'],
                 'group': c.get('g', ''), 'genre': c.get('t', ''), 'country': c.get('c', '')}
                for c in published if isinstance(c, dict) and
                re.fullmatch(r'[a-zA-Z0-9_-]{8,64}', str(c.get('id', ''))) and
                isinstance(c.get('n'), str) and isinstance(c.get('u'), str) and
                c['u'].startswith(('http://', 'https://'))]
    except (OSError, ValueError):
        return []

CHANNELS = load_channels()

def api_request(method, payload):
    """Bound explicit rate-limit retries; avoid duplicating sends after ambiguous I/O."""
    token, _ = get_env_config()
    if not token:
        return {'ok': False, 'error_code': 0, 'description': 'Missing bot credential'}
    url = f'https://api.telegram.org/bot{token}/{method}'
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=35) as r:
                result = json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            try:
                result = json.loads(exc.read(65536).decode('utf-8'))
            except (ValueError, UnicodeError):
                result = {'ok': False, 'error_code': exc.code, 'description': 'HTTP failure'}
        except Exception as exc:
            # Never log request URLs: they contain the bot credential.
            return {'ok': False, 'error_code': 0, 'description': type(exc).__name__}
        if not isinstance(result, dict):
            return {'ok': False, 'error_code': 0, 'description': 'Invalid API response'}
        if result.get('ok') is True:
            return result
        retry_after = result.get('parameters', {}).get('retry_after', 1)
        if result.get('error_code') != 429 or attempt == 2:
            return result
        try:
            delay = max(1, float(retry_after))
        except (TypeError, ValueError):
            delay = 1
        if delay > 30:
            return result  # Do not retry earlier than Telegram permits.
        time.sleep(delay)
    return result

def send_message(chat_id, text, reply_markup=None):
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': True}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    return api_request('sendMessage', payload)

def edit_message(chat_id, message_id, text, reply_markup=None):
    payload = {'chat_id': chat_id, 'message_id': message_id, 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': True}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    return api_request('editMessageText', payload)

BANNER_FILE_ID_CACHE = {}

def send_photo_multipart(chat_id, filepath, caption=None, reply_markup=None):
    global BANNER_FILE_ID_CACHE
    token, _ = get_env_config()
    if not token:
        return None
    url = f'https://api.telegram.org/bot{token}/sendPhoto'
    boundary = f'----WebKitFormBoundary{int(time.time()*1000)}'

    parts = []
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode('utf-8'))
    if caption:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'.encode('utf-8'))
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="parse_mode"\r\n\r\nHTML\r\n'.encode('utf-8'))
    if reply_markup:
        rm_str = json.dumps(reply_markup)
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="reply_markup"\r\n\r\n{rm_str}\r\n'.encode('utf-8'))

    filename = os.path.basename(filepath)
    try:
        with open(filepath, 'rb') as f:
            file_bytes = f.read()
    except Exception as e:
        print(f'Error reading banner file {filepath}: {e}')
        return None

    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="{filename}"\r\nContent-Type: image/png\r\n\r\n'.encode('utf-8') + file_bytes + b'\r\n')
    parts.append(f'--{boundary}--\r\n'.encode('utf-8'))
    body = b''.join(parts)

    req = urllib.request.Request(url, data=body, headers={
        'Content-Type': f'multipart/form-data; boundary={boundary}',
        'Content-Length': str(len(body))
    })
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            res = json.loads(r.read().decode('utf-8'))
            if res and res.get('ok') and res.get('result', {}).get('photo'):
                photos = res['result']['photo']
                cache_key = 'welcome' if 'welcome' in filename.lower() else ('start' if 'start' in filename.lower() else filename)
                BANNER_FILE_ID_CACHE[cache_key] = photos[-1]['file_id']
            return res
    except Exception as e:
        print(f'send_photo_multipart Error: {type(e).__name__}')
        return None

def send_photo(chat_id, photo_source, caption=None, reply_markup=None):
    global BANNER_FILE_ID_CACHE
    src_str = str(photo_source).lower()
    cache_key = 'welcome' if 'welcome' in src_str else ('start' if 'start' in src_str else None)

    # 1. Use cached Telegram file_id if available (instant delivery)
    if cache_key and cache_key in BANNER_FILE_ID_CACHE:
        payload = {'chat_id': chat_id, 'photo': BANNER_FILE_ID_CACHE[cache_key]}
        if caption:
            payload['caption'] = caption
            payload['parse_mode'] = 'HTML'
        if reply_markup:
            payload['reply_markup'] = reply_markup
        res = api_request('sendPhoto', payload)
        if res and res.get('ok'):
            return res

    # 2. If photo_source is a local file, upload via multipart
    if isinstance(photo_source, str) and os.path.isfile(photo_source) and not photo_source.startswith('http'):
        res = send_photo_multipart(chat_id, photo_source, caption, reply_markup)
        if res and res.get('ok'):
            return res

    # 3. If photo_source is URL, let Telegram fetch it
    payload = {'chat_id': chat_id, 'photo': photo_source}
    if caption:
        payload['caption'] = caption
        payload['parse_mode'] = 'HTML'
    if reply_markup:
        payload['reply_markup'] = reply_markup
    res = api_request('sendPhoto', payload)
    if res and res.get('ok'):
        if res.get('result', {}).get('photo') and cache_key:
            BANNER_FILE_ID_CACHE[cache_key] = res['result']['photo'][-1]['file_id']
        return res

    # 4. Fallback to standard message if image sending fails
    return send_message(chat_id, caption or '', reply_markup)

def build_main_keyboard(app_url):
    kb = []
    # Hero Full-Width Button
    if app_url:
        kb.append([{'text': '🚀 បើកទស្សនា DERLENG TV', 'web_app': {'url': app_url}}])

    # Featured Cambodia Button
    kb.append([{'text': '🇰🇭 ប៉ុស្តិ៍ជាតិកម្ពុជា (១២ ប៉ុស្តិ៍)', 'callback_data': 'cat_Cambodia_0'}])

    # 2-Column Category Grid with Kids category
    kb.append([
        {'text': '🧸 កុមារ & តុក្កតា (៧០)', 'callback_data': 'cat_Kids_0'},
        {'text': '⚽ កីឡាផ្សាយផ្ទាល់ (៨១)', 'callback_data': 'cat_Sports_0'}
    ])
    kb.append([
        {'text': '📰 ព័ត៌មាន ២៤/៧ (២៥៨)', 'callback_data': 'cat_News_0'},
        {'text': '🎬 ភាពយន្ត & កុន (២៣៣)', 'callback_data': 'cat_Movies_0'}
    ])
    kb.append([
        {'text': '📚 ភាពយន្តឯកសារ (១៨)', 'callback_data': 'cat_Documentary_0'},
        {'text': '🌍 ប៉ុស្តិ៍ផ្សាយទាំងអស់', 'callback_data': 'cat_ALL_0'}
    ])
    kb.append([
        {'text': '🔍 របៀបស្វែងរក', 'callback_data': 'nav_search'},
        {'text': '📊 ស្ថិតិប៉ុស្តិ៍', 'callback_data': 'nav_stats'}
    ])

    # Utility Row
    kb.append([
        {'text': '❓ ជំនួយ & របៀបមើល', 'callback_data': 'nav_help'}
    ])
    return {'inline_keyboard': kb}

def send_welcome_banner(chat_id):
    nl = chr(10)
    welcome_text = (
        '📺 <b>សូមស្វាគមន៍មកកាន់ DERLENG TV!</b>' + nl + nl +
        'ទស្សនាប៉ុស្តិ៍ទូរទស្សន៍ផ្សាយបន្តផ្ទាល់ជាង ៦,១០០+ ប៉ុស្តិ៍ដោយផ្ទាល់នៅលើ Telegram រួមមានប៉ុស្តិ៍ជាតិកម្ពុជា កុមារ និងតុក្កតា កីឡាផ្សាយផ្ទាល់ ព័ត៌មាន ២៤/៧ និងភាពយន្តជាច្រើនទៀត។' + nl + nl +
        '<b>លក្ខណៈពិសេស៖</b>' + nl +
        '• ចុចម្តងដើម្បីបើកទិដ្ឋភាពពេញអេក្រង់ផ្ដេកកម្រិតភាពយន្ត (Landscape Cinema Mode)' + nl +
        '• ការផ្សាយផ្ទាល់ល្បឿនលឿនកម្រិត HLS មិនទាក់ មិនកន្ត្រាក់' + nl +
        '• ការស្វែងរកប៉ុស្តិ៍រហ័ស និងបែងចែកតាមប្រភេទច្បាស់លាស់'
    )

    local_welcome = os.path.join(BASE_DIR, 'welcome_banner.png')
    if not os.path.isfile(local_welcome):
        local_welcome = os.path.join(BASE_DIR, 'welcome banner.png')

    _, app_url = get_env_config()
    if os.path.isfile(local_welcome):
        return send_photo(chat_id, local_welcome, welcome_text)
    elif app_url:
        banner_url = f"{app_url.rstrip('/')}/welcome_banner.png"
        return send_photo(chat_id, banner_url, welcome_text)
    else:
        return send_message(chat_id, welcome_text)

def send_main_menu(chat_id):
    _, app_url = get_env_config()
    nl = chr(10)

    welcome_text = (
        '📺 <b>DERLENG TV</b> • <i>ផ្សាយបន្តផ្ទាល់កម្រិត HD</i>' + nl + nl +
        f'ទស្សនា <b>ប៉ុស្តិ៍ក្នុងបញ្ជី {len(CHANNELS):,} ប៉ុស្តិ៍</b> ដោយផ្ទាល់នៅលើ Telegram ជាមួយប្រព័ន្ធសំឡេងច្បាស់ និងទិដ្ឋភាពពេញអេក្រង់ផ្ដេក (Landscape Cinema Mode)។' + nl + nl +
        '🌟 <b>ប៉ុស្តិ៍ពិសេសៗ៖</b>' + nl +
        '• 🇰🇭 <b>ប៉ុស្តិ៍ជាតិកម្ពុជា</b> (TVK, Town Full HDTV, Fresh News, BTV...)' + nl +
        '• 🧸 <b>កុមារ និងតុក្កតា</b> (LEGO TV, Mattel Junior, Animation...)' + nl +
        '• ⚽ <b>បណ្ដាញកីឡាផ្សាយបន្តផ្ទាល់</b> (beIN, FloSports, Racing, Golf...)' + nl +
        '• 📰 <b>ព័ត៌មានទាន់ហេតុការណ៍សកល</b> (Al Jazeera, BBC, CBS, Bloomberg...)' + nl +
        '• 🎬 <b>ភាពយន្ត ឯកសារ និងតន្ត្រី</b>' + nl + nl +
        '👇 <i>សូមចុចប៊ូតុងខាងក្រោមដើម្បីបើកកម្មវិធី ឬជ្រើសរើសប៉ុស្តិ៍៖</i>'
    )

    keyboard = build_main_keyboard(app_url)
    local_banner = os.path.join(BASE_DIR, 'start_banner.png')
    if not os.path.isfile(local_banner):
        local_banner = os.path.join(BASE_DIR, 'start banner.png')

    if os.path.isfile(local_banner):
        send_photo(chat_id, local_banner, welcome_text, keyboard)
    elif app_url:
        banner_url = f"{app_url.rstrip('/')}/start_banner.png"
        send_photo(chat_id, banner_url, welcome_text, keyboard)
    else:
        send_message(chat_id, welcome_text, keyboard)

def get_category_channels(cat):
    if cat == 'Cambodia':
        return [c for c in CHANNELS if c.get('country') == 'KH' or c.get('group') == 'Cambodia']
    elif cat == 'Kids':
        return [c for c in CHANNELS if c.get('genre') == 'Kids' or 'kid' in c.get('name', '').lower() or 'cartoon' in c.get('name', '').lower()]
    elif cat == 'ALL':
        return CHANNELS
    else:
        return [c for c in CHANNELS if c.get('genre') == cat]

def build_category_view(cat, page=0):
    _, app_url = get_env_config()
    channels = get_category_channels(cat)
    total = len(channels)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))

    start = page * PAGE_SIZE
    page_channels = channels[start : start + PAGE_SIZE]

    nl = chr(10)
    cat_names = {
        'Cambodia': 'ប៉ុស្តិ៍ជាតិកម្ពុជា',
        'Kids': 'ប៉ុស្តិ៍កុមារ & តុក្កតា',
        'Sports': 'ប៉ុស្តិ៍កីឡាផ្សាយផ្ទាល់',
        'News': 'ប៉ុស្តិ៍ព័ត៌មាន ២៤/៧',
        'Movies': 'ប៉ុស្តិ៍ភាពយន្ត & កុន',
        'Documentary': 'ប៉ុស្តិ៍ភាពយន្តឯកសារ',
        'ALL': 'ប៉ុស្តិ៍ផ្សាយទាំងអស់'
    }
    emoji_map = {
        'Cambodia': '🇰🇭',
        'Kids': '🧸',
        'Sports': '⚽',
        'News': '📰',
        'Movies': '🎬',
        'Documentary': '📚',
        'ALL': '🌍'
    }
    cat_emoji = emoji_map.get(cat, '📺')
    kh_cat_name = html.escape(cat_names.get(cat, cat))

    header_text = (
        f'{cat_emoji} <b>{kh_cat_name} (មាន {total} ប៉ុស្តិ៍)</b>' + nl +
        f'<i>ទំព័រ {page + 1} នៃ {total_pages} • ចុចលើប៉ុស្តិ៍ដើម្បីទស្សនាផ្ទាល់៖</i>'
    )

    kb = []
    # Channels buttons
    for ch in page_channels:
        name = ch.get('name', 'Live Channel')
        display_name = name[:30] + '…' if len(name) > 30 else name

        if app_url:
            base_url = app_url.rstrip('/')
            query = urllib.parse.urlencode({'cid': ch['id']})
            mini_app_link = f"{base_url}/?{query}"
            kb.append([{'text': f"▶️ {display_name}", 'web_app': {'url': mini_app_link}}])
        # Without a configured app URL there is deliberately no raw-stream fallback.

    # Pagination controls in Khmer
    nav_row = []
    if page > 0:
        nav_row.append({'text': '◀️ ថយក្រោយ', 'callback_data': f'cat_{cat}_{page - 1}'})
    nav_row.append({'text': f'📄 ទំព័រ {page + 1}/{total_pages}', 'callback_data': f'cat_{cat}_{page}'})
    if page < total_pages - 1:
        nav_row.append({'text': 'បន្ទាប់ ▶️', 'callback_data': f'cat_{cat}_{page + 1}'})
    kb.append(nav_row)

    # Breadcrumb Action Buttons in Khmer
    action_row = [{'text': '🔙 ម៉ឺនុយមេ', 'callback_data': 'nav_main'}]
    if app_url:
        action_row.append({'text': '🚀 បើកកម្មវិធីពេញលេញ', 'web_app': {'url': app_url}})
    kb.append(action_row)

    return header_text, {'inline_keyboard': kb}

def handle_callback(cb_query):
    query_id = cb_query['id']
    msg = cb_query.get('message', {})
    chat_id = msg.get('chat', {}).get('id')
    message_id = msg.get('message_id')
    data = cb_query.get('data', '')

    api_request('answerCallbackQuery', {'callback_query_id': query_id})
    nl = chr(10)
    _, app_url = get_env_config()

    if data.startswith('cat_'):
        parts = data.split('_')
        cat = parts[1]
        page = int(parts[2]) if len(parts) > 2 else 0
        text, markup = build_category_view(cat, page)
        if message_id and msg.get('text'):
            edit_message(chat_id, message_id, text, markup)
        else:
            send_message(chat_id, text, markup)

    elif data == 'nav_main':
        welcome_text = (
            '📺 <b>DERLENG TV</b> • <i>ម៉ឺនុយមេ</i>' + nl + nl +
            'សូមជ្រើសរើសប្រភេទប៉ុស្តិ៍ទូរទស្សន៍ខាងក្រោមដើម្បីទស្សនា៖'
        )
        keyboard = build_main_keyboard(app_url)
        if message_id and msg.get('text'):
            edit_message(chat_id, message_id, welcome_text, keyboard)
        else:
            send_main_menu(chat_id)

    elif data == 'nav_stats':
        kh_count = len(get_category_channels('Cambodia'))
        kids_count = len(get_category_channels('Kids'))
        sports_count = len(get_category_channels('Sports'))
        news_count = len(get_category_channels('News'))
        movies_count = len(get_category_channels('Movies'))
        doc_count = len(get_category_channels('Documentary'))

        stats_text = (
            '📊 <b>ស្ថិតិទិន្នន័យប្រព័ន្ធ DERLENG TV</b>' + nl + nl +
            f'• <b>ប៉ុស្តិ៍ផ្សាយបន្តផ្ទាល់សរុប៖</b> <code>{len(CHANNELS):,}</code>' + nl +
            f'• 🇰🇭 <b>ប៉ុស្តិ៍ជាតិកម្ពុជា៖</b> <code>{kh_count}</code>' + nl +
            f'• 🧸 <b>ប៉ុស្តិ៍កុមារ & តុក្កតា៖</b> <code>{kids_count}</code>' + nl +
            f'• ⚽ <b>ប៉ុស្តិ៍កីឡាផ្សាយផ្ទាល់៖</b> <code>{sports_count}</code>' + nl +
            f'• 📰 <b>ប៉ុស្តិ៍ព័ត៌មាន ២៤/៧៖</b> <code>{news_count}</code>' + nl +
            f'• 🎬 <b>ប៉ុស្តិ៍ភាពយន្ត & កុន៖</b> <code>{movies_count}</code>' + nl +
            f'• 📚 <b>ប៉ុស្តិ៍ភាពយន្តឯកសារ៖</b> <code>{doc_count}</code>' + nl + nl +
            '⚡ <b>ប្រព័ន្ធផ្សាយ៖</b> HLS Adaptive Bitrate (មិនទាក់ មិនកន្ត្រាក់)' + nl +
            '📱 <b>កម្មវិធីចាក់៖</b> HTML5 Cinema Mode + WebApp Fullscreen'
        )
        kb = [
            [{'text': '🚀 បើកទស្សនា Mini App', 'web_app': {'url': app_url}} if app_url else {'text': '📺 Player', 'callback_data': 'nav_main'}],
            [{'text': '🔙 ត្រឡប់ទៅម៉ឺនុយមេ', 'callback_data': 'nav_main'}]
        ]
        if message_id and msg.get('text'):
            edit_message(chat_id, message_id, stats_text, {'inline_keyboard': kb})
        else:
            send_message(chat_id, stats_text, {'inline_keyboard': kb})

    elif data == 'nav_help':
        help_text = (
            '❓ <b>ការណែនាំអំពីការទស្សនា និងពង្រីកពេញអេក្រង់</b>' + nl + nl +
            '<b>១. របៀបទស្សនាពេញអេក្រង់កម្រិតភាពយន្ត (Landscape Cinema)</b>' + nl +
            '• បង្វិលទូរសព្ទរបស់អ្នកជា<b>ទម្រង់ផ្ដេក (Landscape)</b> — កម្មវិធីនឹងពង្រីកវីដេអូពេញអេក្រង់ ១០០% ដោយស្វ័យប្រវត្តិ!' + nl +
            '• ឬចុចប៊ូតុង <b>⛶ Fullscreen</b> នៅលើផ្ទាំងបញ្ជាវីដេអូ។' + nl + nl +
            '<b>២. ការប្តូរប៉ុស្តិ៍ទស្សនា</b>' + nl +
            '• ចុចលើឈ្មោះប៉ុស្តិ៍ក្នុងបញ្ជីខាងក្រោមវីដេអូ ឬវាយឈ្មោះស្វែងរកក្នុងប្រអប់ Search។' + nl + nl +
            '<b>៣. ការផ្ទុកប៉ុស្តិ៍ឡើងវិញ (Reload)</b>' + nl +
            '• ប្រសិនបើសេវាអ៊ីនធឺណិតមានការរអាក់រអួល សូមចុចប៊ូតុង <b>↻ Reload</b> ដើម្បីភ្ជាប់ឡើងវិញភ្លាមៗ។'
        )
        kb = [
            [{'text': '🚀 បើកដំណើរការកម្មវិធី', 'web_app': {'url': app_url}} if app_url else {'text': '📺 Player', 'callback_data': 'nav_main'}],
            [{'text': '🔙 ត្រឡប់ទៅម៉ឺនុយមេ', 'callback_data': 'nav_main'}]
        ]
        if message_id and msg.get('text'):
            edit_message(chat_id, message_id, help_text, {'inline_keyboard': kb})
        else:
            send_message(chat_id, help_text, {'inline_keyboard': kb})

    elif data == 'nav_search':
        search_text = (
            '🔍 <b>របៀបស្វែងរកប៉ុស្តិ៍ទូរទស្សន៍</b>' + nl + nl +
            'បើក <b>DERLENG TV Mini App</b> ហើយប្រើប្រអប់ស្វែងរក (Search) ផ្នែកខាងលើ ដើម្បីស្វែងរកប៉ុស្តិ៍ក្នុងបញ្ជីតាម៖' + nl +
            '• ឈ្មោះប៉ុស្តិ៍ (ឧទាហរណ៍៖ <i>Fresh News</i>, <i>Town</i>, <i>LEGO</i>, <i>beIN</i>)' + nl +
            '• ប្រភេទប៉ុស្តិ៍ (ឧទាហរណ៍៖ <i>Kids</i>, <i>Sports</i>, <i>News</i>, <i>Movies</i>)' + nl +
            '• ប្រទេស ឬតំបន់'
        )
        kb = [
            [{'text': '🚀 ស្វែងរកក្នុង Mini App', 'web_app': {'url': app_url}} if app_url else {'text': '📺 Player', 'callback_data': 'nav_main'}],
            [{'text': '🔙 ត្រឡប់ទៅម៉ឺនុយមេ', 'callback_data': 'nav_main'}]
        ]
        if message_id and msg.get('text'):
            edit_message(chat_id, message_id, search_text, {'inline_keyboard': kb})
        else:
            send_message(chat_id, search_text, {'inline_keyboard': kb})

def handle_text_command(chat_id, text):
    if not text.strip():
        return
    cmd = text.split()[0].lower()
    _, app_url = get_env_config()
    nl = chr(10)

    if cmd == '/start':
        send_main_menu(chat_id)
    elif cmd in ('/tv', '/player', '/play'):
        if app_url:
            send_message(chat_id, '🚀 <b>សូមចុចខាងក្រោមដើម្បីបើក DERLENG TV៖</b>', {'inline_keyboard': [[{'text': '▶️ បើកទស្សនា DERLENG TV', 'web_app': {'url': app_url}}]]})
        else:
            send_main_menu(chat_id)
    elif cmd in ('/cambodia', '/kh'):
        text, markup = build_category_view('Cambodia', 0)
        send_message(chat_id, text, markup)
    elif cmd in ('/kids', '/kid'):
        text, markup = build_category_view('Kids', 0)
        send_message(chat_id, text, markup)
    elif cmd in ('/sports', '/sport'):
        text, markup = build_category_view('Sports', 0)
        send_message(chat_id, text, markup)
    elif cmd in ('/news'):
        text, markup = build_category_view('News', 0)
        send_message(chat_id, text, markup)
    elif cmd in ('/movies', '/movie'):
        text, markup = build_category_view('Movies', 0)
        send_message(chat_id, text, markup)
    elif cmd in ('/stats'):
        text = f'📊 <b>ប៉ុស្តិ៍ផ្សាយបន្តផ្ទាល់សរុប៖</b> <code>{len(CHANNELS):,}</code> ប៉ុស្តិ៍ក្នុងបញ្ជី។'
        send_message(chat_id, text, build_main_keyboard(app_url))
    elif cmd in ('/help'):
        help_text = (
            '❓ <b>ពាក្យបញ្ជាផ្លូវកាត់ DERLENG TV</b>' + nl + nl +
            '• /tv — បើកកម្មវិធីទស្សនាទូរទស្សន៍' + nl +
            '• /cambodia — ប៉ុស្តិ៍ជាតិកម្ពុជា' + nl +
            '• /kids — ប៉ុស្តិ៍កុមារ និងតុក្កតា' + nl +
            '• /sports — ប៉ុស្តិ៍កីឡាផ្សាយផ្ទាល់' + nl +
            '• /news — ព័ត៌មានជាតិ និងសកលលោក' + nl +
            '• /movies — ភាពយន្ត & កុន' + nl +
            '• /stats — ស្ថិតិប៉ុស្តិ៍សរុប' + nl +
            '• /help — ការណែនាំ'
        )
        send_message(chat_id, help_text, build_main_keyboard(app_url))
    else:
        send_main_menu(chat_id)

def run_bot():
    token, _ = get_env_config()
    if not token:
        print('Error: TELEGRAM_BOT_TOKEN not found in .env or environment.')
        return
    if not CHANNELS:
        print('Error: published catalog missing or empty; build the release or set DERLENG_CATALOG_FILE.')
        return
    print('[*] DERLENG TV Bot (Khmer Edition with Kids) is running! Listening for updates on Telegram...')
    offset = 0
    while True:
        try:
            updates = api_request('getUpdates', {'offset': offset, 'timeout': 20})
            if updates and updates.get('ok') and updates.get('result'):
                for u in updates['result']:
                    if 'message' in u:
                        msg = u['message']
                        chat_id = msg['chat']['id']
                        text = msg.get('text', '')
                        if text:
                            handle_text_command(chat_id, text)
                    elif 'callback_query' in u:
                        handle_callback(u['callback_query'])
                    # Acknowledge after dispatch, never before a handler exception.
                    offset = u['update_id'] + 1
            time.sleep(1)
        except KeyboardInterrupt:
            print('Bot stopped by user.')
            break
        except Exception as e:
            if 'timed out' not in str(e).lower():
                print(f'Polling error: {e}')
            time.sleep(2)

if __name__ == '__main__':
    run_bot()
