"""Build the strict import schema from the explicit offline course contracts."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def obj(properties):
    return dict(type='object',properties=properties,required=list(properties),additionalProperties=False)
def arr(items,lo=0,hi=100):
    return dict(type='array',items=items,minItems=lo,maxItems=hi)
S=dict(type='string',minLength=1,maxLength=200000)
N=dict(type='number',minimum=0)
I=dict(type='integer',minimum=0)
def infer(value):
    if isinstance(value,bool): return dict(type='boolean')
    if isinstance(value,str): return S
    if isinstance(value,int): return I
    if isinstance(value,float): return N
    if isinstance(value,list): return arr(infer(value[0]) if value else S)
    return obj({k:infer(v) for k,v in value.items()})
lab=json.loads((ROOT/'content/labs/lab-softmax.json').read_text(encoding='utf-8'))
unit=json.loads((ROOT/'content/units/l0-softmax.json').read_text(encoding='utf-8'))
schema=obj({'unit':infer(unit),'lecture':S,'lab':infer(lab)})
schema['$schema']='https://json-schema.org/draft/2020-12/schema'
u=schema['properties']['unit']['properties'];u['concepts']=arr(S,1,6);u['week']=dict(type='integer',minimum=1,maximum=12)
l=schema['properties']['lab']['properties'];l['timebox_min']=dict(type='integer',minimum=120,maximum=240)
l['env']['properties']['vram_limit_mb']=dict(type='integer',minimum=1,maximum=8192)
scalar={'anyOf':[{'type':'number'},{'type':'array','items':{'$ref':'#/$defs/value'},'maxItems':200000}]}
schema['$defs']={'value':scalar}
dataset=obj({'entrypoint':dict(type='string',pattern='^[a-zA-Z_][a-zA-Z0-9_]*$'),'cases':arr(obj({'args':arr({'$ref':'#/$defs/value'},1,10),'expected':{'$ref':'#/$defs/value'}}),3,100),'benchmark_args':arr({'$ref':'#/$defs/value'},1,10),'baseline_source':S})
l['acceptance']['properties']['correctness']['properties']['dataset']={'oneOf':[S,dataset]}
l['acceptance']['properties']['memory']['properties']['limit_mb']=dict(type='integer',minimum=32,maximum=8192)
for k,count in [('stages',3),('hints',3),('symptoms',5)]:l[k].update(minItems=count,maxItems=count)
l['scaffold']['properties']['edge_cases'].update(minItems=3,maxItems=3)
(ROOT/'content/bundle.schema.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2),encoding='utf-8')
