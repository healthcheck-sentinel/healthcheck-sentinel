"""Signed, allowlisted Slack actions for a local Docker demo operator."""
import hashlib
import json
import math
import os
import re
import sqlite3
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from chatops.slack_client import SlackClient
SERVICES = ("payment-service", "order-service", "user-service")


def action_blocks(services):
    blocks = []
    for service in services:
        if service not in SERVICES:
            continue
        blocks.append({'type':'actions','elements':[
            {'type':'button','text':{'type':'plain_text','text':f'Logs: {service}'},
             'action_id':'sentinel_logs','value':service},
            {'type':'button','text':{'type':'plain_text','text':f'Restart: {service}'},
             'action_id':'sentinel_restart','value':service,'style':'danger',
             'confirm':{'title':{'type':'plain_text','text':'Restart this demo service?'},
                        'text':{'type':'plain_text','text':f'Only {service} will restart. Active requests may be interrupted.'},
                        'confirm':{'type':'plain_text','text':'Restart'},
                        'deny':{'type':'plain_text','text':'Cancel'}}}]})
    return blocks


def safe_response_url(value):
    if not isinstance(value,str):
        return False
    try:
        url = urlsplit(value)
        return (url.scheme == 'https' and url.hostname == 'hooks.slack.com'
                and url.port in (None,443) and not url.username and not url.password
                and not url.query and not url.fragment
                and url.path.startswith(('/actions/','/app-actions/')))
    except ValueError:
        return False


def redact_logs(text):
    for key,value in os.environ.items():
        if any(word in key.upper() for word in ('SECRET','TOKEN','PASSWORD','WEBHOOK','API_KEY')) and len(value)>3:
            text=text.replace(value,'[REDACTED]')
    text=re.sub(r'(?i)\b[a-z][a-z0-9+.-]*://[^\s]+', '[URL REDACTED]', text)
    text=re.sub(r'(?i)(password|token|secret|api[_-]?key)([\s:=]+)[^\s,;]+',r'\1\2[REDACTED]',text)
    text=re.sub(r'(?i)(authorization[\s:=]+)(?:bearer\s+|basic\s+)?[^\s,;]+',r'\1[REDACTED]',text)
    text=re.sub(r'xox[baprs]-[A-Za-z0-9-]+','[REDACTED]',text)
    text=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',text)
    return text[-2600:]


def execute_local(action, service):
    from scripts.local_action import command, require_local_engine
    require_local_engine()
    args=command(action,service,50)
    # Bound captured stdout as well as execution time.
    process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    timer=threading.Timer(40,process.kill)
    timer.start()
    try:
        output=process.stdout.read(65537)
        truncated=len(output)>65536
        if truncated:
            process.kill()
        code=process.wait(timeout=5)
        if action=='restart':
            return f'{service}: restart completed.' if code==0 else f'{service}: restart failed; check local Docker.'
        if code!=0 and not truncated:
            return f'{service}: logs unavailable; check local Docker.'
        return f'{service} recent logs'+(' (truncated)' if truncated else '')+':\n'+redact_logs(output.decode(errors='replace'))
    finally:
        timer.cancel()
        if process.poll() is None:
            process.kill()
        process.stdout.close()


class ActionGate:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.path=str(path)
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS actions (id TEXT PRIMARY KEY, service TEXT, action TEXT, created REAL)')

    def reserve(self,key,service,action):
        now=time.time()
        with sqlite3.connect(self.path,timeout=0.5) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM actions WHERE created < ?', (now-86400,))
            if db.execute('SELECT 1 FROM actions WHERE id=?',(key,)).fetchone():
                return False
            cooldown=60 if action=='restart' else 5
            if db.execute('SELECT 1 FROM actions WHERE service=? AND action=? AND created>?',
                          (service,action,now-cooldown)).fetchone():
                return False
            db.execute('INSERT INTO actions VALUES (?,?,?,?)',(key,service,action,now))
        return True


def create_app(signing_secret=None, team=None, users=None, channels=None,
               state_path='.sentinel-state/slack-actions.sqlite3', executor=execute_local, deliver=None):
    secret=signing_secret or os.getenv('SLACK_SIGNING_SECRET','')
    team=team or os.getenv('SLACK_ALLOWED_TEAM','')
    users=set(users if users is not None else filter(None,os.getenv('SLACK_ALLOWED_USERS','').split(',')))
    channels=set(channels if channels is not None else filter(None,os.getenv('SLACK_ALLOWED_CHANNELS','').split(',')))
    if not secret or not team or not users or not channels:
        raise ValueError('Slack signing secret and explicit team/user/channel allowlists are required')
    verifier=SlackClient(signing_secret=secret)
    gate=ActionGate(state_path)
    worker=ThreadPoolExecutor(max_workers=2,thread_name_prefix='slack-action')
    slots=threading.BoundedSemaphore(4)
    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            worker.shutdown(wait=True)
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)

    def post(url,payload):
        with httpx.Client(timeout=5,follow_redirects=False,trust_env=False) as client:
            client.post(url,json=payload).raise_for_status()

    def run(action,service,url):
        try:
            try:
                text=executor(action,service)
            except Exception:
                text=f'{service}: action failed safely; check local Docker.'
            payload={'response_type':'ephemeral','replace_original':False,
                     'blocks':[{'type':'section','text':{'type':'plain_text','text':str(text)[:2900]}}]}
            try:
                (deliver or post)(url,payload)
            except Exception:
                # Never log URLs, request bodies, signing values or private output.
                print('Slack action result delivery failed; action will not be retried.')
        finally:
            slots.release()

    @app.post('/slack/actions')
    async def actions(request: Request):
        body=b''
        async for chunk in request.stream():
            body+=chunk
            if len(body)>65536:
                return JSONResponse({'error':'request too large'},status_code=413)
        if not verifier.verify_request(body,request.headers.get('x-slack-request-timestamp',''),
                                       request.headers.get('x-slack-signature','')):
            return JSONResponse({'error':'unauthorized'},status_code=401)
        try:
            payload=json.loads(parse_qs(body.decode())['payload'][0])
            if (payload['type']!='block_actions' or payload['team']['id']!=team
                or payload['user']['id'] not in users or payload['channel']['id'] not in channels):
                return JSONResponse({'error':'forbidden'},status_code=403)
            entries=payload['actions']
            if not isinstance(entries,list) or len(entries)!=1:
                raise ValueError()
            item=entries[0]
            action={'sentinel_logs':'logs','sentinel_restart':'restart'}[item['action_id']]
            service=item['value']
            if service not in SERVICES or not safe_response_url(payload.get('response_url')):
                raise ValueError()
            stamp=str(item['action_ts'])
            if not math.isfinite(float(stamp)) or abs(time.time()-float(stamp))>300:
                raise ValueError()
            key=hashlib.sha256(json.dumps([team,payload['user']['id'],payload['channel']['id'],
                                          action,service,stamp]).encode()).hexdigest()
        except (KeyError,ValueError,TypeError,IndexError):
            return JSONResponse({'error':'invalid action'},status_code=400)
        if not slots.acquire(blocking=False):
            return JSONResponse({'error':'busy'},status_code=429)
        try:
            accepted=gate.reserve(key,service,action)
        except sqlite3.Error:
            slots.release()
            return JSONResponse({'error':'busy'},status_code=503)
        if not accepted:
            slots.release()
            return JSONResponse({'response_type':'ephemeral','text':'Already handled or rate limited.'})
        worker.submit(run,action,service,payload['response_url'])
        return JSONResponse({'response_type':'ephemeral','text':f'{service}: {action} accepted.'})

    return app


def main():
    from dotenv import load_dotenv
    import uvicorn
    load_dotenv()
    app=create_app()
    # Publish only this signed endpoint through an operator-managed HTTPS tunnel.
    uvicorn.run(app,host='127.0.0.1',port=9102,access_log=False,log_level='warning')

if __name__=='__main__':
    main()
