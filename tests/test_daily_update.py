"""Offline tests of the unattended daily update using saved provider captures."""
import json, shutil, sys, tempfile, unittest
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src/live_data'))
from daily_update import main, freeze_forecasts
from sofascore_capture import parse_capture, compare

CAPTURE = ROOT/'data/artifacts/review_20261027_29'
LIVE = ['match_stats_actualseason.csv', 'match_stats_actualseason.sources.json',
        'match_stats_champions_actualseason.csv', 'match_stats_champions_actualseason.sources.json',
        'matches_footballdata.csv', 'match_stats_4ligas.csv']


class DailyUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.data = self.tmp/'data';self.art = self.tmp/'artifacts';self.web = self.tmp/'web'
        self.data.mkdir();(self.web/'data').mkdir(parents=True)
        for name in LIVE:shutil.copy2(ROOT/'data/live'/name, self.data/name)
        for sub in ['prediction_archive', 'recommendation_archive']:
            shutil.copytree(ROOT/'data/artifacts'/sub, self.art/sub)
        for day in ['2026-10-27', '2026-10-28', '2026-10-29']:
            shutil.copytree(ROOT/'data/artifacts/daily_reviews'/day, self.art/'daily_reviews'/day)

    def tearDown(self):shutil.rmtree(self.tmp)

    def run_offline(self, source=CAPTURE, **kw):
        return main(days=2, end='2026-10-29', source_dir=source, post=False, data_dir=self.data,
                    artifact_dir=self.art, web_dir=self.web, **kw)

    def test_reprocessing_saved_days_adds_nothing_and_writes_nothing(self):
        live = {n: (ROOT/'data/live'/n).read_bytes() for n in LIVE}
        r = main(days=2, end='2026-10-29', source_dir=CAPTURE, apply=False)
        self.assertEqual(r['added_rows'], 0);self.assertEqual(r['finals'], 9)
        self.assertEqual([(p['home'], p['away']) for p in r['pending']], [('Fiorentina', 'Atalanta')])
        for n, b in live.items():self.assertEqual((ROOT/'data/live'/n).read_bytes(), b)

    def test_removed_rows_are_restored_identically_and_rerun_is_idempotent(self):
        path = self.data/'match_stats_actualseason.csv'
        original = pd.read_csv(path)
        pd.read_csv(path).query("date!='2026-10-28'").to_csv(path, index=False)
        r = self.run_offline()
        self.assertEqual(r['added_rows'], 10)
        restored = pd.read_csv(path)
        key = ['match_id', 'team']
        a = original.sort_values(key).reset_index(drop=True);b = restored.sort_values(key).reset_index(drop=True)
        pd.testing.assert_frame_equal(a, b)
        before = {p: p.read_bytes() for p in [path, self.art/'daily_reviews/2026-10-28/ingestion.json']}
        again = self.run_offline()
        self.assertEqual(again['added_rows'], 0)
        for p, data in before.items():self.assertEqual(p.read_bytes(), data)

    def test_score_disagreement_and_missing_statistics_stay_pending(self):
        src = self.tmp/'capture';shutil.copytree(CAPTURE, src)
        fd = json.loads((src/'football_data_matches_range.json').read_text(encoding='utf-8'))
        for m in fd['matches']:
            if str(m['id']) == '558558':m['score']['fullTime']['home'] = 4
        (src/'football_data_matches_range.json').write_text(json.dumps(fd), encoding='utf-8')
        detail_path = src/'2026-10-28/espn_401874773.json'
        detail = json.loads(detail_path.read_text(encoding='utf-8'))
        for team in detail['boxscore']['teams']:
            team['statistics'] = [s for s in team['statistics'] if s['name'] != 'wonCorners']
        detail_path.write_text(json.dumps(detail), encoding='utf-8')
        path = self.data/'match_stats_actualseason.csv'
        pd.read_csv(path).query("date<'2026-10-28'").to_csv(path, index=False)
        r = self.run_offline(source=src, apply=False)
        reasons = {(p['home'], p['away']): p['reason'] for p in r['pending']}
        self.assertIn('Marcador discrepante', reasons[('Frosinone', 'Lecce')])
        by_event = {p['espn_event_id']: p['reason'] for p in r['pending']}
        self.assertIn('wonCorners', by_event['401874773'])
        self.assertNotIn('Serie A_2026/27_espn_401874976', r['added_matches'])

    def test_freeze_uses_latest_pre_kickoff_publication_once(self):
        status = freeze_forecasts('2026-10-31', self.art)
        self.assertTrue(status.startswith('frozen_from:20261026T234507'))
        pred = json.loads((self.art/'daily_reviews/2026-10-31/predictions_before_results.json').read_text(encoding='utf-8'))
        fijas = json.loads((self.art/'daily_reviews/2026-10-31/fijas_before_results.json').read_text(encoding='utf-8'))
        self.assertEqual(pred['run']['dataset_id'], fijas['dataset_id'])
        self.assertEqual(freeze_forecasts('2026-10-31', self.art), 'already_frozen')
        self.assertEqual(freeze_forecasts('2026-10-29', self.art), 'already_frozen')

    def test_sofascore_capture_matches_csv_contract(self):
        capture = {'event': {'event': {'id': 1, 'status': {'type': 'finished'}, 'homeTeam': {'name': 'Fiorentina'},
                                       'awayTeam': {'name': 'Atalanta'}, 'homeScore': {'current': 2}, 'awayScore': {'current': 2}}},
                   'statistics': {'statistics': [{'period': 'ALL', 'groups': [{'statisticsItems': [
                       {'key': 'totalShotsOnGoal', 'homeValue': 26, 'awayValue': 10},
                       {'key': 'shotsOnGoal', 'homeValue': 4, 'awayValue': 5},
                       {'key': 'fouls', 'homeValue': 10, 'awayValue': 13},
                       {'key': 'cornerKicks', 'homeValue': 8, 'awayValue': 2},
                       {'key': 'yellowCards', 'homeValue': 3, 'awayValue': 2}]}]}]},
                   'incidents': {'incidents': [{'incidentType': 'card', 'incidentClass': 'yellow', 'isHome': True}] * 3 +
                                              [{'incidentType': 'card', 'incidentClass': 'yellow', 'isHome': False}] * 2}}
        m = parse_capture(capture)
        self.assertEqual(m['metrics'], {'goals': [2, 2], 'shots': [26, 10], 'sot': [4, 5], 'fouls': [10, 13],
                                        'corners': [8, 2], 'cards': [3, 2]})
        self.assertEqual(m['red'], [0, 0])
        self.assertEqual(compare({'goals': [2, 2], 'shots': [25, 10]}, m['metrics']), {'shots': {'espn': [25, 10], 'sofascore': [26, 10]}})
        del capture['incidents']
        with self.assertRaises(ValueError):parse_capture(capture)  # red cards cannot be assumed zero


if __name__ == '__main__':unittest.main()
