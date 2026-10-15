#!/usr/bin/env python3
"""Reproduce public aggregate calculations and deterministic SVGs; no experiments."""
import argparse
from decimal import Decimal, ROUND_HALF_UP
from html import escape
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def whole(value):
    return f'{value.quantize(Decimal("1"), rounding=ROUND_HALF_UP):,}'


def render(data, metric):
    values = [(a['label'], Decimal(a[metric + '_sum']) / a['sessions']) for a in data['arms']]
    title = ('Total' if metric == 'total_input' else 'Uncached') + ' input tokens per session'
    desc = '; '.join(f'{label}: {whole(v)}' for label, v in values)
    desc += '. One selected task, 12 blocks; amended set, six environment-failed sessions replaced post hoc in two rounds. No general efficiency or monetary savings established.'
    lines = ['<svg xmlns="http://www.w3.org/2000/svg" width="800" height="390" viewBox="0 0 800 390" role="img" aria-labelledby="title desc">',
             f'<title id="title">{title}</title>', f'<desc id="desc">{escape(desc)}</desc>',
             '<rect width="800" height="390" fill="white"/>',
             '<g font-family="sans-serif" fill="#172033" font-size="18">',
             f'<text x="20" y="30">{title}</text>']
    maximum = 2000000 if metric == 'total_input' else 120000
    for i, (label, value) in enumerate(values):
        y = 75 + i * 70
        width = (value * 500 / maximum).quantize(Decimal('.001'), rounding=ROUND_HALF_UP)
        lines.extend([f'<text x="20" y="{y}">{label}: {whole(value)}</text>',
                      f'<rect x="20" y="{y+10}" width="{width}" height="22" fill="#365da8"/>'])
    for y, text in [(290,'D1: one selected Dulwich task; 12 sessions per arm.'),
                    (315,'36 patches passed; six environment failures replaced in two rounds.'),
                    (340,'Preregistered comparison unidentified; total interval includes zero.'),
                    (365,'Uncached findings exploratory; no general efficiency or savings claim.')]:
        lines.append(f'<text x="20" y="{y}" font-size="16">{escape(text)}</text>')
    return '\n'.join(lines) + '\n</g>\n</svg>\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    data = json.loads((ROOT/'evidence/d1.json').read_text())
    assert data['blocks'] == 12 and data['selected_tasks'] == 1
    sessions = data['blocks'] * len(data['arms'])
    assert all(a['sessions'] == data['blocks'] for a in data['arms'])
    assert data['replaced_infrastructure_failures'] == 6 == sum(data['replacement_rounds'])
    assert data['replacement_rounds'] == [4, 2] and data['replacements_reclassified_from_agent_timeout'] == 2
    assert data['original_sessions_completed'] + data['replaced_infrastructure_failures'] == sessions
    assert data['patches_passed_frozen_checks'] == 36 == sessions
    assert data['preregistered_comparison_identified'] is False
    low, high = data['sql_minus_graphify_total_nominal_95_interval']
    assert low < 0 < high
    assert 'mean within-block paired difference' in data['interval_definition']
    evidence = (ROOT/'docs/evidence.md').read_text()
    assert f'{whole(Decimal(low))} to {whole(Decimal(high))}' in evidence, 'documented interval differs'
    readme = (ROOT/'README.md').read_text()
    pypi = (ROOT/'PYPI_README.md').read_text()
    interval = f'{whole(Decimal(low))} to +{whole(Decimal(high))}'
    assert interval in readme and interval in pypi, 'README interval differs'
    mean = {a['label']: {m: Decimal(a[m+'_sum'])/a['sessions'] for m in ('total_input','uncached_input')} for a in data['arms']}
    paired = (mean['sql_orient']['total_input'] - mean['Native Graphify']['total_input'])
    assert abs(paired - (Decimal(low) + Decimal(high))/2) < 1, 'interval is not centred on the mean paired difference'
    pct = lambda a, b, m: f'{(1 - mean[a][m]/mean[b][m]) * 100:.1f}%'
    claims = [f'mean paired difference of {whole(paired)}', pct('sql_orient','Native Graphify','total_input')+' lower',
              pct('sql_orient','Source-only','total_input')+' lower', pct('sql_orient','Native Graphify','uncached_input')+' below',
              pct('sql_orient','Source-only','uncached_input')+' below']
    assert all(c in readme for c in claims), 'README derived numbers differ from aggregate calculation'
    for metric, filename, title in [('total_input','total-input','Total input'), ('uncached_input','uncached-input','Uncached input')]:
        row = '| '+title+' | '+' | '.join(whole(Decimal(a[metric+'_sum'])/a['sessions']) for a in data['arms'])+' |'
        assert row in readme and row in pypi, 'README table differs from aggregate calculation'
        path = ROOT/'docs/figures'/f'{filename}.svg'
        expected = render(data, metric).encode()
        if args.check:
            assert path.read_bytes() == expected, f'figure differs: {filename}'
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(expected)
    print('Public means, both README tables, derived percentages, paired interval and two SVGs checked.' if args.check else 'Rendered two public SVGs.')


if __name__ == '__main__':
    main()
