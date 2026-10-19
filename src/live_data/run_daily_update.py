"""Daily current-season update; optional API-Football remains separate."""
import argparse

def main(max_stats=None,api_football=False):
    if api_football:
        from fetch_fixtures import main as fixtures
        from fetch_team_stats import main as stats
        fixtures();stats(max_nuevos=max_stats)
        print('API-Football raw files updated. They are not silently mixed with canonical match statistics.')
    else:
        from refresh_calendar import main as refresh
        from generate_jornada_predictions import main as predictions
        from content_brief import main as content
        refresh();predictions();content()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--api-football',action='store_true');p.add_argument('--max-stats',type=int)
    args=p.parse_args();main(args.max_stats,args.api_football)
