#!/usr/bin/env python3
"""Install a wheel outside this checkout and exercise the distributed interface."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import venv

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wheel', type=Path)
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    with tempfile.TemporaryDirectory(prefix='sql-orient-wheel-') as temporary:
        work = Path(temporary)
        venv.create(work/'env', with_pip=True, symlinks=True)
        python = work/'env/bin/python'
        cli = work/'env/bin/sql-orient'
        env = dict(os.environ)
        env.pop('PYTHONPATH', None)
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        def run(argv, success=True):
            p = subprocess.run([str(a) for a in argv],cwd=work,env=env,capture_output=True,text=True)
            assert (p.returncode == 0) == success, (p.stdout,p.stderr)
            return p
        run([python,'-m','pip','install','--no-deps',wheel])
        shutil.copytree(ROOT/'tests/fixtures/mini',work/'mini')
        shutil.copyfile(ROOT/'examples/callers.sql',work/'callers.sql')
        assert not (work/'env/bin/codeindex').exists()
        run([python,'-c',"import importlib.util; import sql_orient; assert importlib.util.find_spec('codeindex') is None; assert 'site-packages' in sql_orient.__file__"])
        for name, extra in [('graph',[]),('paired',['--scip','mini/scip.json'])]:
            run([cli,'build','--repo','mini/repo','--graph','mini/graph.json','--db',name+'.db',*extra])
            p=run([cli,'sql','--db',name+'.db','--file','callers.sql'])
            assert p.stdout == 'caller\trelation\ttarget\nbeta()\tcalls\talpha()\nbeta()\tcalls\talpha()\n'
            p=run([cli,'sql','--db',name+'.db','--query','SELECT COUNT(*) AS n FROM g_nodes','--format','json'])
            assert json.loads(p.stdout)['rows'] == [[15]]
            p=run([cli,'sql','--db',name+'.db','--query','SELECT id FROM g_nodes ORDER BY id','--format','json','--max-rows','1'])
            assert json.loads(p.stdout)['delivery']['more_rows']
            p=run([cli,'sql','--db',name+'.db','--query','DELETE FROM g_nodes'],False)
            assert not p.stdout and 'not authorized' in p.stderr
        (work/'bad.json').write_text('{')
        p=run([cli,'build','--repo','mini/repo','--graph','mini/graph.json','--scip','bad.json','--db','bad.db'],False)
        assert 'invalid JSON' in p.stderr and 'Traceback' not in p.stderr and not (work/'bad.db').exists()
        p=run([python,'-m','sql_orient','sql','--db','paired.db','--query','SELECT COUNT(*) FROM s_occurrences'])
        assert p.stdout == 'COUNT(*)\n28\n'
    print('Installed wheel outside checkout: Graphify-only, SCIP JSON, diagnostics, quickstart TSV, bounded JSON, read-only SQL and alias absence passed.')


if __name__ == '__main__':
    main()
