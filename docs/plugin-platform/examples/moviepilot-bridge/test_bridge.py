"""Protocol tests; no MoviePilot instance or tracker credentials required."""
import base64
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


class HTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail


class Torrent:
    def from_dict(self, row):
        self.__dict__.update({k: v for k, v in row.items() if k != 'volume_factor'})


class MTorrent:
    _apikey, _ua, _proxy, _url, _timeout, _searchurl = 'tracker-key', 'UA', None, 'https://tracker/', 10, 'https://tracker/api'

    def __init__(self, site):
        pass

    def __get_params(self, keyword, mtype, page):
        return {'keyword': keyword, 'categories': ['401'], 'pageNumber': page + 1, 'pageSize': 100}

    def __parse_result(self, rows):
        return rows


# Keep Python's name-mangled MP extension seam identical to production.
MTorrent._MTorrentSpider__get_params = MTorrent._MTorrent__get_params
MTorrent._MTorrentSpider__parse_result = MTorrent._MTorrent__parse_result


def module(name, **attrs):
    value = types.ModuleType(name)
    value.__dict__.update(attrs)
    return value


class BridgeContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stubs = {
            'fastapi': module('fastapi', HTTPException=HTTPException),
            'app.sdk.plugin': module('app.sdk.plugin', _PluginBase=type('Base', (), {})),
            'app.application.site.sites': module('app.application.site.sites', SitesHelper=type('Sites', (), {})),
            'app.domain.context': module('app.domain.context', TorrentInfo=Torrent),
            'app.application.rss': module('app.application.rss', RssHelper=type('RSS', (), {})),
            'app.chain.download': module('app.chain.download', DownloadChain=type('Download', (), {})),
            'app.chain.site': module('app.chain.site', SiteChain=type('Site', (), {})),
            'app.chain.torrents': module('app.chain.torrents', TorrentsChain=type('Torrents', (), {})),
            'app.modules.indexer': module('app.modules.indexer', IndexerModule=type('Indexer', (), {}), SPIDER_PARSER_CLASSES={}),
            'app.modules.indexer.spider': module('app.modules.indexer.spider', mtorrent=module('mtorrent', MTorrentSpider=MTorrent)),
            'app.schemas.types': module('app.schemas.types', MediaType=types.SimpleNamespace(MOVIE='movie', TV='tv')),
        }
        path = Path(__file__).parent / 'plugins.v2/dian115bridge/__init__.py'
        spec = importlib.util.spec_from_file_location('dian115bridge_test', path)
        cls.bridge_module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, stubs):
            spec.loader.exec_module(cls.bridge_module)

    def setUp(self):
        self.mod = self.bridge_module
        self.plugin = self.mod.Dian115Bridge()
        self.plugin.init_plugin({'enabled': True})

    def test_disabled_and_auth_contract(self):
        self.plugin.init_plugin()
        with self.assertRaises(HTTPException) as raised:
            self.plugin.capabilities({})
        self.assertEqual(409, raised.exception.status_code)
        for api in self.plugin.get_api():
            self.assertEqual('apikey', api['auth'])
            self.assertEqual(['POST'], api['methods'])

    def test_disabled_site_is_not_executable(self):
        with patch.object(self.mod.SitesHelper, 'get_indexers', lambda _: [{'id': 13, 'is_active': False}], create=True):
            with self.assertRaises(HTTPException) as raised:
                self.plugin._site({'site_id': 13})
        self.assertEqual(409, raised.exception.status_code)

    def test_torrent_reconstructs_dataclass_and_uses_current_site_credentials(self):
        captured = []
        self.plugin._site = lambda _: {'id': 13, 'name': 'site', 'cookie': 'current', 'ua': 'UA'}
        with patch.object(self.mod.DownloadChain, 'download_torrent', lambda _, torrent: (captured.append(torrent) or b'torrent', '', []), create=True):
            result = self.plugin.torrent({'torrent': {'site': 13, 'title': 'Show', 'volume_factor': 'free', 'site_cookie': 'stale'}})
        self.assertEqual(b'torrent', base64.b64decode(result['data']['content']))
        self.assertEqual('current', captured[0].site_cookie)
        with self.assertRaises(HTTPException):
            self.plugin.torrent({'torrent': {'site': 12}})

    def test_bridge_exposes_no_downloader_execution(self):
        paths = {api['path'] for api in self.plugin.get_api()}
        self.assertEqual({'/capabilities', '/search', '/torrent', '/rss', '/rss_url', '/userdata'}, paths)
        operations = set(self.plugin.capabilities({})['data']['operations'])
        self.assertFalse(operations & {'downloader', 'file_selection', 'delete_keep_files'})

    def test_mteam_window_mode_and_business_error(self):
        captured = []
        class Request:
            def __init__(self, **kwargs): pass
            def post_res(self, **kwargs):
                captured.append(kwargs)
                return types.SimpleNamespace(status_code=200, json=lambda: {'code': '0', 'data': {'data': []}})
        with patch.object(self.mod.mp_mtorrent, 'RequestUtils', Request, create=True):
            rows, count = self.mod._BoundMTorrent({}).search_bound({'keyword': 'Show', 'page': 2, 'category': '401,402', 'mteam_mode': 'adult', 'published_after': '2026-11-11T00:00:00Z', 'published_before': '2026-11-12T00:00:00Z'}, None)
        params = captured[0]['json']
        self.assertEqual(['401', '402'], params['categories'])
        self.assertEqual(3, params['pageNumber'])
        self.assertEqual('adult', params['mode'])
        self.assertEqual('2026-11-11 08:00:00', params['uploadDateStart'])
        self.assertEqual('DESC', params['sortDirection'])
        self.assertEqual(([], 0), (rows, count))
        Request.post_res = lambda *args, **kwargs: types.SimpleNamespace(status_code=200, json=lambda: {'code': '403', 'data': {}})
        with patch.object(self.mod.mp_mtorrent, 'RequestUtils', Request, create=True), self.assertRaises(HTTPException) as raised:
            self.mod._BoundMTorrent({}).search_bound({}, None)
        self.assertEqual(502, raised.exception.status_code)


if __name__ == '__main__':
    unittest.main()
