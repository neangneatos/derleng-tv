import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import catalog
import build_ui

class CatalogBuildTests(unittest.TestCase):
    def test_unsafe_urls_and_unsupported_protocols(self):
        for url in ['https://127.0.0.1/a.m3u8',
                    'https://169.254.169.254/a.m3u8','https://localhost/a.m3u8',
                    'https://10.0.0.1/a.m3u8','https://2130706433/a.m3u8',
                    'https://example.org/a.mpd','https://example.org/a.m3u8?token=123',
                    'https://user:pass@example.org/a.m3u8',
                    'https://example.org/a.m3u8?auth%69d=x','javascript:alert(1)',
                    'https://example.org/a.m3u8#secret']:
            with self.subTest(url=url), self.assertRaises(ValueError): catalog.public_url(url)
        self.assertEqual(catalog.public_url('https://example.org/a.m3u8?channel_id=4'), 'https://example.org/a.m3u8?channel_id=4')

    def test_http_https_and_ports_preserved(self):
        for url in ['http://example.org/a.m3u8', 'http://example.org:8080/a.m3u8',
                    'https://example.org:8443/a.m3u8']:
            self.assertEqual(catalog.public_url(url), url)
        rows, rejected = catalog.sanitize_catalog([
            {'name': 'A', 'url': 'https://example.org:8443/a.m3u8'},
            {'name': 'B', 'url': 'https://example.org/a.m3u8'},
            {'name': 'C', 'url': 'http://example.org/a.m3u8'}])
        self.assertEqual(len(rows), 3)
        self.assertEqual(rejected, {})

    def test_stable_ids_and_deduplication(self):
        rows=[{'name':'A','url':'https://example.org/a.m3u8'}, {'name':'B','url':'https://example.org/a.m3u8'}]
        one,rejected=catalog.sanitize_catalog(rows)
        two,_=catalog.sanitize_catalog([{'name':'renamed','url':rows[0]['url']}])
        self.assertEqual(len(one),1);self.assertEqual(rejected['duplicate'],1)
        self.assertEqual(one[0]['id'],two[0]['id'])
        self.assertEqual(one[0]['availability'],'unverified')

    def test_reproducibility_and_safe_script_serialization(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); source=root/'raw.json'
            name='</script><script>window.pwned=true</script>\u2028'
            source.write_text(json.dumps([{'name':name,'url':'https://example.org/a.m3u8'}]))
            with mock.patch.object(build_ui,'RAW_CHANNELS_PATH',str(source)),contextlib.redirect_stdout(io.StringIO()):
                build_ui.build_all(root/'a');build_ui.build_all(root/'b')
            self.assertEqual((root/'a/index.html').read_bytes(),(root/'b/index.html').read_bytes())
            html=(root/'a/index.html').read_text()
            self.assertNotIn('</script><script>window.pwned',html)
            data=html.split('let channels = ',1)[1].split(';\n',1)[0]
            self.assertEqual(json.loads(data)[0]['n'],name.strip())
            self.assertEqual(json.loads((root/'a/channels_public.json').read_text())[0]['n'],name.strip())

    def test_logo_paths_are_local_content_addressed_only(self):
        for path, expected in [('logos/' + 'a'*64 + '.webp', True),
                               ('https://attacker.org/logo.png', False),
                               ('logos/../../private.webp', False),
                               ('logos/' + 'a'*64 + '.webp" onerror="alert(1)', False)]:
            rows,_ = catalog.sanitize_catalog([{'name':'A','url':'https://example.org/a.m3u8','logo':path}])
            self.assertEqual('l' in rows[0], expected)

    def test_preferred_source_preserves_id_and_rejects_unsafe_preferences(self):
        base={'name':'A','url':'http://example.org/a.m3u8'}
        original,_=catalog.sanitize_catalog([base])
        for url,allowed in [('https://cdn.example.org/a.m3u8',True),
                            ('https://127.0.0.1/private.m3u8',False),
                            ('https://example.org/a.m3u8?token=secret',False),
                            ('http://example.org/b.m3u8',False)]:
            rows,_=catalog.sanitize_catalog([dict(base,preferred_url=url)])
            self.assertEqual(rows[0]['id'],original[0]['id'])
            self.assertEqual('p' in rows[0],allowed)

    def test_audited_market_fields_and_iso_gb_survive_build(self):
        rows,_ = catalog.sanitize_catalog([{'name':'A','url':'https://example.org/a.m3u8',
            'country':'ZZ','group':'Country unverified',
            'country_basis':'origin_unknown_curated_feed_market',
            'market_code':'GB','market_name':'United Kingdom'}])
        self.assertEqual(rows[0]['mc'],'GB')
        self.assertEqual(rows[0]['mg'],'United Kingdom')
        records=json.loads(Path(build_ui.RAW_CHANNELS_PATH).read_text())
        public,_=catalog.sanitize_catalog(records)
        market_rows=[c for c in public if c.get('country_basis')=='origin_unknown_curated_feed_market']
        self.assertTrue(market_rows)
        self.assertTrue(all(c.get('mc') and c.get('mg') for c in market_rows))

    def test_empty_build_does_not_replace_release(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'raw.json').write_text('[]');(root/'index.html').write_text('old')
            with mock.patch.object(build_ui,'RAW_CHANNELS_PATH',str(root/'raw.json')),self.assertRaises(ValueError):
                build_ui.build_all(root)
            self.assertEqual((root/'index.html').read_text(),'old')

if __name__=='__main__': unittest.main()
