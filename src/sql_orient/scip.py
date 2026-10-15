"""SCIP input handling: read .scip via the `scip` CLI or accept `scip print --json` output.

No binary parsing here: protobuf decoding is delegated to the standard SCIP
CLI. Descriptor parsing below implements the documented SCIP symbol grammar
(package/version prefix, '/'-separated owners, '#'/`().` member separators,
terminal suffixes) far enough to extract declaration (owner, name) pairs.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile

SUFFIX_RE = re.compile(r'^(.*?)(#|\(\).|\(\)|:|\.|/)$')


def decode_range(occurrence: dict, field: str, *, context: str) -> tuple[int, int, int, int] | None:
    """Decode a half-open SCIP range into zero-based endpoints, without conversion.

    Accept deprecated arrays, flat snake-case typed fields and the Go CLI's
    encoding/json oneof wrappers. Unknown typed shapes reject; raw input is
    never rewritten. Missing enclosing ranges are optional, occurrences are not.
    """
    if field == 'range':
        single, multi, wrapper = 'single_line_range', 'multi_line_range', 'TypedRange'
        variants = ('SingleLineRange', 'MultiLineRange')
        unsupported = ('singleLineRange', 'multiLineRange', 'typed_range', 'typedRange')
    elif field == 'enclosing_range':
        single, multi, wrapper = ('single_line_enclosing_range', 'multi_line_enclosing_range',
                                  'TypedEnclosingRange')
        variants = ('SingleLineEnclosingRange', 'MultiLineEnclosingRange')
        unsupported = ('enclosingRange', 'singleLineEnclosingRange', 'multiLineEnclosingRange',
                       'typed_enclosing_range', 'typedEnclosingRange')
    else:
        raise ValueError(f'unsupported range field: {field}')

    def fail(message):
        raise RuntimeError(f'{context} {field}: {message}')

    if not isinstance(occurrence, dict):
        fail('occurrence must be a JSON object')
    for key in unsupported:
        if key in occurrence:
            fail(f'unsupported JSON field {key!r}; use scip print --json format')

    typed = [(key, occurrence[key], key == multi) for key in (single, multi) if key in occurrence]
    wrapped = occurrence.get(wrapper)
    if wrapped is not None:  # Go encoding/json emits null for an unset oneof.
        if not isinstance(wrapped, dict) or len(wrapped) != 1:
            fail(f'{wrapper} must contain exactly one typed alternative')
        key = next(iter(wrapped))
        if key not in variants:
            fail(f'unsupported {wrapper} alternative {key!r}')
        typed.append((wrapper + '.' + key, wrapped[key], key == variants[1]))
    if len(typed) > 1:
        fail('multiple typed alternatives for oneof')

    def endpoints(values):
        if any(type(n) is not int or not 0 <= n <= 2147483647 for n in values):
            fail('coordinates must be nonnegative int32 integers (not booleans)')
        start_line, start_col, end_line, end_col = values
        if (end_line, end_col) < (start_line, start_col):
            fail('end precedes start')
        return start_line, start_col, end_line, end_col

    legacy = occurrence.get(field)
    normalized_legacy = None
    if legacy is not None:
        if not isinstance(legacy, list) or len(legacy) not in (0, 3, 4):
            fail('legacy array must have exactly three or four coordinates')
        if legacy:
            normalized_legacy = endpoints(
                (legacy[0], legacy[1], legacy[0], legacy[2]) if len(legacy) == 3 else legacy)

    if typed:
        key, value, multiline = typed[0]
        keys = ('start_line', 'start_character', 'end_line', 'end_character') if multiline else (
            'line', 'start_character', 'end_character')
        if not isinstance(value, dict) or any(k not in keys for k in value):
            fail(f'{key} must be an object with supported snake-case coordinate fields')
        values = tuple(value.get(k, 0) for k in keys)  # Protobuf omitted scalars default to zero.
        normalized_typed = endpoints(values if multiline else (
            values[0], values[1], values[0], values[2]))
        if normalized_legacy is not None and normalized_typed != normalized_legacy:
            fail('typed and legacy ranges conflict')
        return normalized_typed
    if normalized_legacy is None and field == 'range':
        fail('missing occurrence range or supported typed alternative')
    return normalized_legacy


# Independent wire example from scip.proto: Index.documents (2), Document
# relative_path (1), occurrences (2), position_encoding (6); Occurrence typed
# alternatives (8/9) and enclosing alternatives (10/11). No protobuf dependency.
_DECODER_PROBE = bytes.fromhex(
    '12300a0870726f62652e7079120e4206080710021805520408071809'
    '12124a0808071002180920045a060806180a20033002')


def _check_decoder(exe: str) -> None:
    """Refuse binary decoding that could silently discard typed coordinates."""
    try:
        with tempfile.TemporaryDirectory(prefix='sql-orient-scip-decoder-') as tmp:
            path = tmp + '/probe.scip'
            with open(path, 'wb') as fh:
                fh.write(_DECODER_PROBE)
            proc = subprocess.run([exe, 'print', '--json', path], capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError('decoder probe failed')
        docs = json.loads(proc.stdout)['documents']
        if (not isinstance(docs, list) or len(docs) != 1 or not isinstance(docs[0], dict)
                or type(docs[0].get('position_encoding')) is not int
                or docs[0]['position_encoding'] != 2):
            raise RuntimeError('document encoding lost')
        occurrences = docs[0]['occurrences']
        expected = [((7, 2, 7, 5), (7, 0, 7, 9)), ((7, 2, 9, 4), (6, 0, 10, 3))]
        if not isinstance(occurrences, list) or len(occurrences) != len(expected):
            raise RuntimeError('typed occurrences lost')
        for occ, (rng, enc) in zip(occurrences, expected):
            if (decode_range(occ, 'range', context='decoder probe') != rng or
                    decode_range(occ, 'enclosing_range', context='decoder probe') != enc):
                raise RuntimeError('typed coordinates lost')
    except (RuntimeError, ValueError, KeyError, TypeError, OSError) as exc:
        raise RuntimeError(
            'binary SCIP input requires a decoder preserving typed ranges and document '
            'position_encoding (verified with scip v0.9.0); installed CLI failed the '
            'capability check. Use a compatible CLI or a verified JSON export.') from exc


def _validate_index(index: dict) -> None:
    """Validate shapes consumed by the importer; leave producer extras untouched."""
    def obj(value, context):
        if not isinstance(value, dict):
            raise ValueError(f'{context}: expected a JSON object')

    def objects(value, context):
        if not isinstance(value, list):
            raise ValueError(f'{context}: expected an array')
        for number, item in enumerate(value, 1):
            obj(item, f'{context}[{number}]')
        return value

    obj(index, 'index')
    metadata = index.get('metadata', {})
    obj(metadata, 'metadata')
    obj(metadata.get('tool_info', {}), 'metadata.tool_info')
    paths = set()
    for number, doc in enumerate(objects(index.get('documents', []), 'documents'), 1):
        context = f'documents[{number}]'
        path = doc.get('relative_path')
        if not isinstance(path, str) or not path:
            raise ValueError(f'{context}.relative_path: expected a nonempty string')
        if path in paths:
            raise ValueError(f'{context}.relative_path: duplicate document {path!r}')
        paths.add(path)
        context = f'SCIP document {path!r}'
        encoding = doc.get('position_encoding')
        if 'positionEncoding' in doc:
            raise ValueError(f'{context} position_encoding: unsupported JSON field '
                             'positionEncoding; use scip print --json format')
        if encoding is not None and (type(encoding) is not int or
                                     not -2147483648 <= encoding <= 2147483647):
            raise ValueError(f'{context} position_encoding: expected an int32 enum value or null')
        for kind in ('occurrences', 'symbols'):
            for number, item in enumerate(objects(doc.get(kind, []), f'{context}.{kind}'), 1):
                if 'symbol' in item and not isinstance(item['symbol'], str):
                    raise ValueError(f'{context}.{kind}[{number}].symbol: expected a string')
                if kind == 'occurrences':
                    occurrence_context = f'{context} occurrence {number}'
                    rng = decode_range(item, 'range', context=occurrence_context)
                    enc = decode_range(item, 'enclosing_range', context=occurrence_context)
                    if enc is not None and not (enc[:2] <= rng[:2] and rng[2:] <= enc[2:]):
                        raise ValueError(f'{occurrence_context} enclosing_range: does not contain range')
                    roles = item.get('symbol_roles')
                    if roles is not None and (type(roles) is not int or
                                              not -2147483648 <= roles <= 2147483647):
                        raise ValueError(f'{context}.occurrences[{number}].symbol_roles: '
                                         'expected an int32 integer')
                    if roles is not None and roles & 1 and not item.get('symbol'):
                        raise ValueError(f'{context}.occurrences[{number}].symbol: '
                                         'a definition needs a symbol')


def _read_json(text: str, path: str) -> dict:
    try:
        index = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"SCIP input {path!r}: invalid JSON at line {exc.lineno}, "
                           f"column {exc.colno}: {exc.msg}; supply a valid scip print --json export") from exc
    try:
        _validate_index(index)
    except (ValueError, RuntimeError) as exc:
        raise RuntimeError(f"SCIP input {path!r}: {exc}; supply a valid scip print --json export") from exc
    return index


def load_index(path: str) -> dict:
    """Load SCIP; expected input failures are RuntimeErrors with chained causes."""
    # Check the supplied file even when no external decoder is installed.
    try:
        with open(path, 'rb') as fh:
            if not fh.read(1):
                raise ValueError('file is empty')
    except (OSError, ValueError) as exc:
        reason = exc.strerror if isinstance(exc, OSError) else str(exc)
        raise RuntimeError(f"SCIP input {path!r}: {reason}; supply a readable, nonempty SCIP input") from exc
    if path.endswith('.json'):
        try:
            with open(path, encoding='utf-8') as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            reason = exc.strerror if isinstance(exc, OSError) else 'JSON input is not valid UTF-8'
            raise RuntimeError(f"SCIP input {path!r}: {reason}; supply a readable UTF-8 JSON export") from exc
        return _read_json(text, path)
    exe = shutil.which('scip')
    if exe is None:
        raise RuntimeError(
            f"SCIP input {path!r}: binary input requires the `scip` CLI on PATH "
            "(https://github.com/sourcegraph/scip/releases); alternatively supply "
            "a verified scip print --json export as --scip")
    try:
        _check_decoder(exe)
    except RuntimeError as exc:
        raise RuntimeError(f"SCIP input {path!r}: {exc}") from exc
    try:
        proc = subprocess.run([exe, 'print', '--json', path], capture_output=True, text=True)
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"SCIP input {path!r}: cannot read decoder output: {exc}; "
                           "check the decoder installation or supply a verified JSON export") from exc
    if proc.returncode != 0:
        # External output is untrusted; keep the CLI diagnostic concise and one-line.
        detail = ' '.join(proc.stderr.split())[:300] or f'exit status {proc.returncode}'
        raise RuntimeError(f"SCIP input {path!r}: scip print --json failed: {detail}; "
                           "check the binary index or supply a verified JSON export")
    return _read_json(proc.stdout, path)


def parse_definition_symbol(symbol: str) -> tuple[str, str, str] | None:
    """Split a global definition symbol into (owner, name, suffix).

    Returns None for local symbols, parameters, and unparseable shapes.
    """
    parts = symbol.split(' ', 4)
    desc = parts[4] if len(parts) > 4 else symbol
    if desc.startswith('local') or ').(' in desc or '/' not in desc:
        return None
    head, tail = desc.rsplit('/', 1)
    m = SUFFIX_RE.match(tail)
    if not m:
        return None
    core, suffix = m.group(1), m.group(2)
    if '#' in core:
        towner, name = core.rsplit('#', 1)
        owner = head + '/' + towner + '#'
    elif '().' in core:
        fowner, name = core.rsplit('().', 1)
        owner = head + '/' + fowner + '().'
    else:
        owner, name = head, core
    if not name:
        return None
    return owner.replace('`', ''), name, suffix


def package_versions(index: dict) -> list[str]:
    """Distinct `manager language package version` prefixes seen in the index."""
    seen: set[str] = set()
    for doc in index.get('documents', []):
        for occ in doc.get('occurrences', []):
            sym = occ.get('symbol', '')
            if sym.startswith('local'):
                continue
            seen.add(' '.join(sym.split(' ')[:4]))
        for info in doc.get('symbols', []):
            sym = info.get('symbol', '')
            if sym.startswith('local'):
                continue
            seen.add(' '.join(sym.split(' ')[:4]))
    return sorted(seen)
