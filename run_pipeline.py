"""Single project entry point. Data acquisition and evaluation are explicit."""
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'src/live_data'))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--refresh-calendar',action='store_true')
    parser.add_argument('--evaluate',action='store_true')
    parser.add_argument('--excel',action='store_true')
    args=parser.parse_args()
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
