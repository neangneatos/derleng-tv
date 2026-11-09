"""Public static-hosting catalog policy. No network or secret-bearing output."""
import hashlib
import ipaddress
import re
from collections import Counter
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# Deliberately narrow: unknown query keys are quarantined, not silently stripped.
PUBLIC_QUERY_KEYS = frozenset(('ads.xumo_channelid', 'ads.xumo_providerid',
    'ads.xumo_providername', 'content_livestream', 'network_id', 'ads.service_id',
    'channel_id', 'tp', 'channel', 'content_id'))
TITLE_PREFIX_RE = re.compile(r'^title="[^"]*"\s*-\s*', re.I)

def public_url(raw):
    if not isinstance(raw, str) or any(ord(c) < 33 for c in raw):
        raise ValueError('invalid_url')
    try:
        u = urlsplit(raw)
        host = (u.hostname or '').lower()
        port = u.port
    except ValueError:
        raise ValueError('invalid_url')
    if u.scheme.lower() != 'https':
        raise ValueError('https_required')
    if u.username is not None or u.password is not None or u.fragment:
        raise ValueError('private_url')
    if not host or host.endswith('.') or '.' not in host or host.endswith(('.local', '.localhost', '.internal', '.test', '.invalid')):
        raise ValueError('invalid_host')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # DNS is not resolved at build time; this is not a proxy/egress safeguard.
        if not re.fullmatch(r'[a-z0-9.-]+', host):
            raise ValueError('invalid_host')
        if all(part.isdigit() for part in host.split('.')):
            raise ValueError('invalid_host')
    else:
        if not address.is_global:
            raise ValueError('private_host')
    if port not in (None, 443):
        raise ValueError('nonstandard_port')
    if not u.path.lower().endswith('.m3u8'):
        raise ValueError('unsupported_protocol')
    pairs = parse_qsl(u.query, keep_blank_values=True)
    if any(k.lower() not in PUBLIC_QUERY_KEYS for k, _ in pairs):
        raise ValueError('unapproved_query')
    if re.search(r'eyJ[a-zA-Z0-9_-]{10,}', raw):
        raise ValueError('private_url')
    return urlunsplit(('https', host, u.path, urlencode(pairs), ''))

def sanitize_catalog(records):
    public, seen, rejected = [], set(), Counter()
    for record in records:
        try:
            if not isinstance(record, dict):
                raise ValueError('invalid_record')
            name = record.get('name', record.get('n', ''))
            if not isinstance(name, str) or not name.strip() or name.lower() in ('blocked]', 'blocked', 'null'):
                raise ValueError('invalid_name')
            name = TITLE_PREFIX_RE.sub('', name).strip()
            if not name:
                raise ValueError('invalid_name')
            url = public_url(record.get('url', record.get('u', '')))
            if url in seen:
                raise ValueError('duplicate')
            fields = {}
            for compact, long, fallback in [('g','group','Global'),('t','genre','Entertainment'),('c','country','INT')]:
                value = record.get(long, record.get(compact, fallback)) or fallback
                if not isinstance(value, str):
                    raise ValueError('invalid_record')
                fields[compact] = value.strip()
            if fields['t'] not in ('Cambodia','Kids','Sports','News','Movies','Documentary') and any(x in (name+' '+fields['g']).lower() for x in ('kid','cartoon')):
                fields['t'] = 'Kids'
            public.append(dict(id=hashlib.sha256(url.encode()).hexdigest()[:16], n=name, u=url,
                               protocol='hls', availability='unverified', **fields))
            seen.add(url)
        except ValueError as exc:
            rejected[str(exc)] += 1
    order = {'Kids':1,'Sports':2,'News':3,'Movies':4,'Documentary':5,'Music':6,'Entertainment':7}
    public.sort(key=lambda x:(0 if x['c']=='KH' or x['g']=='Cambodia' else 1, order.get(x['t'],8),x['n'].lower(),x['id']))
    return public, dict(sorted(rejected.items()))
