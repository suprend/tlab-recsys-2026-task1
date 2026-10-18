"""Synthetic byte witnesses for immutable H&M source downloads."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.hm_download import download


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.payloads = {name: (name + '\n').encode() for name in
                         ('articles.csv', 'customers.csv', 'transactions_train.csv')}
        config = {'dataset': 'synthetic witness', 'mirror': 'fixture/test',
                  'revision': 'abc123', 'original_url': 'https://example.test/original',
                  'rules_url': 'https://example.test/rules', 'files': [
                      {'path': 'data/raw/' + name, 'size': len(data),
                       'sha256': hashlib.sha256(data).hexdigest()}
                      for name, data in self.payloads.items()]}
        self.config = self.root / 'source.json'
        self.config.write_text(json.dumps(config), encoding='utf-8')
        self.out = self.root / 'raw'

    def tearDown(self):
        self.temp.cleanup()

    def source(self, request, timeout):
        name = request.full_url.split('/')[-1].split('?')[0]
        return io.BytesIO(self.payloads[name])

    def test_verified_files_and_idempotent_rerun_do_not_use_network(self):
        with patch('scripts.hm_download.urlopen', side_effect=self.source) as network:
            result = download(self.config, self.out)
            self.assertEqual(network.call_count, 3)
        self.assertEqual(result['status'], 'complete')
        for name, data in self.payloads.items():
            self.assertEqual((self.out / name).read_bytes(), data)
        with patch('scripts.hm_download.urlopen', side_effect=AssertionError('network')):
            self.assertEqual(download(self.config, self.out)['status'], 'complete')

    def test_bad_network_bytes_remain_partial_and_cannot_be_adopted(self):
        wrong = b'x' * len(self.payloads['articles.csv'])
        with patch('scripts.hm_download.urlopen', return_value=io.BytesIO(wrong)):
            with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
                download(self.config, self.out)
        self.assertFalse((self.out / 'articles.csv').exists())
        self.assertEqual((self.out / 'articles.csv.part').read_bytes(), wrong)
        self.assertEqual(json.loads((self.out / 'download.json').read_text())['status'], 'failed')
        with patch('scripts.hm_download.urlopen', side_effect=AssertionError('network')):
            with self.assertRaises(FileExistsError):
                download(self.config, self.out)

    def test_existing_bad_file_preserved(self):
        self.out.mkdir()
        path = self.out / 'articles.csv'
        path.write_bytes(b'owner content')
        with patch('scripts.hm_download.urlopen', side_effect=AssertionError('network')):
            with self.assertRaisesRegex(ValueError, 'preserved'):
                download(self.config, self.out)
        self.assertEqual(path.read_bytes(), b'owner content')


if __name__ == '__main__':
    unittest.main()
