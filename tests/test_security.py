"""Defensive boundary checks with local fixtures only."""
import io
import unittest
import urllib.error
import zipfile
from unittest.mock import patch

from novelengine.ai import ProviderError, http_json
from novelengine.config import validate_provider_url
from novelengine.rag import epub_text


class SecurityTests(unittest.TestCase):
    def test_cloud_url_must_use_tls_or_exact_loopback(self):
        for url in ('http://example.invalid/v1', 'https://example.invalid:99999/v1',
                    'https://user@example.invalid/v1', 'https://example.invalid/v1?test=1'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_provider_url(url, cloud=True)
        validate_provider_url('http://127.0.0.1:8080/v1', cloud=True)
        validate_provider_url('https://example.invalid/v1', cloud=True)

    def test_provider_errors_return_status_without_response_body(self):
        error = urllib.error.HTTPError('https://example.invalid', 400, 'bad request', {},
                                       io.BytesIO(b'private fixture'))
        with patch('novelengine.ai.urllib.request.OpenerDirector.open', side_effect=error):
            with self.assertRaisesRegex(ProviderError, '^HTTP 400 tại nhà cung cấp$'):
                http_json('https://example.invalid', {})

    def test_epub_metadata_size_bound(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('META-INF/container.xml', ' ' * 512_001)
        with self.assertRaisesRegex(ValueError, 'Metadata EPUB'):
            epub_text(buffer.getvalue())
