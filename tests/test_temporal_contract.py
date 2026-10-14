"""Contract checks use hand-computed cases and an independent SQL oracle."""

from datetime import datetime, timedelta, timezone
import itertools
import unittest

import duckdb

from scripts.temporal_contract import (
    closed_utc_days,
    history_window,
    label_is_mature,
    observed_history_age,
    source_coverage,
    target_window,
    timestamp_batches,
)

UTC = timezone.utc
S = datetime(2019, 10, 1, tzinfo=UTC)
E = datetime(2019, 11, 1, tzinfo=UTC)
DAY = timedelta(days=1)


class TemporalContractTests(unittest.TestCase):
    def test_strict_history_boundaries(self):
        anchor = S + 2 * DAY
        window = history_window(anchor, DAY)
        self.assertFalse(window.contains(anchor - DAY - timedelta(seconds=1)))
        self.assertTrue(window.contains(anchor - DAY))
        self.assertTrue(window.contains(anchor - timedelta(seconds=1)))
        self.assertFalse(window.contains(anchor))
        self.assertFalse(window.contains(anchor + timedelta(seconds=1)))

    def test_rolling_and_completed_days_have_different_meanings(self):
        anchor = S + 2 * DAY + timedelta(hours=15)
        rolling, calendar = history_window(anchor, DAY), closed_utc_days(anchor, 1)
        self.assertEqual(rolling.start, S + DAY + timedelta(hours=15))
        self.assertEqual(calendar.start, S + DAY)
        self.assertEqual(calendar.end, S + 2 * DAY)
        self.assertTrue(rolling.contains(S + 2 * DAY + timedelta(hours=10)))
        self.assertFalse(calendar.contains(S + 2 * DAY + timedelta(hours=10)))

    def test_timezone_is_explicit_and_normalized(self):
        offset = timezone(timedelta(hours=3))
        local = datetime(2019, 10, 2, 3, tzinfo=offset)
        self.assertEqual(history_window(local, DAY), history_window(S + DAY, DAY))
        with self.assertRaisesRegex(ValueError, 'timezone-aware'):
            history_window(datetime(2019, 10, 2), DAY)

    def test_source_coverage_is_separate_from_user_age(self):
        anchor = S + 6 * DAY
        coverage = source_coverage(history_window(anchor, 7 * DAY), source_start=S, source_end=E)
        self.assertEqual(coverage.observed_seconds, 6 * 86400)
        self.assertEqual(coverage.fraction, 6 / 7)
        self.assertFalse(coverage.complete)
        self.assertEqual(observed_history_age(anchor, anchor - timedelta(seconds=1)), timedelta(seconds=1))
        self.assertEqual(coverage.observed_seconds, 6 * 86400)

    def test_october_has_full_thirty_days_only_on_october_31(self):
        for anchor, complete in [(S, False), (S + 29 * DAY, False), (S + 30 * DAY, True)]:
            result = source_coverage(history_window(anchor, 30 * DAY), source_start=S, source_end=E)
            self.assertEqual(result.complete, complete)
        self.assertEqual(source_coverage(history_window(S, DAY), source_start=S, source_end=E).fraction, 0)
        self.assertEqual(source_coverage(history_window(E + DAY, DAY), source_start=S, source_end=E).fraction, 0)

    def test_first_anchor_has_unknown_age_not_zero(self):
        for first in (None, S, S + timedelta(seconds=1)):
            self.assertIsNone(observed_history_age(S, first))
        self.assertEqual(observed_history_age(S + DAY, S), DAY)

    def test_target_endpoint_choices_are_explicit(self):
        for include_anchor, include_end in itertools.product((False, True), repeat=2):
            window = target_window(S, DAY, include_anchor=include_anchor, include_end=include_end)
            self.assertEqual(window.contains(S), include_anchor)
            self.assertEqual(window.contains(S + DAY), include_end)
            self.assertTrue(window.contains(S + timedelta(seconds=1)))
            self.assertFalse(window.contains(S - timedelta(seconds=1)))

    def test_maturity_obeys_right_endpoint_and_availability_delay(self):
        right_open = target_window(S, DAY, include_anchor=True, include_end=False)
        right_closed = target_window(S, DAY, include_anchor=False, include_end=True)
        self.assertTrue(label_is_mature(right_open, available_before=S + DAY))
        self.assertFalse(label_is_mature(right_closed, available_before=S + DAY))
        self.assertTrue(label_is_mature(right_closed, available_before=S + DAY + timedelta(seconds=1)))
        self.assertFalse(label_is_mature(right_open, available_before=S + DAY, availability_delay=timedelta(seconds=1)))
        self.assertTrue(label_is_mature(right_open, available_before=S + DAY + timedelta(seconds=1), availability_delay=timedelta(seconds=1)))

    def test_invalid_durations_and_source_bounds_fail(self):
        for duration in (timedelta(0), -DAY):
            with self.assertRaises(ValueError):
                history_window(S, duration)
        for days in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                closed_utc_days(S, days)
        with self.assertRaises(ValueError):
            source_coverage(history_window(S, DAY), source_start=E, source_end=S)
        target = target_window(S, DAY, include_anchor=False, include_end=False)
        with self.assertRaises(ValueError):
            label_is_mature(target, available_before=E, availability_delay=-DAY)

    @staticmethod
    def _replay_counts(events):
        history = []
        result = {}
        for anchor, peers in timestamp_batches(events, timestamp=lambda row: row[1]):
            window = history_window(anchor, DAY)
            # Read globally for all users before one batch update.
            for event_id, _, _, item in peers:
                result[event_id] = sum(row[3] == item and window.contains(row[1]) for row in history)
            history.extend(peers)
        return result

    def test_replay_matches_hand_computed_counts_and_independent_sql(self):
        events = [
            ('a', S, 'u1', 'item'),
            ('b', S, 'u2', 'item'),
            ('c', S + timedelta(seconds=1), 'u2', 'item'),
            ('d', S + DAY, 'u3', 'item'),
            ('e', S + DAY, 'u4', 'other'),
            ('f', S + DAY + timedelta(seconds=1), 'u1', 'item'),
        ]
        replay = self._replay_counts(events)
        self.assertEqual(replay, {'a': 0, 'b': 0, 'c': 2, 'd': 3, 'e': 0, 'f': 2})
        con = duckdb.connect(':memory:')
        try:
            con.execute('CREATE TABLE fixture(event_id VARCHAR, event_time TIMESTAMPTZ, user_id VARCHAR, item_id VARCHAR)')
            con.executemany('INSERT INTO fixture VALUES (?,?,?,?)', events)
            oracle = dict(con.execute("""
                SELECT a.event_id, (SELECT count(*) FROM fixture h
                    WHERE h.item_id=a.item_id
                      AND h.event_time >= a.event_time - INTERVAL '1 day'
                      AND h.event_time < a.event_time)
                FROM fixture a
            """).fetchall())
            self.assertEqual(replay, oracle)
        finally:
            con.close()

    def test_peer_permutation_and_future_suffix_do_not_change_past_features(self):
        peers = [('a', S, 'u1', 'item'), ('b', S, 'u2', 'item'), ('c', S, 'u3', 'other')]
        later = [('d', S + timedelta(seconds=1), 'u4', 'item')]
        expected = {'a': 0, 'b': 0, 'c': 0, 'd': 2}
        for order in itertools.permutations(peers):
            events = list(order) + later
            self.assertEqual(self._replay_counts(events), expected)
            future = ('future', S + 2 * DAY, 'u5', 'item')
            extended = self._replay_counts(events + [future])
            self.assertEqual({key: extended[key] for key in expected}, expected)

    def test_stream_rejects_backwards_time_and_accepts_empty_input(self):
        self.assertEqual(list(timestamp_batches([], timestamp=lambda row: row)), [])
        with self.assertRaisesRegex(ValueError, 'ordered'):
            list(timestamp_batches([S + DAY, S], timestamp=lambda row: row))


if __name__ == '__main__':
    unittest.main()
