"""Text/JSON content draft using exactly the published prediction contract."""
import json
from paths import DATA_DIR,ARTIFACT_DIR
from generate_jornada_predictions import atomic_json

def build_brief(report):
    return {'fixture_id':report['fixture_id'],'title':f"{report['local']} vs {report['visitante']} · {report['competition']}",
        'prediction_version':report['model']['version'],'dataset_id':report['dataset_id'],'cutoff':report['cutoff'],
        'script_short':f"{report['local']} contra {report['visitante']}. El modelo estima {report['p_home']:.0f}% de victoria local, {report['p_draw']:.0f}% de empate y {report['p_away']:.0f}% de victoria visitante. Goles esperados: {report['lam_home']:.2f} y {report['lam_away']:.2f}. Son probabilidades estimadas. Revisaremos el resultado después del partido.",
        'research_required':['Confirmar alineaciones','Verificar bajas y sanciones con fuente y hora'],
        'data_warnings':report['data_warnings'],'publication_status':'draft','source_prediction':report}

def main():
    data=json.loads((DATA_DIR/'jornada_predictions.json').read_text(encoding='utf-8'))
    briefs=[build_brief(r) for r in data.values()]
    atomic_json(ARTIFACT_DIR/'content_briefs.json',briefs)
    print(f'{len(briefs)} content drafts generated; no external messages or publications sent.')

if __name__=='__main__':main()
