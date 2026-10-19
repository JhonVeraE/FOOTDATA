"""Static delivery checks: every forecast must have real local image assets."""
import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

WEB=Path(__file__).resolve().parents[1]/'web'

class WebAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assets=json.loads((WEB/'data/assets.json').read_text(encoding='utf-8'))
        cls.predictions=json.loads((WEB/'data/predictions.json').read_text(encoding='utf-8'))

    def test_every_forecast_team_has_a_cached_crest(self):
        teams={t for m in self.predictions['matches'] for t in [m['local'],m['visitante']]}
        self.assertFalse(teams-set(self.assets['teams']))
        for team in teams:self.assertTrue((WEB/self.assets['teams'][team]['image']).is_file(),team)

    def test_every_target_competition_has_an_emblem(self):
        for league in ['La Liga','Premier League','Bundesliga','Serie A','Ligue 1','UEFA Champions League']:
            self.assertIn(league,self.assets['competitions'])
            self.assertTrue((WEB/self.assets['competitions'][league]['image']).exists())

    def test_local_paths_and_image_formats(self):
        for item in list(self.assets['teams'].values())+list(self.assets['competitions'].values()):
            path=WEB/item['image']
            self.assertTrue(path.resolve().is_relative_to((WEB/'assets').resolve()))
            content=path.read_bytes()
            if path.suffix=='.svg':
                tree=ET.fromstring(content)
                for node in tree.iter():
                    self.assertNotIn(node.tag.split('}')[-1],['script','foreignObject'])
                    self.assertFalse(any(k.lower().startswith('on') for k in node.attrib))
            else:self.assertTrue(content.startswith(b'\x89PNG'))

    def test_asset_manifest_contains_no_download_failures(self):
        self.assertEqual(self.assets['failures'],[])

if __name__=='__main__':unittest.main()
