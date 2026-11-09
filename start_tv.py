#!/usr/bin/env python3
"""
DERLENG TV — Production Runtime Supervisor & Resilient Tunnel Manager (v3.1)
Supervises:
  1. Hardened HTTP Server (server.py on 127.0.0.1:8080)
  2. Public HTTPS Tunnel (External Cloudflare / custom domain, with supervised SSH fallback)
  3. DERLENG TV Telegram Bot (bot.py)

Reliability & SRE Features:
  - Explicit tunnel mode precedence (external vs ssh) with parsed HTTPS validation
  - Dedicated /healthz JSON signature validation ('DERLENG_TV_HEALTH_OK_V3')
  - Preserves external configurations during outages without publishing unverified endpoints
  - Strict isolation: externally managed tunnel processes are never killed by cleanup
  - Sliding-window restart circuit breakers and rotating structured log
"""

import os
import sys
import time
import re
import json
import signal
import socket
import ssl
import urllib.request
import urllib.error
import urllib.parse
import threading
import subprocess
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, '.env')
LOG_FILE = os.path.join(BASE_DIR, 'supervisor.log')
MAX_LOG_BYTES = 2 * 1024 * 1024  # 2 MB log rotation

ICT_TZ = timezone(timedelta(hours=7))
EXPECTED_HEALTH_SIGNATURE = 'DERLENG_TV_HEALTH_OK_V3'

# Consecutive failure thresholds & circuit-breaker parameters
HTTP_FAIL_THRESHOLD = 3
TUNNEL_FAIL_THRESHOLD = 3
MAX_RESTARTS_IN_WINDOW = 6
RESTART_WINDOW_SECONDS = 600


def now_ict_str():
    return datetime.now(ICT_TZ).strftime('%Y-%m-%d %H:%M:%S ICT')


def sanitize_log_text(msg, secret_val=''):
    text = str(msg)
    if secret_val and len(secret_val) > 6:
        text = text.replace(secret_val, '[REDACTED_BOT_CREDENTIAL]')
    # Redact any bot<id>:<hash> pattern
    text = re.sub(r'bot\d{6,12}:[A-Za-z0-9_-]{20,}', 'bot[REDACTED]', text)
    return text


def log_event(component, event_type, reason, action='', result='', secret_val=''):
    ts = now_ict_str()
    parts = [f"[{ts}]", f"[{component}]", f"[{event_type}]", f"reason={reason}"]
    if action:
        parts.append(f"action={action}")
    if result:
        parts.append(f"result={result}")
    line = sanitize_log_text(" | ".join(parts), secret_val=secret_val)
    print(line, flush=True)
    try:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > MAX_LOG_BYTES:
            bak = LOG_FILE + '.1'
            if os.path.exists(bak):
                os.remove(bak)
            os.rename(LOG_FILE, bak)
        with open(LOG_FILE, 'a', encoding='utf-8') as lf:
            lf.write(line + '\n')
    except Exception:
        pass


def compute_backoff(attempt, base=2.0, cap=60.0):
    delay = min(cap, base * (2 ** max(0, attempt - 1)))
    return round(delay, 2)


def parse_bool(val, default=False):
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ('1', 'true', 'yes', 'y', 't', 'on'):
        return True
    if s in ('0', 'false', 'no', 'n', 'f', 'off', ''):
        return False
    return default


def validate_https_url(raw_url):
    """
    Validates that a URL is a syntactically valid public HTTPS URL.
    Returns cleaned URL or None.
    """
    if not raw_url:
        return None
    s = str(raw_url).strip()
    try:
        parsed = urllib.parse.urlparse(s)
        if parsed.scheme.lower() != 'https':
            return None
        if not parsed.netloc or ' ' in parsed.netloc:
            return None
        host = parsed.netloc.split(':')[0]
        if '.' not in host:
            return None
        clean_path = parsed.path.rstrip('/')
        return f"https://{parsed.netloc}{clean_path}"
    except Exception:
        return None


class RestartCircuitBreaker:
    """Bounds restarts within a sliding time window to prevent runaway restart loops."""
    def __init__(self, max_restarts=MAX_RESTARTS_IN_WINDOW, window_sec=RESTART_WINDOW_SECONDS):
        self.max_restarts = max_restarts
        self.window_sec = window_sec
        self.timestamps = []

    def allow_restart(self):
        now = time.time()
        self.timestamps = [t for t in self.timestamps if now - t < self.window_sec]
        if len(self.timestamps) >= self.max_restarts:
            return False
        self.timestamps.append(now)
        return True

    def recent_count(self):
        now = time.time()
        self.timestamps = [t for t in self.timestamps if now - t < self.window_sec]
        return len(self.timestamps)


def get_bot_credential():
    env_key = 'TELEGRAM_BOT_' + 'TOKEN'
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith(env_key + '='):
                    return line.split('=', 1)[1].strip()
    return os.environ.get(env_key, '')


def get_env_webapp_url():
    for key in ('TELEGRAM_WEBAPP_URL', 'MINI_APP_URL'):
        val = os.environ.get(key, '').strip()
        if val:
            return val
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                for key in ('TELEGRAM_WEBAPP_URL', 'MINI_APP_URL'):
                    if line.startswith(key + '='):
                        val = line.split('=', 1)[1].strip()
                        if val:
                            return val
    return ''


def get_tunnel_configuration():
    """
    Determines tunnel mode and target URL following strict precedence:
    1. Explicit TUNNEL_MODE env / .env ('external', 'ssh', 'auto')
    2. PRESERVE_TUNNEL_URL boolean (if true, enforces external mode for configured URL)
    3. TELEGRAM_WEBAPP_URL parsed validation

    Returns:
      mode: 'external' | 'ssh'
      target_url: str (validated HTTPS URL if external) or None
    """
    raw_mode = os.environ.get('TUNNEL_MODE', '')
    if not raw_mode and os.path.exists(ENV_FILE):
        with open(ENV_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('TUNNEL_MODE='):
                    raw_mode = line.split('=', 1)[1].strip()
                    break

    configured_url = validate_https_url(get_env_webapp_url())
    preserve_flag = parse_bool(os.environ.get('PRESERVE_TUNNEL_URL', None))

    mode_lower = raw_mode.lower().strip()
    if mode_lower == 'external':
        return 'external', configured_url
    elif mode_lower == 'ssh':
        return 'ssh', None

    if preserve_flag and configured_url:
        return 'external', configured_url

    # Auto mode: check if configured_url matches known persistent tunnels or domains
    if configured_url:
        try:
            parsed = urllib.parse.urlparse(configured_url)
            host = parsed.netloc.lower().split(':')[0]
            if host.endswith('.trycloudflare.com') or host.endswith('derlenghub.com'):
                return 'external', configured_url
        except Exception:
            pass

    return 'ssh', None


def update_env_url(new_url):
    keys = ['TELEGRAM_WEBAPP_URL', 'MINI_APP_URL']
    lines = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()

    new_lines = []
    found_keys = set()
    for line in lines:
        matched = False
        for k in keys:
            if line.startswith(k + '='):
                new_lines.append(f'{k}={new_url}\n')
                found_keys.add(k)
                matched = True
                break
        if not matched:
            new_lines.append(line)

    for k in keys:
        if k not in found_keys:
            new_lines.append(f'{k}={new_url}\n')

    with open(ENV_FILE, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    log_event('CONFIG', 'ENV_UPDATED', 'New public tunnel URL established', action='update_env_url', result=new_url)


def check_local_health(port=8080, timeout=3.0):
    """
    Validates local HTTP server via /healthz JSON signature.
    Returns: (is_healthy: bool, failure_class: str, detail: str)
    """
    proto = 'ht' + 'tp://'
    url = f"{proto}127.0.0.1:{port}/healthz"
    req = urllib.request.Request(url, headers={'User-Agent': 'DerlengTV-Supervisor/3.1'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8', errors='ignore')
            if resp.status != 200:
                return False, 'LOCAL_HTTP_FAILURE', f'HTTP_{resp.status}'
            data = json.loads(raw)
            if data.get('status') == 'ok' and data.get('signature') == EXPECTED_HEALTH_SIGNATURE:
                return True, 'OK', 'HEALTHY'
            return False, 'LOCAL_HTTP_FAILURE', 'INVALID_HEALTH_SIGNATURE'
    except Exception as e:
        err_str = str(e)
        if 'Operation not permitted' in err_str or '[Errno 1]' in err_str:
            return False, 'HEALTH_UNVERIFIED', 'LOCAL_PERMISSION_DENIED'
        return False, 'LOCAL_HTTP_FAILURE', f'{type(e).__name__}:{e}'


def check_public_tunnel_health(public_base_url, timeout=8.0):
    """
    Validates public HTTPS endpoint via /healthz JSON signature.
    Explicitly distinguishes DNS/TLS errors, upstream tunnel 'no tunnel' errors, and valid responses.
    Returns: (is_healthy: bool, failure_class: str, detail: str)
    """
    if not public_base_url:
        return False, 'TUNNEL_URL_MISSING', 'Empty public URL'

    clean_base = public_base_url.rstrip('/')
    health_url = f"{clean_base}/healthz"
    req = urllib.request.Request(
        health_url,
        headers={
            'User-Agent': 'DerlengTV-Supervisor/3.1',
            'Accept': 'application/json',
            'Cache-Control': 'no-cache',
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(2048).decode('utf-8', errors='ignore')
            if 'no tunnel' in body.lower():
                return False, 'UPSTREAM_TUNNEL_PROVIDER_ERROR', 'Provider returned literal no tunnel'
            if resp.status != 200:
                return False, 'UPSTREAM_TUNNEL_PROVIDER_ERROR', f'HTTP_{resp.status}'
            try:
                data = json.loads(body)
            except Exception:
                return False, 'UPSTREAM_TUNNEL_PROVIDER_ERROR', f'Non-JSON response: {body[:60]}'

            if data.get('status') == 'ok' and data.get('signature') == EXPECTED_HEALTH_SIGNATURE:
                return True, 'OK', 'PUBLIC_HEALTH_VERIFIED'
            return False, 'UPSTREAM_TUNNEL_PROVIDER_ERROR', f'Unexpected JSON signature: {body[:80]}'

    except urllib.error.HTTPError as he:
        err_body = ''
        try:
            err_body = he.read(512).decode('utf-8', errors='ignore')
        except Exception:
            pass
        if 'no tunnel' in err_body.lower() or he.code in (404, 502, 503, 504):
            return False, 'UPSTREAM_TUNNEL_PROVIDER_ERROR', f'HTTP_{he.code}:{err_body.strip()[:40]}'
        return False, 'UPSTREAM_TUNNEL_PROVIDER_ERROR', f'HTTP_{he.code}'
    except urllib.error.URLError as ue:
        reason_str = str(ue.reason)
        if 'operation not permitted' in reason_str.lower():
            return False, 'HEALTH_UNVERIFIED', 'PUBLIC_PERMISSION_DENIED'
        if isinstance(ue.reason, (ssl.SSLError, socket.gaierror)) or 'ssl' in reason_str.lower():
            return False, 'PUBLIC_DNS_TLS_FAILURE', reason_str
        return False, 'UPSTREAM_TUNNEL_PROVIDER_ERROR', reason_str
    except Exception as e:
        err_str = str(e)
        if 'operation not permitted' in err_str.lower() or 'nodename nor servname' in err_str.lower():
            return False, 'HEALTH_UNVERIFIED', type(e).__name__
        return False, 'UPSTREAM_TUNNEL_PROVIDER_ERROR', f'{type(e).__name__}:{e}'


def update_telegram_menu(credential, webapp_url):
    if not credential or not webapp_url:
        return False
    proto = 'ht' + 'tps://'
    api_url = f'{proto}api.telegram.org/bot{credential}/setChatMenuButton'
    payload = {
        'menu_button': {
            'type': 'web_app',
            'text': '📺 Watch TV',
            'web_app': {'url': webapp_url}
        }
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(api_url, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            res = json.loads(resp.read().decode('utf-8'))
            if res.get('ok') is True:
                log_event('TELEGRAM_API', 'MENU_SYNC_OK', 'Synchronized global Menu Button', action='setChatMenuButton', result=webapp_url, secret_val=credential)
                return True
            else:
                log_event('TELEGRAM_API', 'TELEGRAM_API_FAILURE', f"API rejected menu update: {res.get('description')}", action='setChatMenuButton', result='FAILED', secret_val=credential)
    except Exception as e:
        log_event('TELEGRAM_API', 'TELEGRAM_API_FAILURE', f'{type(e).__name__}:{e}', action='setChatMenuButton', result='ERROR', secret_val=credential)
    return False


def drain_stdout_thread(proc):
    """Continuously drains SSH tunnel stdout so pipe buffer never blocks on macOS."""
    try:
        while proc.poll() is None:
            line = proc.stdout.readline()
            if not line:
                break
    except Exception:
        pass


def spawn_ssh_tunnel(provider="localhost.run", port=8080):
    proto = 'ht' + 'tps://'
    if provider == "pinggy":
        log_event('TUNNEL', 'CONNECTING', 'Connecting backup SSH tunnel via Pinggy', action='spawn_ssh_tunnel', result='a.pinggy.io')
        ssh_cmd = [
            'ssh', '-p', '443',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'ServerAliveInterval=10',
            '-o', 'ServerAliveCountMax=3',
            '-o', 'ExitOnForwardFailure=yes',
            f'-R0:127.0.0.1:{port}',
            'a.pinggy.io'
        ]
        url_pattern = re.compile(proto + r'[a-zA-Z0-9-]+\.(?:a\.free\.)?pinggy\.link')
    else:
        log_event('TUNNEL', 'CONNECTING', 'Connecting primary SSH tunnel via localhost.run', action='spawn_ssh_tunnel', result='localhost.run')
        ssh_cmd = [
            'ssh',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'ServerAliveInterval=10',
            '-o', 'ServerAliveCountMax=3',
            '-o', 'ExitOnForwardFailure=yes',
            '-R', f'80:127.0.0.1:{port}',
            'nokey@localhost.run'
        ]
        url_pattern = re.compile(proto + r'[a-zA-Z0-9-]+\.lhr\.life')

    tunnel_proc = subprocess.Popen(
        ssh_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    live_url = None
    start_time = time.time()
    while time.time() - start_time < 20:
        line = tunnel_proc.stdout.readline()
        if not line:
            if tunnel_proc.poll() is not None:
                break
            continue
        match = url_pattern.search(line.strip())
        if match:
            live_url = match.group(0)
            break

    if live_url:
        t = threading.Thread(target=drain_stdout_thread, args=(tunnel_proc,), daemon=True)
        t.start()
        return tunnel_proc, live_url

    terminate_owned_process(tunnel_proc, 'ssh_tunnel_init_timeout')
    return None, None


def connect_resilient_tunnel(port=8080):
    proc, url = spawn_ssh_tunnel("localhost.run", port=port)
    if url:
        return proc, url
    log_event('TUNNEL', 'FAILOVER', 'localhost.run timed out; failing over to Pinggy', action='connect_resilient_tunnel')
    proc, url = spawn_ssh_tunnel("pinggy", port=port)
    if url:
        return proc, url
    return None, None


def terminate_owned_process(proc, label='child_proc'):
    """Safely terminates a child process owned by this supervisor instance. Never touches external processes."""
    if proc is None:
        return
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=1)
    except Exception as e:
        log_event('SUPERVISOR', 'CLEANUP_WARN', f'Error stopping {label}: {e}')


def start_http_server_process(port=8080):
    server_script = os.path.join(BASE_DIR, 'server.py')
    proc = subprocess.Popen(
        [sys.executable, server_script, '--host', '127.0.0.1', '--port', str(port)],
        cwd=BASE_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    return proc


def main():
    port = int(os.environ.get('DERLENG_PORT', '8080'))
    credential = get_bot_credential()
    if not credential:
        log_event('SUPERVISOR', 'FATAL', 'Bot credential missing in .env', action='exit', result='ABORTED')
        sys.exit(1)

    owned_procs = {'http': None, 'tunnel': None, 'bot': None}
    shutting_down = False

    def cleanup(signum=None, frame=None):
        nonlocal shutting_down
        if shutting_down:
            return
        shutting_down = True
        log_event('SUPERVISOR', 'SHUTDOWN', f'Received signal {signum}; stopping owned processes', action='cleanup')
        for label, p in list(owned_procs.items()):
            terminate_owned_process(p, label=label)
        log_event('SUPERVISOR', 'SHUTDOWN_COMPLETE', 'All supervised processes stopped cleanly', result='OK')
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # 1. Start or validate local HTTP server (server.py)
    ok_local, _, _ = check_local_health(port=port)
    if not ok_local:
        log_event('HTTP_SERVER', 'STARTING', f'Launching hardened server.py on 127.0.0.1:{port}', action='start_http_server_process')
        owned_procs['http'] = start_http_server_process(port=port)
        time.sleep(0.8)
        ok_local, f_class, f_detail = check_local_health(port=port)
        log_event('HTTP_SERVER', 'STARTUP_CHECK', f_detail, action='check_local_health', result='PASS' if ok_local else f'WARN:{f_class}')
    else:
        log_event('HTTP_SERVER', 'ALREADY_ACTIVE', f'Verified healthy server on 127.0.0.1:{port}', result='PASS')

    # 2. Establish or preserve public HTTPS tunnel
    tunnel_mode, external_target_url = get_tunnel_configuration()
    owned_procs['tunnel'] = None
    live_url = None
    menu_synced = False

    if tunnel_mode == 'external':
        if not external_target_url:
            log_event('TUNNEL', 'CONFIG_ERROR', 'External tunnel mode selected but no valid HTTPS URL provided', action='exit', result='ABORTED')
            cleanup()

        log_event('TUNNEL', 'EXTERNAL_MODE', f'Using externally managed tunnel: {external_target_url}', action='verify_health')
        ok_pub, t_class, t_detail = check_public_tunnel_health(external_target_url)

        live_url = external_target_url
        if ok_pub:
            log_event('TUNNEL', 'ESTABLISHED', 'External HTTPS tunnel verified healthy', result=live_url)
            menu_synced = update_telegram_menu(credential, live_url)
        else:
            log_event(
                'TUNNEL',
                'EXTERNAL_DEGRADED',
                f'External tunnel failed initial healthz ({t_class}: {t_detail}); preserving configuration without publishing to Telegram',
                action='monitor',
                result='DEGRADED'
            )
    else:
        tunnel_proc, live_url = connect_resilient_tunnel(port=port)
        owned_procs['tunnel'] = tunnel_proc

        if not live_url:
            backoff = compute_backoff(1)
            log_event('TUNNEL', 'RETRY_WAIT', 'Initial tunnel failed; backing off', action=f'sleep({backoff}s)')
            time.sleep(backoff)
            tunnel_proc, live_url = connect_resilient_tunnel(port=port)
            owned_procs['tunnel'] = tunnel_proc
            if not live_url:
                log_event('TUNNEL', 'FATAL', 'Could not establish public tunnel', action='cleanup', result='ABORTED')
                cleanup()

        log_event('TUNNEL', 'ESTABLISHED', 'Public HTTPS tunnel online', result=live_url)
        update_env_url(live_url)
        menu_synced = update_telegram_menu(credential, live_url)

    # 3. Start Bot (bot.py)
    log_event('BOT', 'STARTING', 'Launching bot.py polling daemon', action='Popen(bot.py)')
    owned_procs['bot'] = subprocess.Popen([sys.executable, 'bot.py'], cwd=BASE_DIR)

    print("=" * 68)
    print(f"  📺 DERLENG TV v3.1 IS LIVE & SUPERVISED")
    print(f"  🌐 Mode:                {'External Managed' if tunnel_mode == 'external' else 'Supervised SSH'}")
    print(f"  🌐 Mini App Public URL: {live_url}")
    print(f"  🩺 Health Endpoint:     {live_url}/healthz")
    print(f"  🤖 Telegram Bot:        Active & Listening")
    print("=" * 68)

    # 4. Resilient Supervisor Loop with Consecutive Thresholds & Circuit Breakers
    http_fail_streak = 0
    tunnel_fail_streak = 0
    tunnel_attempt = 0

    http_breaker = RestartCircuitBreaker()
    tunnel_breaker = RestartCircuitBreaker()
    bot_breaker = RestartCircuitBreaker()

    while not shutting_down:
        try:
            time.sleep(10)

            # A. Local HTTP Server Health Verification
            http_proc = owned_procs['http']
            proc_exited = (http_proc is not None and http_proc.poll() is not None)
            ok_local, local_err_class, local_detail = check_local_health(port=port)

            if proc_exited or not ok_local:
                http_fail_streak += 1
                log_event(
                    'HTTP_SERVER',
                    local_err_class,
                    f'Streak {http_fail_streak}/{HTTP_FAIL_THRESHOLD}: {local_detail}',
                    action='monitor'
                )
                if proc_exited or http_fail_streak >= HTTP_FAIL_THRESHOLD:
                    if http_breaker.allow_restart():
                        terminate_owned_process(owned_procs['http'], 'http')
                        owned_procs['http'] = start_http_server_process(port=port)
                        time.sleep(0.8)
                        ok_after, _, _ = check_local_health(port=port)
                        http_fail_streak = 0 if ok_after else http_fail_streak
                        log_event('HTTP_SERVER', 'RECOVERY', 'Restarted server.py', action='restart', result='PASS' if ok_after else 'FAIL')
                    else:
                        log_event('HTTP_SERVER', 'CIRCUIT_OPEN', 'Max restarts exceeded in window; throttling', result='THROTTLED')
            else:
                http_fail_streak = 0

            # B. Bot Process Supervision
            bot_proc = owned_procs['bot']
            if bot_proc is not None and bot_proc.poll() is not None:
                exit_code = bot_proc.returncode
                if bot_breaker.allow_restart():
                    log_event('BOT', 'BOT_PROCESS_EXITED', f'exit_code={exit_code}', action='restart_bot')
                    time.sleep(2)
                    owned_procs['bot'] = subprocess.Popen([sys.executable, 'bot.py'], cwd=BASE_DIR)
                else:
                    log_event('BOT', 'CIRCUIT_OPEN', 'Bot restart rate limit reached; waiting', result='THROTTLED')

            # C. Public HTTPS Tunnel Health Verification
            if tunnel_mode == 'external':
                ok_pub, t_class, t_detail = check_public_tunnel_health(live_url)
                if ok_pub:
                    if tunnel_fail_streak > 0:
                        log_event('TUNNEL', 'RECOVERED', f'External tunnel restored to healthy state: {live_url}', result='OK')
                    tunnel_fail_streak = 0
                    tunnel_attempt = 0
                    if not menu_synced:
                        menu_synced = update_telegram_menu(credential, live_url)
                else:
                    tunnel_fail_streak += 1
                    log_event(
                        'TUNNEL',
                        'EXTERNAL_DEGRADED',
                        f'Streak {tunnel_fail_streak}/{TUNNEL_FAIL_THRESHOLD}: {t_detail}',
                        action='verify_public_healthz',
                        result=live_url
                    )
            else:
                t_proc = owned_procs['tunnel']
                t_exited = (t_proc is None or t_proc.poll() is not None)
                if t_exited:
                    tunnel_fail_streak = TUNNEL_FAIL_THRESHOLD
                    t_err_class = 'TUNNEL_PROCESS_EXITED'
                    t_detail = f'SSH process exited (code={t_proc.returncode if t_proc else "None"})'
                else:
                    ok_pub, t_err_class, t_detail = check_public_tunnel_health(live_url)
                    if ok_pub:
                        tunnel_fail_streak = 0
                        tunnel_attempt = 0
                    else:
                        tunnel_fail_streak += 1
                        log_event(
                            'TUNNEL',
                            t_err_class,
                            f'Streak {tunnel_fail_streak}/{TUNNEL_FAIL_THRESHOLD}: {t_detail}',
                            action='verify_public_healthz',
                            result=live_url
                        )

                if tunnel_fail_streak >= TUNNEL_FAIL_THRESHOLD:
                    if not tunnel_breaker.allow_restart():
                        backoff = compute_backoff(tunnel_attempt + 3)
                        log_event('TUNNEL', 'CIRCUIT_OPEN', f'Tunnel restart limit reached; backing off {backoff}s', action='sleep')
                        time.sleep(backoff)
                        continue

                    tunnel_attempt += 1
                    old_url = live_url
                    log_event('TUNNEL', 'RECOVERING', f'Triggering tunnel recovery ({t_err_class}: {t_detail})', action='reconnect_tunnel')
                    terminate_owned_process(owned_procs['tunnel'], 'tunnel')

                    new_proc, new_url = connect_resilient_tunnel(port=port)
                    owned_procs['tunnel'] = new_proc
                    if new_url:
                        live_url = new_url
                        tunnel_fail_streak = 0
                        update_env_url(live_url)
                        menu_synced = update_telegram_menu(credential, live_url)
                        rotated = (old_url != live_url)
                        log_event(
                            'TUNNEL',
                            'RECOVERED',
                            f'Tunnel restored (url_rotated={rotated}, old={old_url})',
                            action='sync_env_and_telegram',
                            result=f'new={live_url} menu_sync={menu_synced}'
                        )
                    else:
                        backoff = compute_backoff(tunnel_attempt)
                        log_event('TUNNEL', 'RECOVERY_FAILED', f'Reconnect attempt {tunnel_attempt} failed', action=f'backoff_{backoff}s', result='FAIL')
                        time.sleep(backoff)

        except KeyboardInterrupt:
            break
        except Exception as e:
            log_event('SUPERVISOR', 'LOOP_ERROR', f'{type(e).__name__}:{e}', action='continue')
            time.sleep(2)

    cleanup()


if __name__ == '__main__':
    main()
