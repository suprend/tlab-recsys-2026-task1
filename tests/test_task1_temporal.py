"""Future category assignment must not change past candidates or ranking features."""
import contextlib
import io
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
import duckdb
from task1 import build, build4, data, leakcheck

class CategoryAsOfTest(unittest.TestCase):
    def test_future_nonnull_category_does_not_change_either_builder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / 'full.duckdb'
            con = duckdb.connect(str(db))
            con.execute('''CREATE TABLE events(event_time TIMESTAMP, event_type VARCHAR, product_id BIGINT,
                           category_id BIGINT, category_code VARCHAR, brand VARCHAR, price DOUBLE,
                           user_id BIGINT, user_session VARCHAR)''')
            con.execute('''INSERT INTO events VALUES
                ('2020-01-13', 'view', 1, NULL, NULL, 'b', 1, 1, 'a'),
                ('2020-01-14', 'purchase', 1, NULL, NULL, 'b', 1, 2, 'b'),
                ('2020-01-14', 'purchase', 2, 123, 'x.y', 'b', 2, 3, 'c'),
                ('2020-01-15 12:00', 'purchase', 3, 123, 'x.y', 'b', 3, 1, 'd'),
                ('2020-01-16', 'view', 1, 123, 'x.y', 'b', 1, 4, 'e')''')
            data.derive(con)
            self.assertEqual(con.execute('SELECT category_id FROM item_static WHERE product_id=1').fetchone(), (123,))
            con.close()
            with patch.object(build, 'DB', db), patch.object(build4, 'DB', db):
                for builder in (build, build4):
                    with self.subTest(builder=builder.__name__):
                        work = root / builder.__name__
                        work.mkdir()
                        with contextlib.redirect_stdout(io.StringIO()):
                            self.assertTrue(leakcheck.check(date(2020, 1, 15), work, builder))
                        con = duckdb.connect()
                        try:
                            rows = con.execute(f"SELECT user_id, product_id, uc_share_hl1d FROM '{work}/full/2020-01-15.parquet'").fetchall()
                            self.assertEqual(rows, [(1, 2, 0.0)])
                        finally:
                            con.close()

if __name__ == '__main__':
    unittest.main()
