import json, html
V,P,G,X,N = "ok","part","gap","exp","own"
CARD_H = 92
# (id, x, y, w, status, mono, title, desc)
cards = [
 # Release plane
 ("c_cap",45,229,190,V,"C","capabilities/<name>/","manifest, SKILL.md, eval cases. 2 capabilities"),
 ("c_src",250,229,190,V,"S","src/ packages","MCP code for stdio and remote"),
 ("c_pr",45,399,190,V,"PR","PR checks (dry run)","Common baseline, platform checks, evals. Ran green"),
 ("c_rev",250,399,190,P,"R","Review gate","main needs a PR and a passing check. Approvals set to 0, no review team"),
 ("c_rel",45,569,190,V,"Rl","Release job (merge)","Signs with a real secret key, verifies every release before publishing"),
 ("c_reg",250,569,190,P,"Rg","Registry","Git branch, 3 releases, shared-secret signing. KMS or Sigstore later"),
 ("c_dep",45,739,190,V,"D","Deploy job","Deploys to AWS from CI via OIDC. Code hash proven. Entra check not yet in CI"),
 ("c_cat",250,739,190,P,"Ct","Catalogue build","Feed + OpenAI marketplace on a catalogue branch. Local one is laptop-only"),
 # Distribution
 ("c_lm",530,229,270,V,"L","Local marketplace","marketplace.json. Plugins appear and install in Codex"),
 ("c_om",530,335,270,P,"O","OpenAI workspace marketplace","Published to the catalogue branch. Never imported by an admin"),
 ("c_app",530,441,270,G,"A",".app.json plugin kind","Needs an admin-registered OpenAI app id"),
 ("c_oasis",530,609,270,P,"Oa","OASIS feed.json","Provisional format. Real contract unconfirmed"),
 ("c_rbac",530,779,270,G,"Rb","Plugin RBAC groups","Entra groups per capability. tools/list per user"),
 # Cross-cutting
 ("c_ev",45,1019,240,G,"E","Common audit event","Same fields on AWS, Azure and local (K-036)"),
 ("c_geo",305,1019,240,G,"Ge","Geordie consumer","Reads platform telemetry, flags unapproved tools (R6)"),
 ("c_susp",565,1019,240,P,"Su","Suspension control","S3 list (AWS) and Blob list (Azure) work. Local has none. No one CLI for both"),
 ("c_cost",45,1125,240,P,"$","Cost guard","AWS $25 budget, no alert email. Nothing on Azure yet"),
 ("c_cw",305,1125,240,V,"Cw","Audit sinks","CloudWatch (AWS) and Container Apps logs (Azure): user, capability, version"),
 ("c_cache",565,1125,240,P,"T","Trust lifetimes","5 s on AWS and Azure. Local and others undefined (K-024)"),
 # Laptop
 ("c_lid",905,229,260,G,"Id","Local identity","Uses the OS username. No Entra, no SPIFFE"),
 ("c_lrev",1195,229,260,G,"Rv","Local revocation","Cannot stop a package already on a laptop"),
 ("c_lmcp",1485,229,260,V,"M","incident-lookup (stdio)","Verified in Codex. Codex plugin cache holds the copy"),
 # AWS
 ("c_thr",905,474,400,V,"Th","Throttling and limits","10 requests/s, burst 20, set at the gateway"),
 ("c_gw",1325,474,400,V,"Gw","API Gateway + Entra JWT check","Issuer, audience and scope checked before the function runs"),
 ("c_sus",905,639,400,V,"Sp","Suspension list","S3 object, 5 s cache, fails closed"),
 ("c_lam",1325,639,400,V,"La","project-status remote MCP","Lambda from the approved wheel. Does not call the agent yet"),
 ("c_aud",905,804,190,V,"Au","Audit","CloudWatch: user, capability, version"),
 ("c_net",1115,804,190,G,"Nw","Private network path","Public internet today"),
 ("c_be",1325,804,400,G,"Be","Backend service","In-process synthetic data. No separate service, no workload identity"),
 # Azure
 ("c_areg",905,1049,400,G,"Rg","Registered capability","Pipeline support for kind=agent: image digest pinned, tools from live tools/list. Not built"),
 ("c_agw",1325,1049,400,V,"Gw","Agent gateway (Container App)","Entra check, allowed callers, suspension (Blob), audit. OBO call to the agent proven live"),
 ("c_agent",905,1214,260,X,"Ag","tag-compliance-elna","Container App, tool tag.inspect. Tool calls need its API key; no Entra, discovery is open. Unchanged"),
 ("c_dbx",1195,1214,260,G,"Db","Databricks governed path","Read as the signed-in user, with audit"),
 ("c_aing",1485,1214,260,G,"Lk","Agent ingress lockdown","Agent still reachable directly. Close it so only the gateway can call it"),
 # MuleSoft (Arm)
 ("c_mreg",905,1459,260,G,"Rg","Agent Registry (Exchange)","Register the approved release. Needs Anypoint sandbox access"),
 ("c_mgw",1195,1459,260,G,"Og","Omni Gateway policies","Entra JWT check, MCP access rules, OBO policy. Managed or Connected mode only"),
 ("c_mfab",1485,1459,260,N,"Af","Arm-i on Agent Fabric","Arm runs this today for business processes. Orchestrates; not ours to build"),
 # Right column
 ("c_codex",1800,229,280,P,"Cx","Codex (Arm user)","Local install and local tool call verified. Remote call and OAuth sign-in not tried"),
 ("c_entra",1800,474,280,V,"En","Microsoft Entra ID","3 app registrations (MCP, Codex client, agent). Real tokens and OBO verified"),
 ("c_spiffe",1800,804,200,G,"Sf","SPIFFE / SPIRE","Workload identity for backend and agent. Nothing built"),
]
# layers: (id,x,y,w,h,title,sub,indigo)
layers = [
 ("Lr1",30,185,430,150,"Source","Capabilities and code in Git",0),
 ("Lr2",30,355,430,150,"Checks and approval","Before anything is published",0),
 ("Lr3",30,525,430,150,"Release","Signed, immutable records",0),
 ("Lr4",30,695,430,150,"Publish","Deploy and catalogue",0),
 ("Lm1",515,185,300,360,"Marketplaces","Where Codex finds plugins",1),
 ("Lm2",515,565,300,150,"Discovery","Feed for OASIS",1),
 ("Lm3",515,735,300,150,"Access policy","Who may see and use what",1),
 ("Lx",30,975,780,256,"Observability, audit and cost","Same record on every platform",0),
 ("Ll1",885,185,870,150,"Local MCP","stdio process started by Codex",1),
 ("La1",885,430,870,150,"Gateway (native)","API Gateway, HTTP API",0),
 ("La2",885,595,870,150,"Capability runtime","Lambda, arm64",0),
 ("La3",885,760,870,150,"Backend and data","Audit, network, data source",0),
 ("Lz1",885,1005,870,150,"Gateway","In front of the agent",0),
 ("Lz2",885,1170,870,150,"Agent and data","Where the work runs",0),
 ("Lq1",885,1415,870,150,"Gateway and registry","Arm's MuleSoft Agent Fabric",0),
]
bounds = [
 (10,130,470,770,"Release plane · GitHub"),
 (500,130,330,770,"Discovery and distribution"),
 (10,920,820,330,"Cross-cutting controls"),
 (870,130,900,225,"Laptop · Codex local"),
 (870,375,900,555,"AWS sandbox · us-east-1"),
 (870,950,900,390,"Azure lab subscription · westus2"),
 (870,1360,900,235,"MuleSoft Anypoint · Arm sandbox (to request)"),
]
# links: [from,to,sideA,sideB,gap?, opts]
links = [
 ("Lr1","Lr2","bottom","top",0,{}),("Lr2","Lr3","bottom","top",0,{}),("Lr3","Lr4","bottom","top",0,{}),
 ("Lr4","Lm1","right","left",0,{}),
 ("c_codex","c_lmcp","left","right",0,{}),
 ("c_entra","c_gw","left","right",0,{}),
 ("c_gw","c_lam","bottom","top",0,{}),
 ("c_sus","c_lam","right","left",0,{}),
 ("c_lam","c_be","bottom","top",1,{}),
 ("c_spiffe","c_be","left","right",1,{}),
 ("c_areg","c_agw","right","left",1,{}),
 ("c_agw","c_agent","bottom","top",0,{"my":1190,"dxB":0}),
 ("c_entra","c_agw","bottom","right",0,{"dxA":100}),
]
SH = 100
cards = [(i,x,y-SH,w,st,m,t,d) for i,x,y,w,st,m,t,d in cards]
layers = [(i,x,y-SH,w,h,t,sb,ind) for i,x,y,w,h,t,sb,ind in layers]
bounds = [(x,y-SH,w,h,l) for x,y,w,h,l in bounds]
links = [(a,b,sa,sb,g,({**o,"my":o["my"]-SH} if "my" in o else o)) for a,b,sa,sb,g,o in links]
STATUS = {V:("Verified","#1F7A4D"),P:("Partial","#B7791F"),G:("Gap","#C0392B"),X:("Exposed","#8E44AD"),N:("Arm-owned","#4B5563")}
def esc(s): return html.escape(s, quote=True)
out=[]
out.append('''<title>Governed MCP Build Map</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
:root{--page:#FFFFFF;--layer:#F7F8FA;--line:#D5D9E0;--ink:#111827;--sub:#6B7280;--wire:#374151;--blue:#2F5BEA;--indigo:#4F46E5;--pill:#0B5D63;--ok:#1F7A4D;--part:#B7791F;--gap:#C0392B;--exp:#8E44AD;color-scheme:light}
html,body{background:#fff}
body{margin:0;color:var(--ink);font-family:Arial,Helvetica,sans-serif;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:20px}
h1{font-size:22px;margin:0 0 6px}p.lead{margin:0 0 14px;color:var(--sub);font-size:13px;max-width:900px;line-height:1.5}
.legend{display:flex;flex-wrap:wrap;gap:14px 22px;margin:0 0 14px;font-size:12px;color:var(--ink);align-items:center}
.legend span{display:inline-flex;align-items:center;gap:7px}.sw{width:14px;height:14px;border-radius:3px;border:2px solid}
.ln{width:30px;border-top:2px dashed var(--wire)}.ln.g{border-top-color:var(--gap)}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:#fff}
.canvas{position:relative;width:2100px;height:1520px;background:#fff}
.wires{position:absolute;inset:0;width:100%;height:100%;overflow:visible;z-index:2;pointer-events:none}
.boundary{position:absolute;border:1.5px dashed #B8BEC8;border-radius:24px;background:#FBFBFC;z-index:0;box-sizing:border-box}
.pill{position:absolute;left:18px;top:-14px;background:var(--pill);color:#fff;font-weight:700;font-size:14px;padding:6px 18px;border-radius:999px;white-space:nowrap}
.layer{position:absolute;background:var(--layer);border:1px solid var(--line);border-left:5px solid var(--blue);border-radius:6px;z-index:1;padding:10px 14px;box-sizing:border-box}
.layer.indigo{border-left-color:var(--indigo)}.layer h3{margin:0;font-size:14px}.layer p{margin:3px 0 0;font-size:11px;color:var(--sub)}
.card{position:absolute;display:flex;gap:10px;align-items:flex-start;background:#fff;border:1.5px solid var(--line);border-radius:6px;box-shadow:0 2px 6px rgba(16,24,40,.12);padding:12px 12px 10px;box-sizing:border-box;z-index:3;height:92px;overflow:hidden}
.card b{display:block;font-size:12.5px;line-height:1.25}.card small{display:block;font-size:10.5px;color:var(--sub);margin-top:3px;line-height:1.3}
.ico{flex:0 0 28px;height:28px;border-radius:7px;display:grid;place-items:center;color:#fff;font-weight:700;font-size:11px}
.st-ok{border-color:var(--ok)}.st-ok .ico{background:var(--ok)}
.st-part{border-color:var(--part)}.st-part .ico{background:var(--part)}
.st-gap{border-color:var(--gap);border-style:dashed;background:#FFF6F5}.st-gap .ico{background:var(--gap)}
.st-own{border-color:#4B5563;background:#F3F4F6}.st-own .ico{background:#4B5563}
.st-exp{border-color:var(--exp);background:#FAF5FC}.st-exp .ico{background:var(--exp)}
.badge{position:absolute;bottom:-1px;right:8px;transform:translateY(50%);color:#fff;font-size:9.5px;font-weight:700;padding:2px 8px;border-radius:999px;z-index:4;letter-spacing:.2px}
.card{overflow:visible}
section.order{margin-top:22px}section.order h2{font-size:16px;margin:0 0 10px}
ol{margin:0;padding-left:22px;max-width:980px;font-size:13px;line-height:1.55}ol li{margin-bottom:6px}ol b{font-weight:700}
.note{margin-top:14px;font-size:12px;color:var(--sub);max-width:980px;line-height:1.5}
</style>
<h1>Governed MCP Build Map</h1>
<p class="lead">What exists today across the release plane, the Codex-facing marketplaces, and the three runtime platforms, with what is verified, what is partial, and what is still to build. Everything runs against synthetic data.</p>
<div class="legend">
<span><i class="sw" style="border-color:var(--ok);background:#EAF7EF"></i>Verified: tested live</span>
<span><i class="sw" style="border-color:var(--part);background:#FDF4E1"></i>Partial: built, with a known fault or missing piece</span>
<span><i class="sw" style="border-color:var(--gap);border-style:dashed;background:#FFF6F5"></i>Gap: not built</span>
<span><i class="sw" style="border-color:var(--exp);background:#FAF5FC"></i>Exposed: exists, outside governance</span>
<span><i class="sw" style="border-color:#4B5563;background:#F3F4F6"></i>Arm-owned: exists at Arm, outside our build</span>
<span><i class="ln"></i>Flow that works</span><span><i class="ln g"></i>Flow still missing</span>
</div>
<div class="scroll"><div class="canvas" id="canvas">''')
for x,y,w,h,label in bounds:
    out.append(f'<div class="boundary" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px"><span class="pill">{esc(label)}</span></div>')
for i,x,y,w,h,t,s,ind in layers:
    out.append(f'<div class="layer{" indigo" if ind else ""}" id="{i}" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px"><h3>{esc(t)}</h3><p>{esc(s)}</p></div>')
for cid,x,y,w,st,mono,t,d in cards:
    label,col = STATUS[st]
    out.append(f'<div class="card st-{st}" id="{cid}" style="left:{x}px;top:{y}px;width:{w}px"><span class="badge" style="background:{col}">{label}</span><span class="ico">{esc(mono)}</span><div><b>{esc(t)}</b><small>{esc(d)}</small></div></div>')
out.append('<svg class="wires" id="wires"></svg></div></div>')
out.append('''<section class="order"><h2>What to build, in order</h2><ol>
<li><b>Done today: signing, review gate, CI deploy.</b> Releases are signed with a real key and verified, <code>main</code> needs a PR and a passing check, and a merge deploys to AWS from CI. Still open from this step: a CI identity so the pipeline can also run the real Entra check, and a review team.</li>
<li><b>Azure agent: gateway built and verified.</b> Entra token check, allowed-callers list, suspension and audit sit in front of the agent, and a real on-behalf-of call reaches it. Still open: register it through the pipeline as an agent capability, call it from the AWS MCP, and close the agent's own public ingress.</li>
<li><b>Add SPIFFE.</b> Stand up a sandbox trust domain, split the backend from the function, and make the gateway-to-backend call use a workload identity. AWS first, then the agent.</li>
<li><b>MuleSoft platform.</b> Register a capability in Agent Fabric and publish it through Omni Gateway with the Entra check. Needs an Anypoint sandbox and an answer on self-hosting; see docs/mulesoft.md.</li>
<li><b>Give local MCP real identity.</b> Sign the user in with Entra and add a way to withdraw a package already installed on a laptop.</li>
<li><b>Plugin access by group.</b> Entra groups decide who sees and uses each capability; tools/list follows the user.</li>
<li><b>Databricks.</b> A governed read path that passes the signed-in user through and is audited.</li>
<li><b>One audit record and Geordie.</b> A common event format on every platform, one suspension control for all of them, and Geordie reading the telemetry.</li></ol>
<p class="note">Not shown, because nothing is built: KPaaS gateway, A2A, multi-region. Codex-to-OpenAI details that depend on decision D8 (how plugins reach OpenAI) are unconfirmed.</p></section>
<script>
const links=''' + json.dumps([[a,b,sa,sb,g,o] for a,b,sa,sb,g,o in links]) + ''';
function pt(el,side,dx){const c=document.getElementById('canvas').getBoundingClientRect(),r=el.getBoundingClientRect();const x=r.left-c.left,y=r.top-c.top;dx=dx||0;
 return side==='left'?[x,y+r.height/2]:side==='right'?[x+r.width,y+r.height/2]:side==='top'?[x+r.width/2+dx,y]:[x+r.width/2+dx,y+r.height];}
function draw(){const svg=document.getElementById('wires');
 svg.innerHTML='<defs><marker id="a1" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="#374151"/></marker><marker id="a2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="#C0392B"/></marker></defs>';
 for(const [a,b,sa,sb,gap,o] of links){const A=pt(document.getElementById(a),sa,o.dxA),B=pt(document.getElementById(b),sb,o.dxB);const ha=(sa==='left'||sa==='right'),hb=(sb==='left'||sb==='right');let d;
  if(ha&&hb){const mx=o.mx??(A[0]+B[0])/2;d=`M${A[0]} ${A[1]}H${mx}V${B[1]}H${B[0]}`;}
  else if(!ha&&!hb){const my=o.my??(A[1]+B[1])/2;d=`M${A[0]} ${A[1]}V${my}H${B[0]}V${B[1]}`;}
  else if(ha){d=`M${A[0]} ${A[1]}H${B[0]}V${B[1]}`;}else{d=`M${A[0]} ${A[1]}V${B[1]}H${B[0]}`;}
  const col=gap?'#C0392B':'#374151';
  svg.insertAdjacentHTML('beforeend',`<path d="${d}" fill="none" stroke="${col}" stroke-width="1.8" stroke-dasharray="6 5" marker-end="url(#${gap?'a2':'a1'})"/>`);}}
window.addEventListener('load',draw);window.addEventListener('resize',draw);
</script>''')
open("body.html","w").write("\n".join(out))
open("index.html","w").write("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'></head><body>"+"\n".join(out)+"</body></html>")
print("ok", len(cards), "cards")
