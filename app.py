M
My Workspace


k
My project

Production

FollowerBoostHQBot

Web Service
FollowerBoostHQBot
Python 3
Free
Upgrade your instance

Connect

Manual Deploy
Service ID:
srv-d98f4e7aqgkc73dhc1a0

kont4716-lab / FollowerBoostHQBot
main
f6270d3
Live
https://followerboosthqbot.onrender.com

Auto-Deploy has been disabled to prevent accidental deploys. This service was deployed with a specific commit.
Auto-Deploy Settings
Your free instance will spin down with inactivity, which can delay requests by 50 seconds or more.
Upgrade now
Update app.py
Deployed on
July 24, 2026
at
10:57:31 AM GMT+1
by
you

dep-d9hje2t8nd3s73d5qffg

Visit
Status
Live
Source
f6270d3
Trigger
Manual
Duration
41.7s

All logs
Search
Search logs

Live tail



Using cached blinker-1.9.0-py3-none-any.whl (8.5 kB)
Using cached click-8.4.2-py3-none-any.whl (119 kB)
Using cached deprecation-2.1.0-py2.py3-none-any.whl (11 kB)
Using cached h11-0.16.0-py3-none-any.whl (37 kB)
Using cached itsdangerous-2.2.0-py3-none-any.whl (16 kB)
Using cached jinja2-3.1.6-py3-none-any.whl (134 kB)
Using cached markupsafe-3.0.3-cp314-cp314-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (23 kB)
Using cached pyjwt-2.13.0-py3-none-any.whl (31 kB)
Using cached cryptography-49.0.0-cp311-abi3-manylinux_2_34_x86_64.whl (4.7 MB)
Using cached cffi-2.1.0-cp314-cp314-manylinux2014_x86_64.manylinux_2_17_x86_64.whl (221 kB)
Using cached StrEnum-0.4.15-py3-none-any.whl (8.9 kB)
Using cached typing_extensions-4.16.0-py3-none-any.whl (45 kB)
Using cached typing_inspection-0.4.2-py3-none-any.whl (14 kB)
Using cached werkzeug-3.1.8-py3-none-any.whl (226 kB)
Using cached yarl-1.24.5-cp314-cp314-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (110 kB)
Using cached idna-3.18-py3-none-any.whl (65 kB)
Using cached multidict-6.7.1-cp314-cp314-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (248 kB)
Using cached propcache-0.5.2-cp314-cp314-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (61 kB)
Using cached anyio-4.14.2-py3-none-any.whl (125 kB)
Using cached certifi-2026.7.22-py3-none-any.whl (136 kB)
Using cached packaging-26.2-py3-none-any.whl (100 kB)
Using cached pycparser-3.0-py3-none-any.whl (48 kB)
Installing collected packages: strenum, websockets, typing-extensions, pyjwt, pycparser, propcache, packaging, multidict, markupsafe, itsdangerous, idna, hyperframe, hpack, h11, click, certifi, blinker, annotated-types, yarl, werkzeug, typing-inspection, pydantic-core, jinja2, httpcore, h2, gunicorn, deprecation, cffi, anyio, pydantic, httpx, Flask, cryptography, realtime, supabase-functions, supabase-auth, storage3, postgrest, supabase
Successfully installed Flask-3.1.3 annotated-types-0.8.0 anyio-4.14.2 blinker-1.9.0 certifi-2026.7.22 cffi-2.1.0 click-8.4.2 cryptography-49.0.0 deprecation-2.1.0 gunicorn-26.0.0 h11-0.16.0 h2-4.4.0 hpack-4.2.0 httpcore-1.0.9 httpx-0.28.1 hyperframe-6.1.0 idna-3.18 itsdangerous-2.2.0 jinja2-3.1.6 markupsafe-3.0.3 multidict-6.7.1 packaging-26.2 postgrest-2.31.0 propcache-0.5.2 pycparser-3.0 pydantic-2.13.4 pydantic-core-2.46.4 pyjwt-2.13.0 realtime-2.31.0 storage3-2.31.0 strenum-0.4.15 supabase-2.31.0 supabase-auth-2.31.0 supabase-functions-2.31.0 typing-extensions-4.16.0 typing-inspection-0.4.2 websockets-15.0.1 werkzeug-3.1.8 yarl-1.24.5
[notice] A new release of pip is available: 25.3 -> 26.1.2
[notice] To update, run: pip install --upgrade pip
==> Uploading build...
==> Uploaded in 2.4s. Compression took 1.2s
==> Build successful 🎉
==> Deploying...
==> Setting WEB_CONCURRENCY=1 by default, based on available CPUs in the instance
==> Running 'gunicorn app:app'
[2026-07-24 09:58:10 +0000] [58] [INFO] Starting gunicorn 26.0.0
[2026-07-24 09:58:10 +0000] [58] [INFO] Listening at: http://0.0.0.0:10000 (58)
[2026-07-24 09:58:10 +0000] [58] [INFO] Using worker: sync
[2026-07-24 09:58:10 +0000] [60] [INFO] Booting worker with pid: 60
[2026-07-24 09:58:10 +0000] [58] [INFO] Control socket listening at /opt/render/.gunicorn/gunicorn.ctl
127.0.0.1 - - [24/Jul/2026:09:58:10 +0000] "HEAD / HTTP/1.1" 404 0 "-" "Go-http-client/1.1"
==> Your service is live 🎉
==> 
==> ///////////////////////////////////////////////////////////
==> 
==> Available at your primary URL https://followerboosthqbot.onrender.com
==> 
==> ///////////////////////////////////////////////////////////
127.0.0.1 - - [24/Jul/2026:09:58:13 +0000] "GET / HTTP/1.1" 404 207 "-" "Go-http-client/2.0"
127.0.0.1 - - [24/Jul/2026:09:58:18 +0000] "GET / HTTP/1.1" 404 207 "-" "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36"
127.0.0.1 - - [24/Jul/2026:09:58:18 +0000] "GET /favicon.ico HTTP/1.1" 404 207 "https://followerboosthqbot.onrender.com/" "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36"
Need better ways to work with logs? Try theRender CLI, Render MCP Server, or set up a log stream integration 

0 services selected:

Move

