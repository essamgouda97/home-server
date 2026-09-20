#!/usr/bin/env python3
"""Search-only local LLM helper. Reads catalog/indexer metadata, never media files."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services/media-matcher'))
from matcher import classify, normalize, safe_title, title_evidence


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tmdb-id',type=int,required=True)
    parser.add_argument('--indexer',default='ArabP2P')
    args=parser.parse_args()
    if args.tmdb_id<=0:parser.error('TMDB ID must be positive')
    os.umask(0o077)
    def get(app,path):
        port,config,version={'radarr':(7878,'radarr/config','v3'),'prowlarr':(9696,'prowlarr/data','v1')}[app]
        key=ET.parse('/mnt/server/'+config+'/config.xml').getroot().findtext('ApiKey')
        req=urllib.request.Request(f'http://127.0.0.1:{port}/api/{version}'+path,headers={'X-Api-Key':key})
        with urllib.request.urlopen(req,timeout=45) as r:return json.load(r)
    matches=get('radarr','/movie/lookup?term='+urllib.parse.quote('tmdb:'+str(args.tmdb_id)))
    raw=next(x for x in matches if x.get('tmdbId')==args.tmdb_id)
    movie={k:raw.get(k) for k in ['title','originalTitle','year','imdbId','tmdbId']}
    movie['aliases']=[x['title'] for x in raw.get('alternateTitles',[]) if x.get('title')]
    del raw,matches
    indexer=next(x for x in get('prowlarr','/indexer') if x['name']==args.indexer and x.get('enable'))
    ident=indexer['id'];del indexer
    queries=list(dict.fromkeys(x for x in [movie['originalTitle'],movie['title']] if x))[:2]
    releases={}
    for query in queries:
        results=get('prowlarr','/search?'+urllib.parse.urlencode({'query':query,'indexerIds':ident,'type':'search'}))
        for r in results:
            # Copy only the minimum fields; discard URLs, passkeys and account data.
            title=safe_title(r.get('title',''))
            releases[normalize(title)]={'title':title,'seeders':r.get('seeders',0)}
        del results
    candidates=sorted(releases.values(),key=lambda x:title_evidence(movie,x),reverse=True)[:24]
    start=time.monotonic()
    decisions=classify(movie,candidates)
    report={'tmdbId':args.tmdb_id,'mode':'search-only','model':'ODS local Qwen3.5 4B',
            'indexer':args.indexer,'results_seen':len(releases),'candidates_evaluated':len(candidates),
            'inference_seconds':round(time.monotonic()-start,2),
            'candidates':[{'id':i,**c} for i,c in enumerate(candidates)],'decisions':decisions}
    folder=Path.home()/'.local/state/home-server-maintenance/media-matcher'
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=folder/(str(args.tmdb_id)+'.json')
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');path.chmod(0o600)
    print(json.dumps({k:v for k,v in report.items() if k not in ['candidates','decisions']},ensure_ascii=False))
    print('Candidate matches for review:',sum(x['recommendation']=='review_match' for x in decisions))
    print('Private metadata-only report:',path)
    print('No media reads, downloads, Seerr requests or Radarr mutations performed.')


if __name__=='__main__':
    try:main()
    except Exception as error:
        print('Search helper failed safely: '+type(error).__name__,file=sys.stderr)
        sys.exit(1)
