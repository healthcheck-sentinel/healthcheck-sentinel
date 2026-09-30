"""Paired idle/monitored process CPU measurement; always restores the agent."""
import argparse
import json
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
PORTS={'payment-service':8001,'order-service':8002,'user-service':8003}

def get(url):
    with urlopen(url,timeout=5) as response:return json.load(response)

def compose(action):
    subprocess.run(['docker','compose','-f',str(ROOT/'docker-compose.yml'),action,'monitoring-agent'],check=True,capture_output=True)

def sample():
    return {name:get(f'http://127.0.0.1:{port}/readyz')['resources'] for name,port in PORTS.items()}

def window(seconds):
    start=sample();time.sleep(seconds);end=sample()
    return {name:{'cpu_percent_one_core':max(0,(end[name]['process_cpu_seconds']-start[name]['process_cpu_seconds'])/(end[name]['monotonic_seconds']-start[name]['monotonic_seconds'])*100),
                  'wall_seconds':end[name]['monotonic_seconds']-start[name]['monotonic_seconds']} for name in PORTS}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=int,default=30)
    parser.add_argument('--output',default='docs/target-overhead.json')
    args=parser.parse_args()
    if not 10<=args.seconds<=300:parser.error('seconds must be 10..300')
    status=get('http://127.0.0.1:9101/status')
    if not all(s['state']=='HEALTHY' for s in status['services'].values()):
        raise RuntimeError('Run measurement only with all services healthy')
    try:
        compose('stop')
        print('Measuring target baseline with agent paused.',flush=True)
        baseline=window(args.seconds)
    finally:
        compose('start')
    time.sleep(8)
    agent_start=get('http://127.0.0.1:9101/status')
    print('Measuring targets with normal agent polling.',flush=True)
    monitored=window(args.seconds)
    agent_end=get('http://127.0.0.1:9101/status')
    report={'method':'Paired quiet-host windows; process CPU delta / monotonic wall time. Normal Docker healthchecks remain active in both windows. No application load generated.',
            'baseline':baseline,'monitored':monitored,
            'incremental_cpu_percent_one_core':{name:max(0,monitored[name]['cpu_percent_one_core']-baseline[name]['cpu_percent_one_core']) for name in PORTS},
            'agent_cpu_percent_one_core':(agent_end['process_cpu_seconds']-agent_start['process_cpu_seconds'])/(agent_end['process_wall_seconds']-agent_start['process_wall_seconds'])*100}
    report['all_targets_below_one_percent']=all(v<1 for v in report['incremental_cpu_percent_one_core'].values())
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
