"""Read-only local investment MCP server, JSON-RPC over newline-delimited stdio."""
import json
import sys
from intelligence import tools

def handle(req):
    ident=req.get('id');method=req.get('method');p=req.get('params',{})
    if ident is None:return None
    result=None
    if method=='initialize':result={'protocolVersion':'2025-06-18','capabilities':{'tools':{'listChanged':False}},'serverInfo':{'name':'wealth-investment-intelligence','version':'1.0.0'}}
    elif method=='ping':result={}
    elif method=='tools/list':result={'tools':[{**d,'annotations':{'readOnlyHint':True,'destructiveHint':False,'openWorldHint':True}} for d in tools.definitions()]}
    elif method=='tools/call':
        value=tools.safe_call(p.get('name'),p.get('arguments') or {})
        result={'content':[{'type':'text','text':json.dumps(value,default=str,allow_nan=False)}],'isError':bool(value.get('error')) if isinstance(value,dict) else False}
    else:return {'jsonrpc':'2.0','id':ident,'error':{'code':-32601,'message':'Method not found'}}
    return {'jsonrpc':'2.0','id':ident,'result':result}

def main():
    for line in sys.stdin:
        try:
            request=json.loads(line);response=handle(request)
        except Exception:
            response={'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':'Invalid JSON-RPC request'}}
        if response is not None:print(json.dumps(response,default=str),flush=True)

if __name__=='__main__':main()
