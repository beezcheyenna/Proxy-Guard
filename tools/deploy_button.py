#!/usr/bin/env python3
"""Print a deployment link only for an explicitly supplied public repository."""
import re,sys,urllib.parse
if len(sys.argv)!=2 or not re.fullmatch(r'https://(?:github\.com|gitlab\.com)/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',sys.argv[1]):
 raise SystemExit('Usage: python3 tools/deploy_button.py https://github.com/OWNER/REPOSITORY')
repo=sys.argv[1]+('/-/tree/main/companion/worker' if 'gitlab.com/' in sys.argv[1] else '/tree/main/companion/worker')
url='https://deploy.workers.cloudflare.com/?url='+urllib.parse.quote(repo,safe='')
print('[![Deploy to Cloudflare](https://deploy.workers.cloudflare.com/button)]('+url+')')
