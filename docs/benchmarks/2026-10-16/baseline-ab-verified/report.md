# httpx comparison

Mode: **defaults**. Round: **1**. Targets: **96** across **32** groups.

The capture includes exact commands, binary hashes, version output, timings, raw JSONL, and stderr in the run directory.

| Outcome | Upstream | Fork |
| --- | ---: | ---: |
| HTTP responses | 96 | 96 |
| HTTP 2xx | 60 | 64 |
| Challenge-like heuristic | 4 | 2 |
| request_failure | 0 | 0 |
| missing | 0 | 0 |
| ambiguous | 0 | 0 |
| invalid_result | 0 | 0 |

Among 96 pairs with HTTP responses: 6 changed from non-2xx to 2xx; 2 changed from 2xx to non-2xx. 9 pairs changed status, 11 changed title, and 0 changed redirect status chain.

| Upstream → fork | Count |
| --- | ---: |
| 200 -&gt; 200 | 57 |
| 200 -&gt; 302 | 2 |
| 202 -&gt; 202 | 1 |
| 301 -&gt; 301 | 11 |
| 302 -&gt; 302 | 15 |
| 307 -&gt; 307 | 1 |
| 308 -&gt; 308 | 1 |
| 403 -&gt; 200 | 4 |
| 403 -&gt; 302 | 1 |
| 403 -&gt; 403 | 1 |
| 406 -&gt; 200 | 2 |

Latency: Paired 2xx HTTP responses, same status/final URL/media type, both timings present, no challenge-like evidence on either side; dynamic bodies may differ.

Comparable pairs: 57. Upstream median: 0.306170625 s. Fork median: 0.256918458 s. Median paired delta (fork − upstream): -0.032081916000000016 s.

| Target | Upstream | Fork | Upstream title | Fork title | Changed fields |
| --- | --- | --- | --- | --- | --- |
| https://github.com/ | 200 | 200 | GitHub · Change is constant. GitHub keeps you ahead. · GitHub · GitHub | GitHub · Change is constant. GitHub keeps you ahead. · GitHub · GitHub | body&#95;sha256 |
| https://docs.github.com/ | 302 | 302 |  |  | content&#95;type, content&#95;length, body&#95;sha256 |
| https://support.github.com/ | 302 | 302 |  |  | location |
| https://about.gitlab.com/ | 200 | 200 | GitLab - Speed with control for agentic software engineering | GitLab - Speed with control for agentic software engineering |  |
| https://docs.gitlab.com/ | 200 | 200 | GitLab Docs | GitLab Docs |  |
| https://forum.gitlab.com/ | 200 | 200 | GitLab Forum | GitLab Forum | content&#95;length, body&#95;sha256 |
| https://www.cloudflare.com/ | 200 | 200 | Cloudflare: Build for the agent era | Cloudflare: Build for the agent era | content&#95;length, body&#95;sha256 |
| https://developers.cloudflare.com/ | 200 | 200 | Cloudflare Developer Docs &#124; Cloudflare Docs | Cloudflare Developer Docs &#124; Cloudflare Docs | content&#95;length, body&#95;sha256 |
| https://blog.cloudflare.com/ | 200 | 200 | Cloudflare Blog | Cloudflare Blog |  |
| https://openai.com/ | 403 | 200 |  | OpenAI &#124; Research &amp; Deployment | status, title, content&#95;length, body&#95;sha256, challenge&#95;heuristic |
| https://help.openai.com/ | 403 | 302 |  |  | status, location, content&#95;type, content&#95;length, body&#95;sha256, challenge&#95;heuristic |
| https://platform.openai.com/ | 403 | 200 |  | OpenAI Platform | status, title, content&#95;length, body&#95;sha256, challenge&#95;heuristic |
| https://www.mozilla.org/ | 200 | 302 | Internet for people, not profit — Mozilla Global |  | status, title, location, content&#95;length, body&#95;sha256 |
| https://developer.mozilla.org/ | 302 | 302 |  | Found | title, content&#95;type, content&#95;length, body&#95;sha256 |
| https://support.mozilla.org/ | 406 | 200 |  | Client Challenge | status, title, content&#95;type, content&#95;length, body&#95;sha256, challenge&#95;heuristic |
| https://www.python.org/ | 200 | 200 | Welcome to Python.org | Welcome to Python.org |  |
| https://docs.python.org/3/ | 200 | 200 | 3.15.0 Documentation | 3.15.0 Documentation |  |
| https://discuss.python.org/ | 200 | 200 | Discussions on Python.org | Discussions on Python.org | content&#95;length, body&#95;sha256 |
| https://www.npmjs.com/ | 403 | 200 | Just a moment... | npm &#124; Home | status, title, content&#95;length, body&#95;sha256, challenge&#95;heuristic |
| https://docs.npmjs.com/ | 200 | 200 | npm Docs | npm Docs |  |
| https://registry.npmjs.org/ | 200 | 200 |  |  |  |
| https://www.docker.com/ | 200 | 200 | Docker &#124; Secure Sandboxes for AI Agents | Docker &#124; Secure Sandboxes for AI Agents |  |
| https://docs.docker.com/ | 200 | 200 | Docker Docs | Docker Docs |  |
| https://hub.docker.com/ | 200 | 200 | Docker Hub Container Image Library &#124; App Containerization | Docker Hub Container Image Library &#124; App Containerization | body&#95;sha256 |
| https://www.microsoft.com/ | 302 | 302 |  |  |  |
| https://learn.microsoft.com/ | 302 | 302 |  |  |  |
| https://support.microsoft.com/ | 301 | 301 |  |  |  |
| https://www.google.com/ | 200 | 200 | Google | Google | content&#95;length, body&#95;sha256 |
| https://developers.google.com/ | 200 | 200 | Google for Developers &#124; Build with Gemini | Google for Developers &#124; Build with Gemini | body&#95;sha256 |
| https://support.google.com/ | 200 | 200 | Google Help | Google Help | content&#95;length, body&#95;sha256 |
| https://www.apple.com/ | 200 | 200 | Apple | Apple |  |
| https://developer.apple.com/ | 200 | 200 | Apple Developer | Apple Developer | body&#95;sha256 |
| https://support.apple.com/ | 200 | 200 | Official Apple Support | Official Apple Support |  |
| https://www.wikipedia.org/ | 200 | 200 | Wikipedia | Wikipedia |  |
| https://en.wikipedia.org/ | 301 | 301 |  |  |  |
| https://it.wikipedia.org/ | 301 | 301 |  |  |  |
| https://www.wikimedia.org/ | 200 | 200 | Wikimedia | Wikimedia |  |
| https://commons.wikimedia.org/ | 301 | 301 |  |  |  |
| https://meta.wikimedia.org/ | 301 | 301 |  |  |  |
| https://stackoverflow.com/ | 302 | 302 |  |  |  |
| https://meta.stackoverflow.com/ | 200 | 200 | Meta Stack Overflow | Meta Stack Overflow | content&#95;length, body&#95;sha256 |
| https://chat.stackoverflow.com/ | 200 | 200 | All &#124; chat.stackoverflow.com | All &#124; chat.stackoverflow.com | body&#95;sha256 |
| https://www.reddit.com/ | 200 | 200 | Reddit | Reddit - Prove your humanity | title, content&#95;length, body&#95;sha256, challenge&#95;heuristic |
| https://old.reddit.com/ | 302 | 302 |  |  |  |
| https://developers.reddit.com/ | 200 | 200 | Reddit for Developers | Reddit for Developers | body&#95;sha256 |
| https://discord.com/ | 200 | 200 | Discord - Group Chat That’s All Fun &amp; Games | Discord - Group Chat That’s All Fun &amp; Games | body&#95;sha256 |
| https://support.discord.com/ | 302 | 302 |  |  |  |
| https://status.discord.com/ | 301 | 301 | 301 Moved Permanently | 301 Moved Permanently |  |
| https://www.spotify.com/ | 301 | 301 |  |  |  |
| https://developer.spotify.com/ | 200 | 200 | Home &#124; Spotify for Developers | Home &#124; Spotify for Developers |  |
| https://support.spotify.com/ | 302 | 302 |  |  |  |
| https://www.twitch.tv/ | 200 | 200 | Twitch | Twitch | body&#95;sha256 |
| https://dev.twitch.tv/ | 200 | 200 | Home &#124; Twitch Developers | Home &#124; Twitch Developers |  |
| https://blog.twitch.tv/ | 302 | 302 |  |  |  |
| https://www.shopify.com/ | 200 | 302 | Shopify: The All-in-One Commerce Platform for Businesses - Shopify |  | status, title, location, content&#95;type, content&#95;length, body&#95;sha256 |
| https://community.shopify.com/ | 200 | 200 | Shopify Community | Shopify Community | content&#95;length, body&#95;sha256 |
| https://help.shopify.com/ | 302 | 302 |  |  |  |
| https://stripe.com/ | 307 | 307 |  |  | location |
| https://docs.stripe.com/ | 200 | 200 | Documentazione Stripe | Stripe Documentation | title, content&#95;length, body&#95;sha256 |
| https://support.stripe.com/ | 200 | 200 | Stripe: Help &amp; Support | Stripe: Help &amp; Support | body&#95;sha256 |
| https://www.paypal.com/ | 302 | 302 |  |  | location, content&#95;type, content&#95;length, body&#95;sha256 |
| https://developer.paypal.com/ | 406 | 200 |  | PayPal Developer &#124; APIs, SDKs &amp; Integration Docs | status, title, content&#95;type, content&#95;length, body&#95;sha256 |
| https://newsroom.paypal-corp.com/ | 200 | 200 | PayPal Newsroom  &#124;  Home | PayPal Newsroom  &#124;  Home | body&#95;sha256 |
| https://www.booking.com/ | 202 | 202 |  |  | body&#95;sha256 |
| https://news.booking.com/ | 200 | 200 | Booking.com: Press | Booking.com: Press | body&#95;sha256 |
| https://careers.booking.com/ | 200 | 200 | Booking.com Careers site | Booking.com Careers site | body&#95;sha256 |
| https://www.tripadvisor.com/ | 403 | 403 | tripadvisor.com | tripadvisor.com | body&#95;sha256 |
| https://ir.tripadvisor.com/ | 403 | 200 | Access Denied | Investor Relations &#124; Tripadvisor | status, title, content&#95;length, body&#95;sha256 |
| https://tripadvisor.mediaroom.com/ | 200 | 200 | US Press Center &#124; TripAdvisor | US Press Center &#124; TripAdvisor | body&#95;sha256 |
| https://www.adobe.com/ | 200 | 200 | Adobe: Creative, marketing and document management solutions | Adobe: Creative, marketing and document management solutions |  |
| https://developer.adobe.com/ | 200 | 200 | The most memorable digital experiences are unleashed by developer creativity | The most memorable digital experiences are unleashed by developer creativity |  |
| https://helpx.adobe.com/ | 301 | 301 | 301 Moved Permanently | 301 Moved Permanently |  |
| https://www.notion.com/ | 200 | 200 | The AI workspace that works for you. &#124; Notion | The AI workspace that works for you. &#124; Notion | content&#95;length, body&#95;sha256 |
| https://developers.notion.com/ | 308 | 308 |  |  |  |
| https://status.notion.so/ | 301 | 301 | 301 Moved Permanently | 301 Moved Permanently |  |
| https://vercel.com/ | 200 | 200 | Agentic Infrastructure - Vercel | Agentic Infrastructure - Vercel |  |
| https://community.vercel.com/ | 200 | 200 | Vercel Community — Discussions, events, and projects | Vercel Community — Discussions, events, and projects | content&#95;length, body&#95;sha256 |
| https://www.vercel-status.com/ | 200 | 200 | Vercel Status | Vercel Status | body&#95;sha256 |
| https://www.netlify.com/ | 200 | 200 | Push your ideas to the web &#124; Netlify | Push your ideas to the web &#124; Netlify |  |
| https://docs.netlify.com/ | 200 | 200 | Netlify Documentation &#124; Netlify Docs | Netlify Documentation &#124; Netlify Docs |  |
| https://answers.netlify.com/ | 200 | 200 | Netlify Support Forums - Netlify Support Forums | Netlify Support Forums - Netlify Support Forums | content&#95;length, body&#95;sha256 |
| https://www.digitalocean.com/ | 200 | 200 | AI-Native Cloud &#124; DigitalOcean | AI-Native Cloud &#124; DigitalOcean |  |
| https://docs.digitalocean.com/ | 200 | 200 | DigitalOcean Docs &#124; DigitalOcean Documentation | DigitalOcean Docs &#124; DigitalOcean Documentation |  |
| https://status.digitalocean.com/ | 200 | 200 | DigitalOcean Status | DigitalOcean Status | body&#95;sha256 |
| https://www.elastic.co/ | 200 | 200 | Elastic: The search database for AI &#124; Search, AI agents, Observability, and Security &#124; Elastic | Elastic: The search database for AI &#124; Search, AI agents, Observability, and Security &#124; Elastic | body&#95;sha256 |
| https://docs.elastic.co/ | 301 | 301 |  |  |  |
| https://discuss.elastic.co/ | 200 | 200 | Discuss the Elastic Stack - Official ELK / Elastic Stack, Elasticsearch, Logstash, Kibana, Beats and more forums | Discuss the Elastic Stack - Official ELK / Elastic Stack, Elasticsearch, Logstash, Kibana, Beats and more forums | content&#95;length, body&#95;sha256 |
| https://sentry.io/ | 302 | 302 |  |  |  |
| https://docs.sentry.io/ | 200 | 200 | Sentry Docs &#124; Application Performance Monitoring &amp; Error Tracking Software | Sentry Docs &#124; Application Performance Monitoring &amp; Error Tracking Software |  |
| https://status.sentry.io/ | 200 | 200 | Sentry Status | Sentry Status | body&#95;sha256 |
| https://www.dropbox.com/ | 200 | 200 | Dropbox: Secure cloud storage, file sharing, and more | Dropbox: Secure cloud storage, file sharing, and more | content&#95;length, body&#95;sha256 |
| https://developers.dropbox.com/ | 301 | 301 |  |  |  |
| https://help.dropbox.com/ | 200 | 200 | Dropbox Help Center - How to use Dropbox - Dropbox Help | Dropbox Help Center - How to use Dropbox - Dropbox Help | content&#95;length, body&#95;sha256 |
| https://www.hackerone.com/ | 200 | 200 | HackerOne &#124; Leader in Continuous Threat Exposure Management &#124; Security for AI | HackerOne &#124; Leader in Continuous Threat Exposure Management &#124; Security for AI |  |
| https://docs.hackerone.com/ | 302 | 302 |  |  |  |
| https://support.hackerone.com/ | 302 | 302 |  |  |  |

Interpretation:

- A missing output, failed process, request failure, and HTTP response are separate outcomes.
- A 403-to-200 transition alone does not establish anti-bot bypass or equivalent content.
- Challenge-like labels include challenge and block-page header/title heuristics. They can produce false positives or miss challenges; they do not prove a WAF, bypass, or usable content.
- The two arms run sequentially; time, CDN routing, cache, server load, and request order can affect differences.
- Body hashes can differ for timestamps, cookies, localization, and other dynamic content.
- The 2 MiB response-read cap can truncate bodies and affect content hashes, lengths, and timing.
- A matched User-Agent still permits differences in DNS, connection reuse, HTTP version, compression, and headers.
- The configured rate limits initial probes; redirects and internal transport requests can add traffic.
- Redirect mode uses -maxr 3; upstream's limit counts the initial request, allowing at most two followed redirects.
- Per-request times describe these requests; they do not measure maximum throughput.
