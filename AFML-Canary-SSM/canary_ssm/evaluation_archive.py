"""Storage-only compact delivery; numerical sources and raw results are unchanged.

Full scenario examples stay included. Large null public/truth buffers regenerate
from the frozen producer, with score, input, truth and command-log verification.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import zipfile
import numpy as np
from . import replay_evaluator as evaluator


def truth_fingerprint(directory,generator):
    base=Path(directory)/'evaluator'
    if generator=='world':
        h=hashlib.sha256()
        with gzip.open(base/'truth.json.gz','rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
        return h.hexdigest()
    h=hashlib.sha256()
    with np.load(base/'truth.npz',allow_pickle=False) as arrays:
        for key in sorted(arrays.files):
            a=np.asarray(arrays[key]);h.update((key+str(a.dtype)+str(a.shape)).encode());h.update(a.tobytes())
    return h.hexdigest()


def describe(directory,generator):
    directory=Path(directory);cache=json.loads((directory/'sample_rows.json').read_text())
    if evaluator.file_hash(directory/'scores.npz')!=cache['score_sha256']:raise ValueError('Null scores modified')
    if evaluator.file_hash(directory/'public/input.npz')!=cache['public_file_sha256']:raise ValueError('Null input modified')
    if evaluator.file_hash(directory/cache['truth_path'])!=cache['truth_file_sha256']:raise ValueError('Null truth buffer modified')
    value=dict(public_fingerprint=cache['rows'][0]['public_sha256'],truth_content_fingerprint=truth_fingerprint(directory,generator),producer_sha256=evaluator.file_hash(directory/'evaluator/producer.json'),storage='per-minute scores/masks, provenance, commands and semantic fingerprints retained; large public/truth arrays regenerate from frozen sources and seed',generator=generator)
    evaluator.write(directory/'regeneration.json',value);return value


def replay(directory,generator,endpoint,role,index,materialize=False):
    root=Path(directory);f=evaluator.checked_freeze(root);saved=root/generator/'inputs'/role/endpoint/str(index)
    cache=json.loads((saved/'sample_rows.json').read_text());expected=json.loads((saved/'regeneration.json').read_text())
    if evaluator.file_hash(saved/'scores.npz')!=cache['score_sha256']:raise ValueError('Archived scores modified')
    if evaluator.file_hash(saved/'evaluator/producer.json')!=expected['producer_sha256']:raise ValueError('Archived command/config provenance modified')
    with tempfile.TemporaryDirectory(prefix='verified-null-') as tmp:
        job=(generator,endpoint,role,index,f['offset'],tmp,f['models'][generator],f['settings'][generator]);rows=evaluator.null_job(job);new=Path(tmp)/'inputs'/role/endpoint/str(index)
        identical=(rows==cache['rows'] and rows[0]['public_sha256']==expected['public_fingerprint'] and truth_fingerprint(new,generator)==expected['truth_content_fingerprint'] and evaluator.file_hash(new/'evaluator/producer.json')==expected['producer_sha256'])
        if not identical:raise ValueError('Regenerated null differs from archived scores/input/truth/ordered commands')
        if materialize:
            (saved/'public').mkdir(exist_ok=True);shutil.copyfile(new/'public/input.npz',saved/'public/input.npz');shutil.copyfile(new/cache['truth_path'],saved/cache['truth_path'])
            # gzip wrapper timestamps are storage metadata, not truth content.
            # Refresh raw-byte cache checks only after every semantic check passes.
            evaluator.write(saved/'sample_rows.json',json.loads((new/'sample_rows.json').read_text()))
    return dict(generator=generator,endpoint=endpoint,role=role,index=index,identical=True,raw_buffers_materialized=materialize,verified='all scores/masks, public fingerprint, evaluator truth and ordered command/config provenance')


def package(project,output):
    root=Path(project);study=root/'examples/evaluator_v2';f=evaluator.checked_freeze(study)
    checks=json.loads((study/'checks.json').read_text())
    if checks['freeze_hash']!=f['freeze_hash']:raise ValueError('Study and development freeze differ')
    omitted=set();counts={};folders=0
    for generator in ('research','world'):
        for endpoint in ('latent_effect',) if generator=='research' else ('release_latency','infrastructure'):
            for role,count in [('threshold-calibration',f['B']),('null-validation',f['n_validation'])]:
                base=study/generator/'inputs'/role/endpoint
                for index in range(count):
                    directory=base/str(index);cache=json.loads((directory/'sample_rows.json').read_text());describe(directory,generator)
                    omitted.add(directory/'public/input.npz');omitted.add(directory/cache['truth_path']);folders+=1
                counts[generator+'/'+endpoint+'/'+role]=count
    manifest=dict(format='compact-null-input-delivery-v1',freeze_hash=f['freeze_hash'],null_rollouts=counts,folders=folders,large_buffers_omitted=len(omitted),raw_tables_and_all_scores_retained=True,full_scenario_public_and_truth_retained=True,archive_adapter_sha256=evaluator.file_hash(Path(__file__)),restore='python -m canary_ssm.evaluation_archive replay-null --study examples/evaluator_v2 --generator world --endpoint release_latency --role null-validation --index 0 --materialize')
    evaluator.write(study/'compact_delivery.json',manifest)
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as archive:
        for p in sorted(root.rglob('*')):
            if not p.is_file() or p in omitted:continue
            rel=p.relative_to(root)
            if any(x in rel.parts for x in ('__pycache__','.pytest_cache','.hypothesis','.git','backend_runtime')):continue
            archive.write(p,str(Path(root.name)/rel))
    return dict(path=str(output),bytes=output.stat().st_size,**manifest)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['pack','replay-null']);p.add_argument('--project',default='.');p.add_argument('--output',default='canary_ssm_evaluator.zip');p.add_argument('--study',default='examples/evaluator_v2');p.add_argument('--generator',choices=['research','world'],default='world');p.add_argument('--endpoint',default='release_latency');p.add_argument('--role',choices=['threshold-calibration','null-validation'],default='null-validation');p.add_argument('--index',type=int,default=0);p.add_argument('--materialize',action='store_true');a=p.parse_args()
    result=package(a.project,a.output) if a.command=='pack' else replay(a.study,a.generator,a.endpoint,a.role,a.index,a.materialize)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
