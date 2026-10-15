#!/usr/bin/env python3
"""Reproduce public aggregate calculations and deterministic SVGs; no experiments.

Standard library only. Reads the sanitized files in evidence/, regenerates the three
README figures and checks the numbers that README.md, PYPI_README.md and
docs/evidence.md state. --check compares figure bytes instead of writing them.
"""
import argparse
from decimal import Decimal, ROUND_HALF_UP
from html import escape
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARMS = [('Source-only', '#64748b'), ('Native Graphify', '#b45309'), ('sql_orient', '#1d4ed8')]
INK, MUTED = '#0f172a', '#475569'
WORDS = {3: 'three'}


def whole(value):
    return f'{Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP):,}'


def load(name):
    return json.loads((ROOT/'evidence'/name).read_text())


def txt(x, y, value, size=24, fill=INK, bold=False, anchor='start'):
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}"'
            f' font-weight="{700 if bold else 400}" text-anchor="{anchor}">{escape(str(value))}</text>')


def svg(title, desc, body, height):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="600" height="' + str(height) + '" '
            f'viewBox="0 0 600 {height}" role="img" aria-labelledby="title desc">\n'
            f'<title id="title">{escape(title)}</title>\n<desc id="desc">{escape(desc)}</desc>\n'
            '<g font-family="DejaVu Sans, Arial, sans-serif">\n'
            f'<rect width="600" height="{height}" fill="#fff"/>\n' + '\n'.join(body) + '\n</g>\n</svg>\n')


def bars(values, sessions, title, maximum, ticks, footer):
    body = [txt(28, 42, title, 28, bold=True),
            txt(28, 77, f'Mean tokens/session · {sessions} sessions per arm', 22, fill=MUTED)]
    for i, ((name, color), value) in enumerate(zip(ARMS, values)):
        y = 135 + i * 100
        width = (value * 544 / maximum).quantize(Decimal('.0001'), rounding=ROUND_HALF_UP)
        body += [txt(28, y, name, bold=name == 'sql_orient'), txt(572, y, whole(value), bold=True, anchor='end'),
                 f'<rect x="28" y="{y+14}" width="544" height="30" fill="#f1f5f9"/>',
                 f'<rect x="28" y="{y+14}" width="{width}" height="30" fill="{color}"/>']
    body.append('<path d="M28 403 H572" stroke="#94a3b8"/>')
    for value, label in ticks:
        x = (Decimal(28) + Decimal(544) * value / maximum).quantize(Decimal('.0001'))
        anchor = 'start' if value == 0 else 'end' if value == maximum else 'middle'
        body += [f'<path d="M{x} 403 v6" stroke="#94a3b8"/>', txt(x, 436, label, 21, fill=MUTED, anchor=anchor)]
    body.append(txt(28, 475, 'D1 · one selected Dulwich task · amended set', 22, fill=MUTED))
    body += [txt(28, 511 + i * 29, line, 22, bold=i == 0) for i, line in enumerate(footer)]
    desc = '; '.join(f'{name}: {whole(v)}' for (name, _), v in zip(ARMS, values))
    desc += f' mean tokens per session. {sessions} sessions per arm. ' + ' '.join(footer)
    return svg(title, desc, body, 610), desc


def delivery(sealed, ledger):
    native, refine = sealed['native_graphify']['first_operation'], sealed['native_graphify']['refinement']
    sql = sealed['sql_orient']
    body = [txt(28, 42, 'Same facts, different delivery', 28, bold=True),
            txt(28, 78, 'Preserved D1 sealed pair · before replication', 22, fill=MUTED),
            txt(28, 112, 'Different queries; not a matched test.', 22, bold=True)]
    for y, (title, color), lines in [
            (137, ARMS[1], ['query_graph → neighborhood → node list',
                            f'{native["nodes_displayed"]} nodes · {native["relationship_lines"]} relationships · truncated',
                            f'Then get_neighbors → {refine["relationship_lines"]} relationships',
                            f'{refine["text_bytes"]:,} bytes of text · no truncation']),
            (337, ARMS[2], ['SQL → edge JOIN + predicate → chosen rows',
                            f'{sql["rows_delivered"]} relationship rows · {sql["json_bytes"]:,} bytes of JSON',
                            'Source + target labels, relation, source file',
                            'SQL LIMIT bounds rows; no IDs delivered'])]:
        body.append(f'<rect x="28" y="{y}" width="544" height="184" rx="8" fill="#f8fafc" stroke="{color}" stroke-width="2"/>')
        body.append(txt(44, y + 34, title, 25, fill=color, bold=True))
        body += [txt(44, y + 68 + i * 31, line, 21) for i, line in enumerate(lines)]
    body += [txt(28, 565, 'Replication: carried index output (approx.)', 22, bold=True),
             txt(28, 601, f'Native Graphify: {ledger["Native Graphify"]:,} tokens/session', 24, fill=ARMS[1][1]),
             txt(28, 635, f'sql_orient: {ledger["sql_orient"]:,} tokens/session', 24, fill=ARMS[2][1], bold=True),
             txt(28, 676, 'Post hoc attribution; not a full causal explanation.', 22, fill=MUTED)]
    desc = (f'query_graph displayed {native["nodes_displayed"]} nodes, no relationships, truncated. '
            f'Native refinement delivered {refine["relationship_lines"]} relationships in {refine["text_bytes"]:,} text bytes. '
            f'SQL delivered {sql["rows_delivered"]} rows in {sql["json_bytes"]:,} JSON bytes; labels and file provenance, no IDs. '
            'Separate sealed pair; different questions, not an equal-question comparison. '
            f'Replication estimated carried index output: Graphify {ledger["Native Graphify"]:,}, '
            f'sql_orient {ledger["sql_orient"]:,} tokens/session. Approximate post-hoc attribution.')
    return svg('Same facts, different delivery', desc, body, 702), desc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    data, extra, sealed, optional = (load(n) for n in ('d1.json', 'd1-exploratory.json', 'd1-sealed-pair.json', 'optional-use.json'))
    historical = load('historical.json')
    assert data['blocks'] == 12 and data['selected_tasks'] == 1
    n = data['blocks']
    sessions = n * len(data['arms'])
    assert [a['label'] for a in data['arms']] == [a['label'] for a in extra['arms']] == [name for name, _ in ARMS]
    assert all(a['sessions'] == n for a in data['arms'] + extra['arms'])
    assert data['replaced_infrastructure_failures'] == 6 == sum(data['replacement_rounds'])
    assert data['replacement_rounds'] == [4, 2] and data['replacements_reclassified_from_agent_timeout'] == 2
    assert data['original_sessions_completed'] + data['replaced_infrastructure_failures'] == sessions
    assert data['patches_passed_frozen_checks'] == 36 == sessions
    assert data['preregistered_comparison_identified'] is False
    low, high = data['sql_minus_graphify_total_nominal_95_interval']
    assert low < 0 < high
    assert 'mean within-block paired difference' in data['interval_definition']
    assert sealed['questions_identical'] is False and sealed['sql_orient']['endpoint_ids_delivered'] is False
    assert all(c['sessions_with_any_index_operation'] == 0 for c in optional['cohorts'])

    mean = {a['label']: {m: Decimal(a[m + '_sum']) / a['sessions'] for m in ('total_input', 'uncached_input')} for a in data['arms']}
    paired = mean['sql_orient']['total_input'] - mean['Native Graphify']['total_input']
    assert abs(paired - (Decimal(low) + Decimal(high)) / 2) < 1, 'interval is not centred on the mean paired difference'
    change = lambda a, b, m: f'{abs(mean[a][m] / mean[b][m] - 1) * 100:.1f}%'
    by = {a['label']: a for a in extra['arms']}
    blocks = extra['paired_blocks_lower']
    ledger = {k: v['approximate_carried_output_tokens_per_session'] for k, v in by.items() if 'approximate_carried_output_tokens_per_session' in v}
    calls = [f'{Decimal(by[name]["model_calls_sum"]) / n:.1f}' for name, _ in ARMS]
    shares = ' | '.join(f'{Decimal(str(by[name]["mean_session_cache_hit_share"])) * 100:.1f}%' for name, _ in ARMS)
    k = lambda v: f'{(Decimal(abs(v)) / 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP)}k'

    readme, pypi = (ROOT/'README.md').read_text(), (ROOT/'PYPI_README.md').read_text()
    evidence = (ROOT/'docs/evidence.md').read_text()
    exact = f'{whole(low)} to +{whole(high)}'
    assert f'{whole(low)} to {whole(high)}' in evidence and exact in pypi, 'documented interval differs'
    for metric, title in (('total_input', 'Total input'), ('uncached_input', 'Uncached input')):
        assert '| ' + title + ' | ' + ' | '.join(whole(mean[name][metric]) for name, _ in ARMS) + ' |' in pypi, 'PyPI table differs'
    claims = {
        'total vs Graphify': f"**{change('sql_orient', 'Native Graphify', 'total_input')} less**",
        'total vs source-only': f"**{change('sql_orient', 'Source-only', 'total_input')} less**",
        'patches': f'All {sessions} patches passed the frozen checks: {n}/{n} per arm.',
        'interval': f'{k(low)} fewer to {k(high)} more tokens per session',
        'interval definition': 'nominal 95% t-interval with 11 degrees of freedom for the mean within-block paired difference',
        'uncached Graphify vs source-only': f"**{change('Native Graphify', 'Source-only', 'uncached_input')} more uncached input**",
        'uncached vs Graphify': f"**{change('sql_orient', 'Native Graphify', 'uncached_input')} less than Graphify**",
        'uncached blocks vs Graphify': f"**{blocks['uncached_input_sql_orient_below_native_graphify']}/{n} blocks**",
        'uncached blocks vs source-only': f"lower in only {blocks['uncached_input_sql_orient_below_source_only']}/{n} blocks",
        'cache shares': f'| Mean session cache-hit share | {shares} |',
        'Graphify lower total blocks': f"Graphify used fewer total input tokens in {WORDS[n - blocks['total_input_sql_orient_below_native_graphify']]} D1 blocks",
        'carried index': f"**{ledger['Native Graphify']['index']:,} tokens/session for Graphify** and **{ledger['sql_orient']['index']:,} for sql_orient**",
        'carried test': f"**{k(ledger['Native Graphify']['test'])} versus {k(ledger['sql_orient']['test'])}**",
        'model calls': f'Mean model calls were {calls[0]} for source-only, {calls[1]} for Graphify and {calls[2]} for sql_orient.',
        'optional use': ' and '.join(f"**{c['sessions_with_any_index_operation']}/{c['indexed_sessions']}**" for c in optional['cohorts']),
        'sealed limit': f"`LIMIT {sealed['sql_orient']['sql_limit']}`",
        'historical HTTPX counterexample': 'Historical HTTPX work used more input with SQL',
        'historical compatibility counterexample': 'both historical tenacity patches broke supported compatibility despite passing a narrow bug oracle',
        'native recovery and SQL cap qualification': 'Native refinement sometimes recovered useful navigation where broad SQL lost selected rows at a cap',
        'analyst SQL qualification': "Analyst-written queries demonstrate addressability, not an unfamiliar agent's formulation effort or avoided source reads",
    }
    prose = ' '.join(readme.split())  # Claims may wrap across lines and list indentation.
    missing = [name for name, text in claims.items() if text not in prose]
    assert not missing, f'README claims differ from public evidence: {missing}'
    assert extra['sql_orient_sessions'] == {'sessions': n, 'one_cli_sql_query': n, 'single_hop_edge_join': n,
                                            'keyword_predicate': n, 'rows_delivered': n}
    assert extra['wall_time_paired_intervals_include_zero'] is True
    intervals = extra['session_elapsed_relative_change_nominal_95_intervals']
    assert len(intervals) == 3 and all(x['interval'][0] < 0 < x['interval'][1] for x in intervals)
    httpx = historical['v4']['httpx']['arms']
    assert [a['label'] for a in httpx] == [name for name, _ in ARMS[1:]]
    assert all(a['sessions'] == 1 for a in httpx)
    assert httpx[1]['cumulative_input_tokens'] > httpx[0]['cumulative_input_tokens']
    assert all(f"{a['cumulative_input_tokens']:,}" in evidence for a in httpx)
    assert all(a['patches'] == 1 and a['narrow_bug_oracle_checks'] == a['narrow_bug_oracle_passed'] == 1
               and a['diagnostic_compatibility_checks'] == 2 and a['diagnostic_compatibility_passed'] == 0
               for a in historical['v4']['tenacity']['arms'])
    dispatch = historical['v7_fixed_check']
    assert dispatch['native']['reformulated_relevant_navigation_candidates'] > dispatch['native']['initial_relevant_navigation_candidates']
    assert dispatch['native']['module_mediated_navigation_recorded'] is True
    assert dispatch['broad_structural_sql']['seed_node_rows_emitted'] == 0
    assert dispatch['broad_structural_sql']['more_rows'] is True and dispatch['broad_structural_sql']['limit_reason'] == 'max_bytes'
    assert f"{dispatch['broad_structural_sql']['edge_rows_emitted']} edge rows" in evidence
    assert f"{dispatch['broad_structural_sql']['max_bytes']:,}-byte cap" in evidence
    cattrs, native_recovery = historical['b1']['cattrs'], historical['b1']['httpx']
    assert cattrs['native_initial_selected'] == cattrs['focused_sql_required_relationships_emitted'] == cattrs['required_stored_navigation_relationships']
    assert cattrs['native_preserved_responses_emitted'] == 0
    assert cattrs['broad_sql_required_relationships_emitted'] < cattrs['required_stored_navigation_relationships']
    assert native_recovery['native_initial_emitted'] == 0
    assert native_recovery['native_after_refinement_emitted'] == native_recovery['required_stored_navigation_relationships']
    assert native_recovery['scoped_sql_contains_all_required'] is True

    tick = lambda m, labels: [(Decimal(v), lab) for v, lab in zip((0, m // 2, m), labels)]
    figures = {}
    figures['total-input'], total_desc = bars(
        [mean[name]['total_input'] for name, _ in ARMS], n, 'Less total input on this task', Decimal(2000000),
        tick(2000000, ('0', '1 million', '2 million')),
        [f'All {sessions} patches passed · {n}/{n} per arm',
         f'{data["replaced_infrastructure_failures"]} failures replaced in two rounds; descriptive.',
         f'Graphify comparison: {k(low)} fewer to {k(high)} more.',
         'Includes no difference; broader gains unproven.'])
    figures['uncached-input'], uncached_desc = bars(
        [mean[name]['uncached_input'] for name, _ in ARMS], n, 'Less uncached input than Graphify', Decimal(120000),
        tick(120000, ('0', '60,000', '120,000')),
        ['Exploratory: chosen after seeing results',
         f"sql_orient lower than Graphify in {blocks['uncached_input_sql_orient_below_native_graphify']}/{n} blocks.",
         'Uncached = total input minus cached input.',
         'Not a preregistered confirmation or money saved.'])
    figures['retrieval-delivery'], delivery_desc = delivery(sealed, {k2: v['index'] for k2, v in ledger.items()})
    for name, desc in (('total-input', total_desc), ('uncached-input', uncached_desc), ('retrieval-delivery', delivery_desc)):
        assert f'![{desc}](docs/figures/{name}.svg)' in readme, f'README figure or alt text differs: {name}'
        path = ROOT/'docs/figures'/f'{name}.svg'
        expected = figures[name].encode()
        if args.check:
            assert path.read_bytes() == expected, f'figure differs: {name}'
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(expected)
    print(f'Public evidence: {len(claims)} README claims, PyPI table, paired interval and three SVGs checked.'
          if args.check else 'Rendered three public SVGs.')


if __name__ == '__main__':
    main()
