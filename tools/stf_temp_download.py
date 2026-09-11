#!/usr/bin/env python3
import argparse,csv,json,re,sys,time,urllib3
from pathlib import Path
from urllib.parse import urljoin,urlparse,parse_qs
import requests
from bs4 import BeautifulSoup
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36'
KNOWN={('PET','15556'):'7514886',('INQ','5026'):'7473347',('RCL','88121'):'7450195',('PET','15198'):'7473336',('PET','15562'):'7515623',('PET','15978'):'7576893',('PET','16662'):'7681133'}
def S():
 s=requests.Session();s.verify=False;s.headers.update({'User-Agent':UA,'Accept-Language':'pt-BR,pt;q=0.9'});return s
def G(s,u,stream=False,timeout=None):
 last=None
 for i in range(3):
  try:
   r=s.get(u,timeout=timeout or (10,120),allow_redirects=True,stream=stream)
   if r.status_code in (429,500,502,503,504):last=RuntimeError(f'HTTP {r.status_code}');time.sleep(2+i*2);continue
   r.raise_for_status();return r
  except Exception as e:last=e;time.sleep(2+i*2)
 raise last
def incident(s,c,n):
 if (c,n) in KNOWN:return KNOWN[(c,n)]
 u=f'https://portal.stf.jus.br/processos/listarProcessos.asp?classe={c}&numeroProcesso={n}'
 r=G(s,u,timeout=(8,20));ids=list(dict.fromkeys(re.findall(r'detalhe\.asp\?incidente=(\d+)',r.text)))
 if len(ids)==1:return ids[0]
 soup=BeautifulSoup(r.text,'html.parser')
 for a in soup.find_all('a',href=True):
  m=re.search(r'detalhe\.asp\?incidente=(\d+)',a['href']);lab=' '.join(a.stripped_strings).upper()
  if m and n in lab and c in lab:return m.group(1)
 raise RuntimeError(f'incident not resolved candidates={ids[:20]}')
def did(u):
 q=parse_qs(urlparse(u).query)
 for k in ('docID','docId','docid','id'):
  if q.get(k):return q[k][0]
 m=re.search(r'(?:docID|docId|docid|id)=(\d+)',u);return m.group(1) if m else ''
def clean(x):
 x=re.sub(r'[^\w.()\-]+','_',x or 'documento',flags=re.UNICODE);return re.sub(r'_+','_',x).strip('_.')[:80] or 'documento'
def savepdf(r,p):
 first=b''
 with p.open('wb') as f:
  for ch in r.iter_content(262144):
   if not ch:continue
   if len(first)<8:first+=ch[:8-len(first)]
   f.write(ch)
 if not first.startswith(b'%PDF'):p.unlink(missing_ok=True);return False
 return True
def one(s,u,p):
 r=G(s,u,stream=True);ct=(r.headers.get('content-type') or '').lower()
 if 'pdf' in ct:return savepdf(r,p),u,'direct'
 body=b''.join(r.iter_content(1048576))
 if body.startswith(b'%PDF'):p.write_bytes(body);return True,u,'direct-body'
 soup=BeautifulSoup(body.decode(r.encoding or 'utf-8',errors='ignore'),'html.parser');cand=[]
 for a in soup.find_all('a',href=True):
  h=urljoin(r.url,a['href'])
  if 'downloadPeca.asp' in h or h.lower().endswith('.pdf'):cand.append(h)
 d=did(u)
 if d:cand.append(f'https://portal.stf.jus.br/processos/downloadPeca.asp?id={d}&ext=.pdf')
 for h in dict.fromkeys(cand):
  try:
   rr=G(s,h,stream=True)
   if savepdf(rr,p):return True,h,'fallback'
  except Exception:pass
 return False,u,'not-pdf'
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--classe',required=True);ap.add_argument('--numero',required=True);a=ap.parse_args();c=a.classe.upper();n=str(a.numero);slug=f'{c}_{n}';out=Path('stf_download')/slug;out.mkdir(parents=True,exist_ok=True);s=S();rows=[]
 try:inc=incident(s,c,n)
 except Exception as e:(out/'ERROR.txt').write_text(f'incident error: {e}\n');print(e);return 0
 viewer='https://redir.stf.jus.br/estfvisualizadorpub/jsp/consultarprocessoeletronico/ConsultarProcessoEletronico.jsf?seqobjetoincidente='+inc
 try:vr=G(s,viewer,timeout=(10,90));soup=BeautifulSoup(vr.text,'html.parser');aa=soup.select("a[target='imgDocumento'][href]")
 except Exception as e:(out/'ERROR.txt').write_text(f'viewer error: {e}\n{viewer}\n');print(e);return 0
 docs=[];seen=set()
 for ael in aa:
  u=urljoin(vr.url,ael['href'])
  if u in seen:continue
  seen.add(u);docs.append((u,' '.join(ael.stripped_strings).strip(),(ael.get('title') or '').strip()))
 print(f'{slug} incident={inc} links={len(docs)}',flush=True)
 for i,(u,desc,title) in enumerate(docs,1):
  d=did(u);name=f'{i:04d}-{clean(desc or title)}'+(f'-docID_{d}' if d else '')+'.pdf';p=out/name;row={'index':i,'doc_id':d,'descricao':desc,'titulo':title,'source_url':u,'saved_as':name,'status':'','resolved_url':'','mode':''}
  try:ok,res,mode=one(s,u,p);row.update(status='OK' if ok else 'FAIL_NOT_PDF',resolved_url=res,mode=mode)
  except Exception as e:row['status']=f'ERROR:{type(e).__name__}:{e}'
  rows.append(row);print(f'[{i}/{len(docs)}] {row["status"]}',flush=True);time.sleep(.08)
 fields=['index','doc_id','descricao','titulo','source_url','saved_as','status','resolved_url','mode']
 with (out/'manifest.csv').open('w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 meta={'classe':c,'numero':n,'incident':inc,'viewer':viewer,'links':len(docs),'downloaded':sum(x['status']=='OK' for x in rows),'failed':sum(x['status']!='OK' for x in rows)};(out/'metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2));print(json.dumps(meta),flush=True);return 0
if __name__=='__main__':sys.exit(main())