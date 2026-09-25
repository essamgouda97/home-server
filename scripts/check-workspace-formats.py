#!/usr/bin/env python3
"""Exercise synthetic PDF and email ingestion through the final HTTPS route."""
import importlib.util
from pathlib import Path
import time
import uuid
from email.message import EmailMessage
from auth_session import AuthSession, prefer_ipv4

spec=importlib.util.spec_from_file_location('check_workspace',Path(__file__).with_name('check-workspace.py'))
check=importlib.util.module_from_spec(spec);spec.loader.exec_module(check)
prefer_ipv4()
marker='Workspace format verification '+uuid.uuid4().hex[:10]
stream=('BT /F1 18 Tf 60 700 Td ('+marker+') Tj ET').encode()
objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream']
pdf=bytearray(b'%PDF-1.4\n');offsets=[0]
for i,obj in enumerate(objects,1):
    offsets.append(len(pdf));pdf.extend(str(i).encode()+b' 0 obj\n'+obj+b'\nendobj\n')
xref=len(pdf);pdf.extend(b'xref\n0 6\n0000000000 65535 f \n')
for offset in offsets[1:]:pdf.extend(('%010d 00000 n \n'%offset).encode())
pdf.extend(('trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n'%xref).encode())
email=EmailMessage();email['From']='synthetic@example.invalid';email['To']='verification@example.invalid';email['Subject']=marker;email.set_content(marker+'\nThis is a synthetic email, not a real message.')
with AuthSession(portal='https://signin.egouda.xyz',target_url=check.BASE) as session:
    for name,mime,content in [('installation-format.pdf','application/pdf',bytes(pdf)),('installation-format.eml','message/rfc822',email.as_bytes())]:
        boundary='format-'+uuid.uuid4().hex
        payload=('--'+boundary+'\r\nContent-Disposition: form-data; name="file"; filename="'+name+'"\r\nContent-Type: '+mime+'\r\n\r\n').encode()+content+('\r\n--'+boundary+'--\r\n').encode()
        upload=check.data(session.opener,'/ui-api/documents/upload',status=202,raw=payload,content_type='multipart/form-data; boundary='+boundary)
        for _ in range(90):
            value=check.data(session.opener,'/ui-api/tasks/'+upload['task_id'])
            tasks=value if isinstance(value,list) else value['results']
            if tasks and tasks[0]['status']=='FAILURE':raise AssertionError(name+' processing failed')
            if tasks and tasks[0]['status']=='SUCCESS':break
            time.sleep(2)
        else:raise AssertionError(name+' processing timed out')
        document=check.data(session.opener,'/ui-api/documents/'+str(tasks[0]['related_document']))
        assert marker in document['content'],name+' extracted content missing'
        with check.response(session.opener,'/ui-api/documents/'+str(document['id'])+'/file') as response:assert response.read()==content
        print('PASS',name,'local parsing and byte-identical original')
