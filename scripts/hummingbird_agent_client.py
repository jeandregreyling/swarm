#!/usr/bin/env python3
"""Use one agent's private login without exposing its credential to a model."""
import argparse
import json
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import Request, HTTPRedirectHandler, build_opener

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.agent_identity import credentials


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise HTTPError(req.full_url,code,'Agent credential requests cannot redirect',headers,fp)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent',required=True)
    parser.add_argument('command',choices=['whoami','memory','tools','audit','call','remember'])
    parser.add_argument('--json-file',type=Path,help='JSON tool request or memory fields')
    args = parser.parse_args()
    credential = credentials(args.agent)
    route = {'whoami':'whoami','memory':'memory','tools':'tools','audit':'audit','call':'tools','remember':'memory'}[args.command]
    payload = None
    if args.command in {'call','remember'}:
        if args.json_file is None:
            parser.error('--json-file required for call/remember')
        payload = json.dumps(json.loads(args.json_file.read_text())).encode()
    request = Request('http://127.0.0.1:5050/api/agent/v1/'+route,data=payload,
        headers={'Authorization':'Bearer '+credential['token'],'Content-Type':'application/json'})
    try:
        with build_opener(NoRedirect()).open(request,timeout=30) as response:
            print(response.read().decode())
    except HTTPError as exc:
        print(exc.read().decode(),file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
