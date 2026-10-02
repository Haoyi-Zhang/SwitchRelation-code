from __future__ import annotations
from pathlib import Path
import sys, tempfile, unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from strict_json import load_strict, loads_strict, StrictJSONError

class StrictJSONTests(unittest.TestCase):
    def test_valid_object(self):
        self.assertEqual(loads_strict('{"a":1,"b":[true,null]}')['a'], 1)
    def test_duplicate_key_rejected(self):
        with self.assertRaises(StrictJSONError):
            loads_strict('{"a":1,"a":2}')
    def test_nan_rejected(self):
        with self.assertRaises(StrictJSONError):
            loads_strict('{"a":NaN}')
    def test_nonobject_rejected(self):
        with self.assertRaises(StrictJSONError):
            loads_strict('[1,2,3]')
    def test_depth_rejected(self):
        with self.assertRaises(StrictJSONError):
            loads_strict('{"a":{"b":{"c":0}}}', max_depth=1)

    def test_file_size_checked_before_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "large.json"
            path.write_text('{"a":12345}', encoding='utf-8')
            with self.assertRaises(StrictJSONError):
                load_strict(path, max_bytes=4)

if __name__ == '__main__':
    unittest.main()
