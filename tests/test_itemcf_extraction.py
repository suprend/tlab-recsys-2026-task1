"""Invented typed9 integration fixtures; no project dataset or native ML used."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

import duckdb

from scripts.itemcf_extraction import (ExtractionLimits, ItemCFQuery,
                                      SourceContract, extract_itemcf_snapshot)
from scripts.itemcf_projection import LimitExceeded, project_itemcf


class ItemCFExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.b = datetime(2020, 1, 10, tzinfo=timezone.utc)
        self.connections = []

    def _database(self, events):
        path = Path(self.temporary.name) / "invented.duckdb"
        writer = duckdb.connect(str(path))
        try:
            writer.execute("""CREATE TABLE events (
                event_time TIMESTAMP, event_type VARCHAR, product_id BIGINT,
                category_id BIGINT, category_code VARCHAR, brand VARCHAR,
                price DECIMAL(12,2), user_id BIGINT, user_session VARCHAR)""")
            writer.executemany("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               [(stamp.replace(tzinfo=None), action, item, None,
                                 None, None, None, user, None)
                                for stamp, action, item, user in events])
        finally:
            writer.close()

        def open_source():
            connection = duckdb.connect(str(path), read_only=True,
                                        config={"threads": 2, "memory_limit": "128MB",
                                                "max_temp_directory_size": "0B"})
            self.connections.append(connection)
            return connection

        return open_source

    def _source(self, count):
        return SourceContract(count, self.b - timedelta(days=10),
                              self.b + timedelta(days=1))

    def _events(self):
        b = self.b
        events = [(b - timedelta(minutes=item), "view", item, 1)
                  for item in range(1, 22)]
        events += [(b - timedelta(days=6), "view", 9000, 1),
                   (b - timedelta(seconds=30), "view", None, 1),
                   (b - timedelta(seconds=10), "cart", 999, 1),
                   (b - timedelta(seconds=15), "cart", 9000, 5)]
        events += [(b - timedelta(days=7), "view", item, user)
                   for user in (2, 3, 4) for item in (9000, 2)]
        events += [(b - timedelta(days=7, seconds=1), "view", item, 5)
                   for item in (9000, 2)]
        events += [(b - timedelta(days=2), "view", 9000, None),
                   (b - timedelta(days=7), "view", 9000, 2),
                   (b, "view", 9000, 5)]
        return events

    def _assert_closed(self):
        self.assertEqual(len(self.connections), 1)
        with self.assertRaises(duckdb.Error):
            self.connections[0].execute("SELECT 1")

    def test_literal_source_to_projection_and_empty_query(self):
        events = self._events()
        queries = (ItemCFQuery("q1", 1, (9000, 1, 8888)), ItemCFQuery("empty", 99, ()))
        self.assertEqual(len(events) + len(queries) + 3, 41)
        snapshots = extract_itemcf_snapshot(
            self._database(events), queries, b=self.b, source=self._source(36),
            limits=ExtractionLimits(1000, 28, 10000), check=lambda: None)
        self._assert_closed()
        main, empty = snapshots
        self.assertEqual((main.query_id, main.user_id, main.candidates),
                         ("q1", 1, (9000, 1, 8888)))
        self.assertEqual(main.latest21, tuple(range(1, 22)))
        expected = {item: (1,) for item in range(1, 22)}
        expected.update({2: (1, 2, 3, 4), 9000: (1, 2, 3, 4), 8888: ()})
        self.assertEqual(main.postings, expected)
        self.assertEqual((empty.query_id, empty.candidates, empty.latest21,
                          empty.postings), ("empty", (), (), {}))
        rows = project_itemcf(main.user_id, main.candidates, main.latest21,
                              main.postings, max_members=28, max_work=10000,
                              check=lambda: None)
        self.assertEqual([row["product_id"] for row in rows], [9000, 1, 8888])
        self.assertAlmostEqual(rows[0]["itemcf_mean"], 3 / 260)
        self.assertAlmostEqual(rows[0]["itemcf_max"], 3 / 13)
        self.assertEqual((rows[0]["pair_support_max"], rows[0]["supported_pairs"],
                          rows[0]["history_n"]), (3, 1, 20))
        self.assertAlmostEqual(rows[0]["defined_fraction"], 1 / 20)
        self.assertEqual((rows[1]["history_n"], rows[1]["candidate_cold"],
                          rows[1]["itemcf_mean"]), (20, True, 0.0))
        self.assertTrue(rows[2]["candidate_cold"])

    def test_zero_offset_anchor_normalizes_before_seven_day_arithmetic(self):
        opened = []

        def forbidden_opener():
            opened.append(True)
            raise AssertionError("Empty batch must not open a source")

        # London is UTC at this anchor, but was UTC+1 seven calendar days ago.
        b = datetime(2020, 10, 26, tzinfo=ZoneInfo("Europe/London"))
        source = SourceContract(0, datetime(2020, 10, 19, tzinfo=timezone.utc),
                                datetime(2020, 10, 26, tzinfo=timezone.utc))
        snapshots = extract_itemcf_snapshot(
            forbidden_opener, (), b=b, source=source,
            limits=ExtractionLimits(0, 0, 0), check=lambda: None)
        self.assertEqual(snapshots, ())
        self.assertEqual(opened, [])

    def test_full_source_descriptor_refuses_before_opener_or_callback(self):
        calls = []

        def forbidden():
            calls.append("called")
            raise AssertionError("Refused source must not be opened/checked")

        with self.assertRaisesRegex(LimitExceeded, "Two-full-pass"):
            extract_itemcf_snapshot(
                forbidden, (ItemCFQuery("q", 1, (1,)),), b=self.b,
                source=self._source(42448764),
                limits=ExtractionLimits(30000000, 100, 100000000), check=forbidden)
        self.assertEqual(calls, [])

    def test_literal_signed_decimal_hash_tie_order(self):
        stamp = self.b - timedelta(seconds=1)
        events = [(stamp, "view", item, 1) for item in (1, 2, 3, -1)]
        snapshot, = extract_itemcf_snapshot(
            self._database(events), (ItemCFQuery("tie", 1, ()),), b=self.b,
            source=self._source(4), limits=ExtractionLimits(100, 4, 1000),
            check=lambda: None)
        # Literal SHA256 UTF8 order: '-1', '3', '1', '2'; not numeric/insertion.
        self.assertEqual(snapshot.latest21, (-1, 3, 1, 2))
        self.assertEqual(snapshot.postings, {-1: (1,), 1: (1,), 2: (1,), 3: (1,)})
        self._assert_closed()

    def test_member_limit_refuses_complete_result_and_closes(self):
        with self.assertRaisesRegex(LimitExceeded, "max_members"):
            extract_itemcf_snapshot(
                self._database(self._events()), (ItemCFQuery("q", 1, (9000, 1, 8888)),),
                b=self.b, source=self._source(36),
                limits=ExtractionLimits(1000, 27, 10000), check=lambda: None)
        self._assert_closed()


if __name__ == "__main__":
    unittest.main()
