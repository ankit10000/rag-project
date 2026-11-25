#!/usr/bin/env python3
"""Native Linux host/cgroup sampling; never reads application env or content."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import time


def numeric_fields(path):
    return {line.split()[0]:int(line.split()[1]) for line in path.read_text().splitlines()}


def snapshot(project):
    memory=numeric_fields(Path('/proc/meminfo'))
    cpu=[int(n) for n in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
    ids=subprocess.check_output(['docker','ps','-q','--filter',f'label=com.docker.compose.project={project}'],text=True).split()
    containers={}
    for identity in ids:
        try:
            raw=subprocess.check_output(['docker','inspect','--format','{{.Name}} {{.State.Pid}} {{.State.OOMKilled}}',identity],text=True,stderr=subprocess.PIPE).split()
        except subprocess.CalledProcessError:
            containers[identity]={'id':identity,'transition':True}
            continue
        name,pid,oom=raw
        try:
            group=next(line.split(':',2)[2] for line in Path(f'/proc/{pid}/cgroup').read_text().splitlines() if line.startswith('0::'))
            root=Path('/sys/fs/cgroup')/group.lstrip('/')
            current=int((root/'memory.current').read_text())
            stats=numeric_fields(root/'memory.stat')
            containers[name.lstrip('/')]={
                'id':identity,'memory_current_bytes':current,
                'memory_working_bytes':max(0,current-stats.get('inactive_file',0)),
                'memory_peak_bytes':int((root/'memory.peak').read_text()),
                'memory_events':numeric_fields(root/'memory.events'),
                'cpu':numeric_fields(root/'cpu.stat'),'oom_killed':oom=='true',
            }
        except (OSError,ValueError,StopIteration):
            containers[name.lstrip('/')]= {'id':identity,'transition':True}
    return {'elapsed':time.monotonic(),'utc':datetime.now(timezone.utc).isoformat(),
            'memory_total_bytes':memory['MemTotal:']*1024,
            'memory_available_bytes':memory['MemAvailable:']*1024,
            'cpu_ticks':cpu,'containers':containers}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',default='rag-demo')
    parser.add_argument('--seconds',type=int,default=360)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not 5<=args.seconds<=900:parser.error('duration must be 5–900 seconds')
    samples=[];previous=None;end=time.monotonic()+args.seconds
    while time.monotonic()<end:
        current=snapshot(args.project)
        if previous:
            wall=current['elapsed']-previous['elapsed']
            ticks=[b-a for a,b in zip(previous['cpu_ticks'],current['cpu_ticks'])]
            total=sum(ticks)
            current['host_cpu_percent']=round(100*(total-ticks[3]-ticks[4])/total,2) if total else 0
            current['host_steal_percent']=round(100*ticks[7]/total,2) if total else 0
            for name,item in current['containers'].items():
                old=previous['containers'].get(name,{})
                if item.get('id')==old.get('id') and 'cpu' in item and 'cpu' in old:
                    delta=item['cpu']['usage_usec']-old['cpu']['usage_usec']
                    item['cpu_percent_one_core']=round(max(0,delta)/wall/10000,2)
        samples.append(current);previous=current;time.sleep(1)
    summary={'status':'MEASURED','cpu_count':os.cpu_count(),'samples':len(samples),
             'minimum_host_available_bytes':min(x['memory_available_bytes'] for x in samples),
             'peak_host_cpu_percent':max(x.get('host_cpu_percent',0) for x in samples),
             'peak_host_steal_percent':max(x.get('host_steal_percent',0) for x in samples),
             'peak_container_working_bytes':max(sum(c.get('memory_working_bytes',0) for c in x['containers'].values()) for x in samples),
             'oom_observed':any(c.get('oom_killed') or c.get('memory_events',{}).get('oom_kill',0) for x in samples for c in x['containers'].values())}
    with args.output.open('x') as output:json.dump({'summary':summary,'samples':samples},output,indent=2)
    print(json.dumps(summary))


if __name__=='__main__':main()
