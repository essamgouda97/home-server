#!/usr/bin/env python3
"""Generate the Workspace dashboard for the existing Grafana datasource."""
import json
from pathlib import Path
panels=[]
def panel(title,expr,unit='short',kind='timeseries',legend='{{name}}',description=''):
    i=len(panels)
    p={'id':i+1,'title':title,'description':description,'type':kind,'gridPos':{'x':(i%2)*12,'y':(i//2)*8,'w':12,'h':8},
       'datasource':{'type':'prometheus','uid':'home-prometheus'},
       'targets':[{'refId':'A','expr':expr,'legendFormat':legend,'instant':kind=='stat'}],
       'fieldConfig':{'defaults':{'unit':unit,'color':{'mode':'palette-classic'}},'overrides':[]},
       'options':{'legend':{'displayMode':'table','placement':'bottom','calcs':['lastNotNull']},'tooltip':{'mode':'multi'}}}
    if kind=='stat':p['options']['reduceOptions']={'calcs':['lastNotNull'],'fields':'','values':False}
    panels.append(p)
panel('Workspace availability','home_service_up{service="workspace"}',kind='stat',legend='HTTPS')
panel('Application telemetry','home_workspace_metrics_up',kind='stat',legend='Collector')
panel('Container CPU','home_container_cpu_percent{name=~"shared-workspace|workspace-.*"}','percent')
panel('Container memory','home_container_memory_bytes{name=~"shared-workspace|workspace-.*"}','bytes')
panel('Host CPU','100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))','percent',legend='Host CPU')
panel('Host memory used','node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes','bytes',legend='Host memory')
panel('Host load','node_load1',legend='1 minute load')
panel('Container health','home_container_healthy{name=~"shared-workspace|workspace-.*"}',kind='stat')
panel('Stored documents','home_workspace_documents',kind='stat',legend='Documents')
panel('Structured records','home_workspace_records',kind='stat',legend='Active records')
panel('Document processing','home_workspace_document_tasks',legend='{{status}}',description='Paperless task history retained by the document engine; counts can decrease when tasks expire.')
panel('Script runs','home_workspace_script_jobs',legend='{{status}}')
panel('API requests','rate(home_workspace_requests_total[5m])','reqps',legend='Requests')
panel('API errors and access denials','rate(home_workspace_errors_total[5m])','reqps',legend='HTTP errors',description='Includes invalid input and authentication failures; not all errors indicate an outage.')
panel('Mean API response time','rate(home_workspace_request_seconds_total[5m]) / clamp_min(rate(home_workspace_requests_total[5m]), 0.001)','s',legend='Mean duration')
panel('Uploads','rate(home_workspace_uploaded_bytes_total[5m])','Bps',legend='Upload bytes')
panel('Workspace storage','home_workspace_storage_bytes','bytes',legend='{{kind}}')
panel('SSD available','home_filesystem_available_bytes{mountpoint="/srv/mergerfs/ssd"}','bytes',legend='SSD free')
panel('Active agent keys','home_workspace_active_keys',kind='stat',legend='Unexpired, unrevoked keys')
panel('API authentication denials','increase(home_workspace_auth_denials_total[1h])',kind='stat',legend='Last hour')
panel('Container restarts','home_container_restart_count{name=~"shared-workspace|workspace-.*"}')
panel('Telemetry age','time() - home_workspace_collected_seconds','s',legend='Seconds since refresh')
panel('Backup age','time() - home_workspace_backup_last_success_seconds','s',legend='Seconds since verified snapshot')
panel('Sandbox execution time','home_workspace_script_seconds_total','s',legend='Cumulative execution time')
d={'uid':'shared-workspace','title':'Shared Workspace','tags':['home-server','workspace'],'timezone':'browser','schemaVersion':41,'version':1,'refresh':'30s','time':{'from':'now-6h','to':'now'},'panels':panels,'links':[{'title':'Open Workspace','url':'https://workspace.egouda.xyz','targetBlank':True}],'annotations':{'list':[]}}
p=Path(__file__).resolve().parents[1]/'config/monitoring/grafana/dashboards/shared-workspace.json'
p.write_text(json.dumps(d,indent=2)+'\n')
print('Generated Workspace Grafana dashboard with',len(panels),'panels.')
