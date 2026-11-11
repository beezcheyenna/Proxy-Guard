#!/usr/bin/env python3
"""Strict UTF-8 validation of native ucode log cursors in an isolated guest."""
from pathlib import Path
import argparse,json,subprocess,tempfile
assert Path('/etc/pgvm-fixture').is_file()
parser=argparse.ArgumentParser()
parser.add_argument('--module',required=True)
parser.add_argument('--expect-invalid',action='store_true')
args=parser.parse_args()
with tempfile.TemporaryDirectory(prefix='pg-log-encoding-')as directory:
 root=Path(directory)
 (root/'passwall-log.uc').write_bytes(Path(args.module).read_bytes())
 program=r"""
import {poll} from './passwall-log.uc';
import {writefile,open,unlink} from 'fs';
let wall=time(),up=100,path=REPLACE_PATH;
function line(msg) {
 let d=localtime(wall);
 return sprintf('%04d-%02d-%02d %02d:%02d:%02d: %s\n',d.year,d.mon,d.mday,d.hour,d.min,d.sec,msg);
}
function emit(label,s) { printf('%J\n',{label,state:s}); }
let rows=[['en','x'],['zh','中'],['ja','あ'],['ru','Ж'],['fa','م']];
for(let row in rows) {
 let padding='';for(let i=0;i<100;i++)padding+=row[1];
 writefile(path,line('Clear NFTSet.')+padding+'\n');
 let s=poll(null,wall,up,'encoding-test',path,'passwall');
 assert(s.pending && s.trip==1,'fresh start must trigger');
 emit(row[0]+'-anchor',s);
 s=json(sprintf('%J',s));
 let done=line('运行完成！'),cut=length(done)-2;
 let f=open(path,'a');f.write(substr(done,0,cut));f.close();
 s=poll(s,wall,up+1,'encoding-test',path,'passwall');
 assert(s.pending,'split code point cannot confirm completion');
 emit(row[0]+'-partial',s);
 s=json(sprintf('%J',s));
 f=open(path,'a');f.write(substr(done,cut));f.close();
 s=poll(s,wall,up+2,'encoding-test',path,'passwall');
 assert(!s.pending && s.trip==1,'completion must survive a saved-cursor roundtrip');
 emit(row[0]+'-complete',s);
 // Existing installations may carry the old raw buffers until the next poll.
 if(s.buffer_encoding=='base64') {
  s.partial=b64dec(s.partial);s.anchor=b64dec(s.anchor);
 }
 s.buffer_encoding=null;
 s=poll(s,wall,up+3,'encoding-test',path,'passwall');
 assert(!s.pending && s.trip==1,'legacy cursor migration must not replay a cycle');
 emit(row[0]+'-legacy',s);
 s.partial=b64dec('/wD/');s.anchor=b64dec('5Lit5paH/w==');s.buffer_encoding=null;
 unlink(path);
 s=poll(s,wall,up+4,'encoding-test',path,'passwall');
 assert(!s.available,'missing log must remain unavailable');
 emit(row[0]+'-missing-log-binary',s);
}
writefile(path,line('Clear NFTSet.'));
let s=poll(null,wall,up,'encoding-test',path,'passwall');
s.partial='%%%';s.anchor='%%%';s.buffer_encoding='base64';
s=poll(s,wall,up+1,'encoding-test',path,'passwall');
assert(s.pending,'corrupt saved buffers cannot grant recovery');
emit('corrupt-saved-buffer',s);
unlink(path);
"""
 program=program.replace('REPLACE_PATH',json.dumps(str(root/'fixture.log')))
 script=root/'test.uc';script.write_text(program)
 result=subprocess.run(['ucode',str(script)],capture_output=True,timeout=80)
 assert result.returncode==0,result.stderr.decode(errors='replace')
 rows=result.stdout.splitlines();invalid=[];labels=[]
 for i,raw in enumerate(rows):
  try:
   d=json.loads(raw.decode('utf-8'));labels.append(d['label'])
  except (UnicodeDecodeError,json.JSONDecodeError)as error:
   invalid.append({'row':i,'error':str(error)})
 assert len(rows)==26,len(rows)
 if args.expect_invalid:assert invalid,'old module must reproduce invalid UTF-8'
 else:assert not invalid,invalid
 print(json.dumps({'ok':True,'observations':len(rows),'invalid':invalid,'valid_labels':labels,'expected_old_failure':args.expect_invalid},indent=2))
