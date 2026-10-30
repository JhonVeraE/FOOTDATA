"""Single project entry point. Data acquisition and evaluation are explicit.

  --daily   unattended results update (ESPN finals, verification, settlement, web)
  --weekly  calendar refresh + daily update + new forecasts and fijas
"""
import argparse,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'src/live_data'))

def daily(days=3):
    from daily_update import main as update
    report=update(days=days)
    if not report.get('healthy',True):sys.exit('ESPN inaccesible: actualización diaria abortada sin cambios.')
    return report

def weekly(excel=False,days=3):
    from settings import secret
    if secret('FOOTBALL_DATA_KEY'):
        from refresh_calendar import main as refresh
        refresh()
        time.sleep(61)  # football-data free tier: 10 requests/minute
    daily(days)
    try:
        # Public bookmaker prices (football-data.co.uk fixtures.csv); optional, returns None offline.
        from market_odds import fetch_market_odds
        fetch_market_odds()
    except Exception as exc:
        print(f'Cuotas de mercado no actualizadas ({type(exc).__name__}); se continúa sin ellas.')
    from generate_jornada_predictions import main as predict
    predict()  # archives predictions and the matching fijas (same dataset_id/run)
    from content_brief import main as content
    content()
    from score_archive import main as score
    score()
    if excel:
        from build_excel_avanzado import main as build_excel
        build_excel()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--refresh-calendar',action='store_true')
    parser.add_argument('--evaluate',action='store_true')
    parser.add_argument('--excel',action='store_true')
    parser.add_argument('--daily',action='store_true')
    parser.add_argument('--weekly',action='store_true')
    parser.add_argument('--days',type=int,default=3)
    args=parser.parse_args()
    if args.daily:return daily(args.days)
    if args.weekly:return weekly(args.excel,args.days)
    if args.refresh_calendar:
        from refresh_calendar import main as refresh
        refresh()
    from build_team_dashboard import main as teams
    teams(refresh=args.refresh_calendar)
    if args.evaluate:
        from evaluate_models import main as evaluate
        evaluate()
    from generate_jornada_predictions import main as predict
    predict()
    from content_brief import main as content
    content()
    from score_archive import main as score
    score()
    if args.excel:
        from build_excel_avanzado import main as excel
        excel()

if __name__=='__main__':main()
