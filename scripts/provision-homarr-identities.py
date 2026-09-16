#!/usr/bin/env python3
"""Maintain private, read-only personal home boards from explicit service grants."""
import datetime,json,sqlite3,uuid,subprocess
from pathlib import Path
from identity_policy import identities

def uid():return uuid.uuid4().hex[:24]
def main():
    result=subprocess.run(['docker','exec','home-authelia','authelia','storage','user','identifiers','generate','--config','/config/configuration.yml','--users',','.join(identities()),'--services','openid'],capture_output=True,text=True)
    assert result.returncode==0,'Cannot prepare stable OIDC subjects'
    with sqlite3.connect('file:/srv/mergerfs/ssd/authelia/db.sqlite3?mode=ro',uri=True) as authdb:
        subjects=dict(authdb.execute("SELECT username,identifier FROM user_opaque_identifier WHERE service='openid' AND sector_id=''"))
    catalog=json.loads((Path(__file__).resolve().parents[1]/'config/services.json').read_text())['services']
    backup=Path.home()/'.local/state/home-server-maintenance/sso';backup.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect('/mnt/server/homarr/appdata/db/db.sqlite') as db:
        with sqlite3.connect(backup/('homarr-identities-'+datetime.datetime.now().strftime('%Y%m%dT%H%M%S')+'.sqlite')) as saved:db.backup(saved)
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        owner=db.execute('SELECT id FROM user WHERE name=?',('egouda',)).fetchone()[0]
        for name,person in identities().items():
            if person['owner']:
                db.execute('UPDATE user SET email=? WHERE name=? AND email IS NULL',(name+'@home.egouda.xyz',name));continue
            found=db.execute('SELECT id,provider FROM user WHERE name=?',(name,)).fetchone()
            if found:
                user=found[0];assert found[1]=='oidc','Review existing account before linking'
            else:
                user=uid();db.execute('INSERT INTO user (id,name,email,provider) VALUES (?,?,?,?)',(user,name,name+'@home.egouda.xyz','oidc'))
            board_name='home-'+name
            found=db.execute('SELECT id FROM board WHERE name=?',(board_name,)).fetchone()
            if found:board=found[0]
            else:
                board=uid();db.execute('INSERT INTO board (id,name,is_public,creator_id,page_title) VALUES (?,?,0,?,?)',(board,board_name,owner,person['display_name']+' — Home'))
                db.execute('INSERT INTO section (id,board_id,kind) VALUES (?,?,?)',(uid(),board,'empty'))
                db.execute('INSERT INTO layout (id,name,board_id,column_count,breakpoint) VALUES (?,?,?,?,0)',(uid(),'Base',board,4))
            db.execute('INSERT OR IGNORE INTO boardUserPermission VALUES (?,?,?)',(board,user,'view'))
            db.execute('UPDATE user SET home_board_id=?,mobile_home_board_id=? WHERE id=?',(board,board,user))
            section=db.execute('SELECT id FROM section WHERE board_id=?',(board,)).fetchone()[0]
            layout=db.execute('SELECT id FROM layout WHERE board_id=?',(board,)).fetchone()[0]
            # Only this generated board is reconciled, never the owner's custom layout.
            db.execute('DELETE FROM item WHERE board_id=?',(board,))
            for index,service in enumerate(s for s in catalog if s['id'] in person['services'] and s['id']!='homarr'):
                app=db.execute('SELECT id FROM app WHERE rtrim(href,?)=?',('/',service['url'].rstrip('/'))).fetchone()
                assert app,'Run catalog reconciliation before household boards'
                item=uid();db.execute('INSERT INTO item (id,board_id,kind,options) VALUES (?,?,?,?)',(item,board,'app',json.dumps({'json':{'appId':app[0]}})))
                db.execute('INSERT INTO item_layout VALUES (?,?,?,?,?,?,?)',(item,section,layout,index%4,index//4,1,1))
            assert not db.execute('SELECT 1 FROM groupMember m JOIN groupPermission p ON p.group_id=m.group_id WHERE m.user_id=?',(user,)).fetchall(),'Household user has global permissions; review required'
        for name in identities():
            user=db.execute('SELECT id FROM user WHERE name=?',(name,)).fetchone()[0]
            existing=db.execute('SELECT user_id FROM account WHERE provider=? AND provider_account_id=?',('oidc',subjects[name])).fetchone()
            if existing:assert existing[0]==user,'OIDC subject collision; refusing reassignment'
            else:db.execute('INSERT INTO account (user_id,type,provider,provider_account_id) VALUES (?,?,?,?)',(user,'oidc','oidc',subjects[name]))
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    print('PASS private household dashboards provisioned; owner board and roles preserved')
if __name__=='__main__':main()
