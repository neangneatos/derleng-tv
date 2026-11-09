#!/usr/bin/env python3
"""Reproducible, static-only Hostinger archive. No network, secrets or live writes."""
import argparse
import base64
import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
import build_ui

BASE = Path(__file__).resolve().parent

def build_release(destination=None):
    destination = Path(destination or BASE / 'dist')
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='derleng-tv-release-') as td:
        stage = Path(td)/'site'
        report = build_ui.build_all(stage)
        for name in ('logo.png','logo.svg','favicon.png','start_banner.png','welcome_banner.png'):
            shutil.copyfile(BASE/name, stage/name)
        (stage/'vendor').mkdir()
        for name in ('hls-1.7.4.min.js','hls-LICENSE.txt'):
            shutil.copyfile(BASE/'vendor'/name,stage/'vendor'/name)
        html=(stage/'index.html').read_text()
        scripts=re.findall(r'<script>(.*?)</script>',html,re.S)
        hashes=' '.join("'sha256-"+base64.b64encode(hashlib.sha256(s.encode()).digest()).decode()+"'" for s in scripts)
        csp=("default-src 'self'; script-src 'self' https://telegram.org "+hashes+"; "
             "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
             "img-src 'self' data: https:; media-src 'self' blob: https:; connect-src 'self' https:; "
             "worker-src 'self' blob:; object-src 'none'; base-uri 'self'; "
             "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org https://t.me https://*.t.me")
        files=[str(p.relative_to(stage)) for p in stage.rglob('*') if p.is_file()]
        files += ['health.json','release-manifest.json']
        allow='|'.join(re.escape(f) for f in sorted(files))
        htaccess=('Options -Indexes\nDirectoryIndex index.html\n'
                  '<IfModule mod_rewrite.c>\nRewriteEngine On\n'
                  'RewriteRule ^proxy/?$ - [G,L]\n'
                  'RewriteRule ^healthz/?$ health.json [L]\n'
                  'RewriteRule ^$ index.html [L]\n'
                  'RewriteRule ^(?:'+allow+')$ - [L]\n'
                  'RewriteRule ^ - [R=404,L]\n</IfModule>\n'
                  '<FilesMatch "(^\\.|\\.(?:py|sh|log|zip|env|bak)$)">\nRequire all denied\n</FilesMatch>\n'
                  '<IfModule mod_headers.c>\n'
                  'Header always set X-Content-Type-Options "nosniff"\n'
                  'Header always set Referrer-Policy "no-referrer"\n'
                  'Header always unset X-Frame-Options\n'
                  'Header always set Content-Security-Policy "'+csp+'"\n'
                  'Header always set Permissions-Policy "camera=(), microphone=(), geolocation=()"\n'
                  '<FilesMatch "^(?:index\\.html|channels_public\\.json|health\\.json|release-manifest\\.json)$">\n'
                  'Header set Cache-Control "no-cache, must-revalidate"\n</FilesMatch>\n'
                  '<FilesMatch "^(?:channels\\.[a-f0-9]{16}\\.json|hls-1\\.7\\.4\\.min\\.js)$">\n'
                  'Header set Cache-Control "public, max-age=31536000, immutable"\n</FilesMatch>\n'
                  '</IfModule>\n')
        (stage/'.htaccess').write_text(htaccess)
        (stage/'health.json').write_text(json.dumps({'status':'static_release_present','service':'derleng-tv-webapp',
            'catalog_version':report['catalog_version'],'channels':report['published'],
            'playback_verified':False,'note':'Static marker only; does not test streams or bot.'},separators=(',',':')))
        manifest={'format':1,'base_url':'https://tv.derlenghub.com','hls_version':'1.7.4',
                  'catalog_version':report['catalog_version'],'files':{}}
        for p in sorted(stage.rglob('*')):
            if p.is_file(): manifest['files'][str(p.relative_to(stage))]=hashlib.sha256(p.read_bytes()).hexdigest()
        release_id=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()[:16]
        manifest['release_id']=release_id
        (stage/'release-manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n')
        archive=destination/('derleng-tv-hostinger-'+release_id+'.zip')
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for p in sorted(stage.rglob('*')):
                if p.is_file():
                    info=zipfile.ZipInfo(str(p.relative_to(stage)),date_time=(2026,1,1,0,0,0))
                    info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
                    z.writestr(info,p.read_bytes())
        # Candidate folder only. Never delete unknown files or touch the project-root live files.
        target=destination/'hostinger';target.mkdir(exist_ok=True)
        for p in stage.rglob('*'):
            if p.is_file():
                t=target/p.relative_to(stage);t.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,t)
        (destination/'catalog-build-report.json').write_text(json.dumps(report,indent=2)+'\n')
        (destination/'latest-release.json').write_text(json.dumps({'archive':archive.name,'release_id':release_id},indent=2)+'\n')
        print('Static archive:',archive)
        return archive

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir');args=parser.parse_args()
    build_release(args.output_dir)
