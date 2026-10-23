"""Raw written-form/encoding ledger audit, independent of the source reader.

The frozen production autoencoder is rerun to establish correspondence, not
independent Cantonese pronunciation truth. No dictionary rows are written.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'cccedict:headwords:autoencoded'
REQUIRED_EXCLUSIONS = {'unihan:kCantonese','cccanto:dictionary','cccanto:cedict-readings',
                       'wordnet:cantown',SOURCE}
RANGES = ((0x3400,0x4DBF),(0x4E00,0x9FFF),(0xF900,0xFAFF),(0x20000,0x2A6DF),
          (0x2A700,0x2B73F),(0x2B740,0x2B81F),(0x2B820,0x2CEAF),(0x2CEB0,0x2EBEF),
          (0x2EBF0,0x2EE5F),(0x2F800,0x2FA1F),(0x30000,0x3134F),
          (0x31350,0x323AF),(0x323B0,0x3347F))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _han(text):
    return bool(text) and all(ord(c)==0x3007 or any(a<=ord(c)<=b for a,b in RANGES) for c in text)


def audit_cccedict_headwords(connection: sqlite3.Connection, lock_audit: dict | None,
                            verified_ids: dict[str,set[int]], *, project_root: Path = ROOT) -> dict:
    """Credit only valid generated-source IDs, after every source check passes."""
    counts, errors, credited = Counter(), [], set()
    try:
        _require(lock_audit is not None and lock_audit.get('verified') is True,'CC-CEDICT source lock is not verified')
        directory = Path(lock_audit['source_directory']).resolve()
        lock_path = Path(lock_audit['path']).resolve()
        _require(sha(lock_path)==lock_audit['sha256'],'CC-CEDICT source lock changed')
        lock = json.loads(lock_path.read_text('utf-8'))
        _require(lock.get('source_id')=='cccedict:headwords' and lock.get('license')=='CC-BY-SA-4.0','Unexpected headword source identity/license')
        guarded = {lock_path:lock_audit['sha256']}
        source = None
        records = lock_audit['files']
        _require(len({row['name'] for row in records})==len(records),'Duplicate headword source file')
        for item in records:
            path = (directory/item['name']).resolve()
            _require(path.is_relative_to(directory) and item.get('matches_lock') is True,'Unverified headword source path')
            _require(path.stat().st_size==item['size_bytes'] and sha(path)==item['sha256'],'Headword source file changed')
            guarded[path]=item['sha256']
            if item['name']=='cedict_ts.u8':
                _require(path.stat().st_size<=32*1024*1024,'Headword source exceeds bound')
                source=path.read_bytes()
        _require(source is not None,'Missing locked headword source')
        source_sha=hashlib.sha256(source).hexdigest()
        metadata={key:json.loads(value) for key,value in connection.execute('SELECT key,value FROM metadata')}
        selected=metadata['source_metadata']['supplements']['cccedict_headwords']
        _require(selected['source_lock_sha256']==lock_audit['sha256'],'Selected headword source lock differs')
        _require(all(selected.get(key)==value for key,value in lock.items()),'Embedded headword source lock differs')
        _require(selected.get('authored_cantonese_readings') is False,'Headword source is incorrectly labeled authored Cantonese')
        for role in ('parser','encoder'):
            path=(Path(project_root)/selected[role+'_file']).resolve()
            _require(path.is_relative_to(Path(project_root).resolve()) and sha(path)==selected[role+'_sha256'],'Headword '+role+' revision changed')
            guarded[path]=selected[role+'_sha256']
        policy=metadata['headword_encoding']
        boundary=policy['pre_headword_max_entry_id']
        _require(type(boundary) is int and boundary>0,'Invalid pre-headword entry boundary')
        old_rows=connection.execute('SELECT COUNT(*),COUNT(DISTINCT text),MAX(id) FROM entries WHERE id<=?',(boundary,)).fetchone()
        _require(old_rows==(policy['baseline_entry_count'],policy['baseline_distinct_texts'],boundary),'Pre-headword entry boundary/counts differ')
        _require(not connection.execute('SELECT 1 FROM entries WHERE id<=? AND source=? LIMIT 1',(boundary,SOURCE)).fetchone(),'Generated source predates its boundary')
        excluded=set(policy['excluded_encoder_sources'])
        _require(REQUIRED_EXCLUSIONS<=excluded,'Headword translator exclusions are incomplete')
        translator=list(connection.execute("SELECT id,text,reading,weight,source,origin FROM entries WHERE id<=? AND origin IN ('explicit','supplement') AND syllable_count=1 ORDER BY text,reading",(boundary,)))
        translator=[row for row in translator if row[4] not in excluded]
        signature=hashlib.sha256()
        for row in translator:
            signature.update((json.dumps(list(row),ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8'))
        _require(len(translator)==policy['translation_rows'] and signature.hexdigest()==policy['translator_input_sha256'],'Fixed character translator cohort differs')
        from cantonese_ime.autoencode import ScriptAutoencoder
        encoder=ScriptAutoencoder([(row[1],row[2],row[3]) for row in translator])
        _require(encoder.metadata()==policy['encoder'],'Recorded encoder algorithm/bounds differ')
        old_texts={row[0] for row in connection.execute('SELECT DISTINCT text FROM entries WHERE id<=?',(boundary,))}
        encodings={row[0]:row[1:] for row in connection.execute('SELECT text,status,codes_json,path_count,work_count,reason,source_refs_json FROM cccedict_headword_encodings')}
        forms={(row[0],row[1]):row[2:] for row in connection.execute('SELECT * FROM cccedict_headword_forms')}
        _require(len(encodings)==connection.execute('SELECT COUNT(*) FROM cccedict_headword_encodings').fetchone()[0]
                 and len(forms)==connection.execute('SELECT COUNT(*) FROM cccedict_headword_forms').fetchone()[0],
                 'Duplicate source or encoding ledger keys')
        refs=defaultdict(list)
        header={}
        statuses=Counter()
        source_lines=source.decode('utf-8').splitlines()
        _require(len(source_lines)<=600000,'Too many source lines')
        declaration='\n'.join(line for line in source_lines if line.startswith('#'))
        _require('Published by MDBG' in declaration and 'Creative Commons Attribution-ShareAlike 4.0 International License' in declaration and 'https://creativecommons.org/licenses/by-sa/4.0/' in declaration,'Missing original source declaration')
        for number,raw in enumerate(source_lines,1):
            _require(len(raw.encode('utf-8'))<=65536,'Oversized source line')
            if raw.startswith('#! '):
                key,separator,value=raw[3:].partition('=')
                _require(separator and key not in header,'Invalid/duplicate source release header')
                header[key]=value
            if not raw or raw.startswith('#'):
                continue
            match=re.fullmatch(r'(\S+)[ \t]+(\S+)[ \t]+\[[^\[\]\r\n]+\][ \t]+/.*\/',raw)
            _require(match is not None,'Malformed written-headword row')
            counts['input_rows']+=1
            line_sha=hashlib.sha256(raw.encode('utf-8')).hexdigest()
            for script,text in zip(('traditional','simplified'),match.groups()):
                actual=forms.pop((number,script),None)
                if not _han(text):
                    status,reason='source_quarantined','non_han_headword'
                elif text in old_texts:
                    status,reason='already_present',None
                else:
                    _require(text in encodings,'Missing absent-text encoding ledger')
                    status,reason=encodings[text][0],encodings[text][4]
                    refs[text].append({'line':number,'script':script,'raw_line_sha256':line_sha})
                _require(actual==(text,line_sha,'cccedict:headwords','cedict_ts.u8',source_sha,status,reason),'Source occurrence ledger differs')
                counts['form_candidates']+=1
                statuses[status]+=1
        release=lock['source_release_header']
        _require(counts['input_rows']>0 and counts['input_rows']==release['entries']==int(header['entries']),'Source row count differs')
        _require(all(header.get(key)==release[key] for key in ('date','format','version','charset')),'Source release header differs')
        _require(not forms and set(refs)==set(encodings),'Unexpected form or encoding ledger rows')
        expected=set()
        encoding_counts=Counter()
        for text,actual in sorted(encodings.items()):
            result=encoder.encode(text)
            _require((result.status,list(result.codes),result.path_count,result.work_count,result.reason)==(actual[0],json.loads(actual[1]),actual[2],actual[3],actual[4]),'Recomputed encoding differs')
            _require(json.loads(actual[5])==refs[text],'Encoding source references differ')
            encoding_counts[result.status]+=1
            if result.status in ('encoded_unique','encoded_ambiguous'):
                expected.update((text,reading) for reading in result.codes)
            else:
                _require(result.status in ('unencodable','truncated','too_long'),'Unrecognized encoding status')
        additions=list(connection.execute('SELECT id,text,reading,base_reading,compact,syllable_count,weight,source,origin FROM entries WHERE source=? ORDER BY id',(SOURCE,)))
        _require(len(additions)==len(expected) and {(row[1],row[2]) for row in additions}==expected,'Generated-source rows differ from complete encoding ledger')
        for index,row in enumerate(additions,boundary+1):
            entry_id,text,reading,base,compact,syllables,weight,source_id,origin=row
            canonical=' '.join(token[:-1] for token in reading.split())
            _require(entry_id==index and base==canonical and compact==canonical.replace(' ','') and syllables==len(reading.split()) and weight==0 and origin=='generated' and text not in old_texts,'Invalid generated row provenance/ID/reading/weight')
            credited.add(entry_id)
        _require(dict(sorted(statuses.items()))==policy['form_status_counts'] and dict(sorted(encoding_counts.items()))==policy['encoding_counts'],'Encoding/form aggregate counts differ')
        _require(policy['source_form_ledger_rows']==counts['form_candidates'] and policy['encoding_ledger_rows']==policy['missing_texts']==len(encodings) and policy['new_generated_pairs']==len(expected) and policy['complete_new_texts']==len({text for text,_ in expected}),'Recorded generated-source counts differ')
        _require(all(sha(path)==expected_hash for path,expected_hash in guarded.items()),'Headword audit source/implementation changed')
        counts.update(source_files_audited=1,encoding_texts_recomputed=len(encodings),generated_pairs=len(expected),generated_rows_credited=len(credited),source_occurrences_verified=counts['form_candidates'])
    except (OSError,ValueError,TypeError,KeyError,sqlite3.Error) as error:
        errors.append(str(error))
    complete=not errors and counts['source_files_audited']==1
    if complete:
        verified_ids.setdefault('generated',set()).update(credited)
    return {'mechanical_complete':complete,'counts':dict(counts),'errors':errors,
            'notice':'Independent raw headword and occurrence audit, rerunning the frozen production encoder to check correspondence. Only generated-source IDs are credited after every check passes. Not independent pronunciation, held-out quality or vocabulary-completeness approval.'}
