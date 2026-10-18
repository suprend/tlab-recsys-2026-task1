"""Independent small CSV witnesses for H&M ingestion and temporal EDA."""
import csv
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

import duckdb

from scripts.hm_eda import SCHEMAS, FILES, cohort_audit, load_sources, run


USERS = [format(i,'064x') for i in range(1,6)]
ARTICLES = ['0108775015','0110065001','0110065002']


def write_fixture(raw):
    """Customer4 has stale history; customer5 never purchases."""
    raw.mkdir()
    customers = [dict.fromkeys(SCHEMAS['customers'],'') for _ in USERS]
    for user,row in zip(USERS,customers):
        row.update(customer_id=user,age=30)
    articles = [dict.fromkeys(SCHEMAS['articles'],'fixture') for _ in ARTICLES]
    for article,row in zip(ARTICLES,articles):
        row['article_id'] = article
    # Retain identical rows: they may encode units, not data corruption.
    purchases = [
        ('2020-08-11',USERS[0],ARTICLES[0]),
        ('2020-08-11',USERS[0],ARTICLES[0]),
        ('2020-08-12',USERS[0],ARTICLES[0]),
        ('2020-08-18',USERS[0],ARTICLES[1]),
        ('2020-08-19',USERS[0],ARTICLES[2]),
        ('2020-08-12',USERS[1],ARTICLES[2]),
        ('2020-08-10',USERS[2],ARTICLES[1]),
        ('2020-04-01',USERS[3],ARTICLES[0]),
        ('2020-08-13',USERS[3],ARTICLES[0]),
    ]
    transactions = [dict(t_dat=d,customer_id=u,article_id=a,price='0.1',sales_channel_id='1')
                    for d,u,a in purchases]
    for table, records in [('customers',customers),('articles',articles),('transactions',transactions)]:
        with (raw/FILES[table]).open('w',encoding='utf-8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(SCHEMAS[table]))
            writer.writeheader()
            writer.writerows(records)


class HmEdaTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.raw=self.root/'raw'
        write_fixture(self.raw)

    def tearDown(self):
        self.tmp.cleanup()

    def test_explicit_types_keep_leading_zero_and_raw_identical_purchases(self):
        con=duckdb.connect(':memory:')
        try:
            load_sources(con,self.raw)
            self.assertEqual(con.execute("SELECT typeof(article_id),min(article_id),count(*) FROM transactions GROUP BY 1").fetchone(),
                             ('VARCHAR',ARTICLES[0],9))
            self.assertEqual(con.execute("SELECT count(*) FROM transactions WHERE customer_id=? AND t_dat=DATE '2020-08-11'",[USERS[0]]).fetchone()[0],2)
        finally:
            con.close()

    def test_strict_history_cold_purchases_no_purchase_and_end_boundary(self):
        con=duckdb.connect(':memory:')
        try:
            load_sources(con,self.raw)
            cohort=cohort_audit(con,dt.date(2020,8,12))
        finally:
            con.close()
        # Manually enumerated oracle: labels users1/2/4; history90 users1/3.
        self.assertEqual(cohort['positive_users'],3)
        self.assertEqual(cohort['cold_positive_users'],1)
        self.assertEqual(cohort['positive_with_prior30d'],1)
        self.assertEqual(cohort['positive_with_prior90d'],1)
        self.assertEqual(cohort['active_prior90d_users'],2)
        self.assertEqual(cohort['active_prior90d_no_purchase_users'],1)
        self.assertEqual(cohort['active_prior90d_positive_rate'],.5)
        self.assertEqual(cohort['label_purchase_rows'],4)
        self.assertEqual(cohort['distinct_user_article_labels'],4)

    def test_reports_aggregate_only_input_unchanged_and_collision_refused(self):
        before={p.name:p.read_bytes() for p in self.raw.iterdir()}
        output=self.root/'out'
        report=run(self.raw,output)
        self.assertEqual(report['tables']['transactions']['rows'],9)
        self.assertEqual(report['tables']['transactions']['exact_duplicates'],
                         {'extra_rows':1,'repeated_groups':1,'rows_in_repeated_groups':2})
        self.assertTrue(all(report['validation'].values()))
        self.assertEqual(report['customers_without_transactions'],1)
        self.assertEqual(sum(row['purchase_rows'] for row in report['aggregates']['daily']),9)
        self.assertEqual(report['foreign_keys']['article_id']['orphan_transaction_rows'],0)
        content=(output/'summary.json').read_text(encoding='utf-8')+(output/'report.md').read_text(encoding='utf-8')
        for private_id in USERS+ARTICLES:
            self.assertNotIn(private_id,content)
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.raw.iterdir()})
        prior=(output/'summary.json').read_bytes()
        with self.assertRaises(FileExistsError):
            run(self.raw,output)
        self.assertEqual(prior,(output/'summary.json').read_bytes())
        saved=json.loads((output/'summary.json').read_text(encoding='utf-8'))
        self.assertFalse(saved['tables']['transactions']['matches_reference_rows'])

    def test_metadata_duplicate_and_orphan_are_diagnostics_not_join_amplification(self):
        with (self.raw/FILES['articles']).open('a',encoding='utf-8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(SCHEMAS['articles']))
            row=dict.fromkeys(SCHEMAS['articles'],'different')
            row['article_id']=ARTICLES[0]
            writer.writerow(row)
        with (self.raw/FILES['transactions']).open('a',encoding='utf-8',newline='') as stream:
            csv.writer(stream).writerow(['2020-08-14',USERS[0],'0999999999',.2,'2'])
        report=run(self.raw,self.root/'out')
        self.assertFalse(report['validation']['metadata_keys_unique'])
        self.assertFalse(report['validation']['foreign_keys_complete'])
        self.assertEqual(report['tables']['articles']['duplicate_keys']['extra_rows'],1)
        self.assertEqual(report['foreign_keys']['article_id']['orphan_transaction_rows'],1)
        self.assertEqual(report['weekly_cohorts'][0]['label_purchase_rows'],5)

    def test_schema_drift_is_rejected(self):
        path=self.raw/FILES['customers']
        path.write_text('customer_id,age\n',encoding='utf-8')
        con=duckdb.connect(':memory:')
        try:
            with self.assertRaisesRegex(ValueError,'CSV header'):
                load_sources(con,self.raw)
        finally:
            con.close()


if __name__=='__main__':
    unittest.main()
