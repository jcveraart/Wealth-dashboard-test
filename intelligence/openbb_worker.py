"""Isolated optional OpenBB runtime; stdin/stdout contain only structured public queries."""
import contextlib,json,sys
from pathlib import Path

def main():
    request=json.load(sys.stdin)
    with contextlib.redirect_stdout(sys.stderr):
        # Route the optional runtime's settings/logs into this application's cache.
        # Patch constants before any settings models import their default paths.
        from openbb_core.app import constants
        local=Path(__file__).absolute().parents[1]/'cache'/'openbb'
        constants.OPENBB_DIRECTORY=local
        constants.USER_SETTINGS_PATH=local/'user_settings.json'
        constants.SYSTEM_SETTINGS_PATH=local/'system_settings.json'
        from openbb import obb
        def query(spec):
            node=obb
            for part in spec['command'].split('.'):node=getattr(node,part)
            result=node(**spec['kwargs'])
            return json.loads(result.to_df().reset_index().to_json(orient='records',date_format='iso'))
        if 'queries' in request:
            value={'datasets':{},'unavailable':{}}
            for name,spec in request['queries'].items():
                try:value['datasets'][name]=query(spec)
                except Exception:value['unavailable'][name]='Dataset unavailable from the configured OpenBB provider/version.'
        else:value=query(request)
    print(json.dumps({'data':value}),flush=True)

if __name__=='__main__':
    try:main()
    except Exception as e:print(json.dumps({'error':str(e)[:300]}),flush=True)
