import unittest
from live_data.odds_audit import parse_market, market_identity, fixture_identity, candidate_key, quote_key


class OddsAuditTests(unittest.TestCase):
    teams = ['Local FC','Visitante FC']

    def market(self,title,label):
        return {'title':title,'selections':[{'aria':f'Bet on {label} with odds 1.83.'}]}

    def test_exact_scope_line_and_half_time_exclusion(self):
        q = parse_market(self.market('Local FC - Goles totales Más/Menos','Más de 1.5'),self.teams)[0]
        self.assertEqual(quote_key(q),('goals','home','over',1.5,''))
        self.assertIsNone(market_identity('Más/Menos Goles en Primer Tiempo',self.teams))
        self.assertIsNone(market_identity('Jugador Uno Remates totales',self.teams))
        self.assertNotEqual(quote_key(q),('goals','total','over',1.5,''))
        self.assertNotEqual(quote_key(q),('goals','home','over',2.5,''))

    def test_asian_handicap_settlement_and_joint_direction(self):
        self.assertIsNone(market_identity('Hándicap Resultado del Partido',self.teams))
        q = parse_market(self.market('Hándicap Asiático (Resultado actual 0 - 0)','Visitante FC +1.5'),self.teams)[0]
        c = {'kind':'handicap','scope':'total','side':'away','line':1.5,'id':'handicap:total:away:1.5:'}
        self.assertEqual(quote_key(q),candidate_key(c))
        q = parse_market(self.market('Doble Oportunidad con Más/Menos (3.5)','Local FC o Empate y Menos 3.5'),self.teams)[0]
        self.assertEqual(quote_key(q),('result_goals','total','1X',3.5,'under'))

    def test_fixture_identity_requires_both_teams_and_exact_kickoff(self):
        target = {'betano':{'text':'Local FC\nVisitante FC'},'kickoff_utc':'2026-10-25T19:45:00+00:00'}
        page = {'heading':['Local FC\nVisitante FC'],'top':'Domingo, 25 Octubre 2026 14:45'}
        self.assertTrue(fixture_identity(target,page))
        page['top']='Domingo, 25 Octubre 2026 14:30'
        self.assertFalse(fixture_identity(target,page))
        page['top']='Domingo, 25 Octubre 2026 14:45';page['heading']=['Visitante FC\nLocal FC']
        self.assertFalse(fixture_identity(target,page))


if __name__=='__main__': unittest.main()
