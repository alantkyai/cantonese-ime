"""Verify retained, literal numeric-Yale spelling evidence for build tooling."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re

COMMIT = 'd0ceb32c2da07d156db99e50b192aaf45236ca95'
SOURCE_ID = 'yale_kfcd_numeric'
ORIGINAL_HASHES = {
    'pingyambiu': 'bfb4a10ff62238a27d087a9a82e64de9b3cf9d3fc2326097ef083a476103e3aa',
    'README.md': '72667a8ac72516528ffb527796646aef0382c3c6e8f0ba05140fdfcb8a5e1977',
    'LICENSE': '243ce65e3a5a24669b08b5b6d25e82e961dfc747f841f04f199126a218968100',
}
_TOKEN = re.compile(r'([a-z]+)([1-9])\Z', re.ASCII)
_SHA = re.compile(r'[a-f0-9]{64}\Z', re.ASCII)


def _digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _inside(root: Path, name: object) -> Path:
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name
            or PurePosixPath(name).is_absolute() or PureWindowsPath(name).is_absolute()
            or any(part in ('', '.', '..') or part.endswith((' ', '.')) for part in name.split('/'))):
        raise ValueError('Unsafe Yale source path')
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('Missing or escaping Yale source file')
    return path


def verify_kfcd_yale_source(root: Path, lock_path: Path, *, alternates: dict,
                           extension_bases: tuple[str, ...] = ('hm', 'hng')) -> dict:
    """Bind six source alternatives and two literal nasals to the reviewed pin.

    All 11-column rows and their explicit terminal tone correspondence validate.
    This does not turn the table's all-possible tones into word attestations or
    parse diacritic/low-register-h input. It never changes runtime mappings.
    """
    root, lock_path = Path(root).resolve(), Path(lock_path).resolve()
    if not lock_path.is_relative_to(root):
        raise ValueError('Yale source lock must be retained within the project')
    lock_hash = _digest(lock_path)
    lock = json.loads(lock_path.read_text('utf-8'))
    policy = {'numeric_yale_column': 0, 'jyutping_column': 6, 'column_count': 11,
              'terminal_numeric_tones_only': True, 'changed_tone_mapping': {'7': '1', '8': '3', '9': '6'}}
    normalized = {base: list(forms) for base, forms in alternates.items()}
    if (lock.get('schema_version') != 1 or lock.get('source_id') != SOURCE_ID
            or lock.get('commit') != COMMIT or lock.get('license') != 'CC-BY-3.0'
            or lock.get('field_policy') != policy or lock.get('alternate_spellings') != normalized
            or lock.get('literal_extension_bases') != list(extension_bases)):
        raise ValueError('Yale source lock differs from the reviewed spelling policy')
    directory_name = lock.get('local_directory')
    if not isinstance(directory_name, str):
        raise ValueError('Missing Yale source directory')
    directory = (root / directory_name).resolve()
    if not directory.is_relative_to(root):
        raise ValueError('Yale source directory escapes the project')
    records = lock.get('files')
    if not isinstance(records, list) or len(records) != 5:
        raise ValueError('Missing Yale original source and full attribution/license records')
    payloads, hashes, names = {}, {}, set()
    for item in records:
        if not isinstance(item, dict):
            raise ValueError('Invalid Yale source record')
        name = item.get('name')
        path = _inside(directory, name)
        if name.casefold() in names:
            raise ValueError('Duplicate Yale source file')
        names.add(name.casefold())
        size, expected = item.get('size_bytes'), item.get('sha256')
        if (type(size) is not int or not 0 < size < 1_000_000
                or not isinstance(expected, str) or not _SHA.fullmatch(expected)
                or path.stat().st_size != size or _digest(path) != expected):
            raise ValueError('Yale retained source differs from its lock')
        if name in ORIGINAL_HASHES and expected != ORIGINAL_HASHES[name]:
            raise ValueError('Yale original source differs from the reviewed upstream commit')
        payloads[name] = path.read_text('utf-8')
        hashes[(path.relative_to(root)).as_posix()] = expected
    if set(payloads) != {*ORIGINAL_HASHES, 'LICENSE-CC-BY-3.0.txt', 'ATTRIBUTION.md'}:
        raise ValueError('Missing Yale source or original notices')
    if ('creativecommons.org/licenses/by/3.0/' not in payloads['LICENSE']
            or '© 2015' not in payloads['README.md']
            or 'Attribution 3.0 Unported' not in payloads['LICENSE-CC-BY-3.0.txt']
            or '8. Miscellaneous' not in payloads['LICENSE-CC-BY-3.0.txt']
            or len(payloads['LICENSE-CC-BY-3.0.txt']) < 10_000
            or COMMIT not in payloads['ATTRIBUTION.md']):
        raise ValueError('Incomplete Yale source attribution or full license terms')
    by_base, all_pairs = defaultdict(set), []
    tone_map = {'1':'1','2':'2','3':'3','4':'4','5':'5','6':'6','7':'1','8':'3','9':'6'}
    for line, raw in enumerate(payloads['pingyambiu'].splitlines(), 1):
        fields = raw.split('\t')
        if len(fields) != 11 or any(not field for field in fields):
            raise ValueError('Malformed numeric-Yale conversion row')
        yale, jyutping = _TOKEN.fullmatch(fields[0]), _TOKEN.fullmatch(fields[6])
        if not yale or not jyutping or jyutping[2] not in '123456' or tone_map[yale[2]] != jyutping[2]:
            raise ValueError('Numeric Yale/Jyutping tone correspondence is invalid')
        by_base[jyutping[1]].add(yale[1])
        all_pairs.append({'line':line,'yale_numeric':fields[0],'jyutping':fields[6]})
    if len(all_pairs) != 3972 or len(by_base) != 741:
        raise ValueError('Reviewed Yale table row/base accounting differs')
    selected = []
    for base, forms in normalized.items():
        if not forms or len(set(forms)) != len(forms) or not set(forms) <= by_base.get(base, set()):
            raise ValueError('A runtime Yale alternative lacks literal source evidence')
        selected.extend(row for row in all_pairs if row['jyutping'][:-1] == base and row['yale_numeric'][:-1] in forms)
    for base in extension_bases:
        if base not in by_base.get(base, set()):
            raise ValueError('A Yale nasal extension lacks literal source evidence')
        selected.extend(row for row in all_pairs if row['jyutping'][:-1] == row['yale_numeric'][:-1] == base)
    if _digest(lock_path) != lock_hash or any(_digest(root/name) != expected for name,expected in hashes.items()):
        raise ValueError('Yale source changed during verification')
    return {'source_id':SOURCE_ID,'license':'CC-BY-3.0','commit':COMMIT,
            'source_lock_file':lock_path.relative_to(root).as_posix(),'source_lock_sha256':lock_hash,
            'files_sha256':hashes,'table_rows':len(all_pairs),'table_bases':len(by_base),
            'alternate_spellings':normalized,'literal_extension_bases':list(extension_bases),
            'selected_literal_rows':selected,'independent_linguistic_approval':False,
            'scope':'Published numeric-Yale spelling evidence; no word frequency, independent pronunciation approval or all-tones word attestation.'}
