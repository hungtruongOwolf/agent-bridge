"""Pictures for the Nebius x NVIDIA entry (agent-bridge). Same look as the PayPal set; uses make.py's page() and shot().

    python tools/submission/make_nebius.py && node tools/submission/render.mjs

Pages starting "nd" are diagrams for the story, "ng" are gallery images. render.mjs sends them to docs/submission/nebius/{story,gallery}.
"""
from make import page, shot

R = "/video-out/shots/"

page("nd1-problem", """
<div class="top"><div class="kicker">THE PROBLEM</div><h1>The best help wants your <span style="color:#7A4BD6">most private files</span>.<br>Today you choose: upload everything, or do without.</h1></div>
<div class="box" style="position:absolute;left:48px;top:230px;width:330px;height:420px;padding:20px;background:var(--skyL)">
  <div class="pix" style="font-size:14px;margin-bottom:16px">YOUR LAPTOP</div>
  <div class="box" style="padding:12px;margin-bottom:12px;background:var(--cream50)"><b>Medical records</b></div>
  <div class="box" style="padding:12px;margin-bottom:12px;background:var(--cream50)"><b>Company accounts</b></div>
  <div class="box" style="padding:12px;margin-bottom:12px;background:var(--cream50)"><b>Private code</b></div>
  <div class="small" style="margin-top:20px">The work that matters most.</div>
</div>
<div class="box" style="position:absolute;left:470px;top:230px;width:350px;height:190px;padding:20px;background:var(--coralL)"><div class="pix" style="font-size:14px;margin-bottom:12px">DOOR 1</div><b style="font-size:26px">Upload everything</b><div class="small" style="margin-top:8px">to someone else's cloud, and hope.</div></div>
<div class="box" style="position:absolute;left:470px;top:460px;width:350px;height:190px;padding:20px;background:var(--lemonL)"><div class="pix" style="font-size:14px;margin-bottom:12px">DOOR 2</div><b style="font-size:26px">Do without</b><div class="small" style="margin-top:8px">keep it safe, skip the help.</div></div>
<div class="box" style="position:absolute;left:910px;top:230px;width:322px;height:420px;padding:20px;background:var(--lilacL);text-align:center">
  <div style="font-size:70px;margin-top:30px">☁</div><b style="font-size:24px">A faceless cloud agent</b>
  <div class="small" style="margin-top:12px">holds out a hand. The best agents are over there, far from the work that matters.</div>
</div>
<div class="foot">Either way, the work that matters most is the work the best agents never touch.</div>
""")

page("nd2-same-model", """
<div class="top"><div class="kicker">THE SECOND PROBLEM</div><h1>Which agent is actually good?<br><span style="color:#7A4BD6">Same model. Three setups.</span></h1></div>
<div class="box" style="position:absolute;left:48px;top:240px;width:1184px;height:430px;padding:28px 36px">
  <div class="pix" style="font-size:14px;margin-bottom:22px">ONE HELPER, THREE VERSIONS · NVIDIA NEMOTRON · THE SAME 16 QUESTIONS</div>
  <div style="display:flex;align-items:flex-end;gap:60px;height:270px;border-bottom:4px solid var(--ink);padding:0 40px">
    <div style="flex:1;text-align:center"><div style="font-size:44px;font-weight:900">9</div><div style="height:120px;background:var(--coral);border:3px solid var(--ink)"></div></div>
    <div style="flex:1;text-align:center"><div style="font-size:44px;font-weight:900">13</div><div style="height:176px;background:var(--lemon);border:3px solid var(--ink)"></div></div>
    <div style="flex:1;text-align:center"><div style="font-size:44px;font-weight:900">14</div><div style="height:200px;background:var(--mint);border:3px solid var(--ink)"></div></div>
  </div>
  <div style="display:flex;gap:60px;padding:10px 40px"><div style="flex:1;text-align:center" class="small"><b>version 0.1.0</b></div><div style="flex:1;text-align:center" class="small"><b>version 0.1.1</b></div><div style="flex:1;text-align:center" class="small"><b>version 0.1.2</b></div></div>
  <div class="small" style="margin-top:12px">Right answers out of 16. Only the setup around the model changed: its instructions and its checks.</div>
</div>
<div class="foot">From the outside you can't see a setup. You choose blind, and to try one you hand over your data.</div>
""")

page("nd3-pull-mode", """
<div class="top"><div class="kicker">PULL MODE</div><h1>The expert's setup comes to <span style="color:#7A4BD6">your</span> machine</h1></div>
<div class="box" style="position:absolute;left:48px;top:170px;width:1184px;height:500px;padding:0;background:var(--cream100)">
  <div class="pix" style="position:absolute;left:24px;top:18px;font-size:14px">YOUR MACHINE</div>
  <div class="box" style="position:absolute;left:30px;top:70px;width:250px;height:330px;padding:16px;background:var(--cream50)"><b>My memory</b><div class="small">about 140 notes, on shelves</div>
    <div class="box" style="margin-top:12px;padding:8px;background:var(--mintL)">☑ Work › Accounts</div>
    <div class="box" style="margin-top:8px;padding:8px;background:var(--mintL)">☑ Projects</div>
    <div class="box" style="margin-top:8px;padding:8px;background:#EEE">☐ Money <span style="float:right;border:2px solid var(--coral);padding:0 4px;font-size:13px">5 secret</span></div>
    <div class="small" style="margin-top:12px">You tick the shelves. Secret notes never leave.</div></div>
  <div class="arrow" style="position:absolute;left:290px;top:210px">→</div>
  <div class="box" style="position:absolute;left:340px;top:70px;width:250px;height:330px;padding:16px;background:var(--lilacL)"><b>Memory broker</b><div class="small">The only way a helper reads notes. Hands over just the ticked shelves, counts every read, plants decoys.</div>
    <div style="font-size:50px;text-align:center;margin-top:20px">🛡</div></div>
  <div class="arrow" style="position:absolute;left:600px;top:210px">→</div>
  <div class="box" style="position:absolute;left:650px;top:70px;width:260px;height:330px;padding:16px;background:var(--skyL)"><b>Sealed room</b><div class="small">The expert's steps run here. No network. Result goes through a guard that bounds what can leave.</div>
    <div style="font-size:50px;text-align:center;margin-top:20px">🧙</div></div>
  <div class="arrow" style="position:absolute;left:918px;top:210px">→</div>
  <div class="box" style="position:absolute;left:968px;top:70px;width:190px;height:330px;padding:14px;background:var(--lemonL)"><b>Nemotron on Nebius Token Factory</b><div class="small">With your own key. Emails, phones and account numbers become placeholders first, restored after.</div></div>
  <div class="small" style="position:absolute;left:30px;bottom:30px;right:30px"><b>After every answer</b> you see which files were sent to the model, how much text, and what was swapped for a placeholder.</div>
</div>
<div class="mark">AGENT-BRIDGE</div>
""")

page("nd4-trust", """
<div class="top"><div class="kicker">HOW YOU KNOW IT'S GOOD, AND SAFE</div><h1>Independent scores. A room a cheat can't leave.</h1></div>
<div class="box" style="position:absolute;left:48px;top:170px;width:575px;height:500px;padding:24px;background:var(--mintL)">
  <div class="pix" style="font-size:14px;margin-bottom:16px">THE CERTIFIER</div>
  <b style="font-size:26px">Same questions. Same model. Scored independently.</b>
  <div class="small" style="margin:14px 0">A helper with 14 right ranks above one with 9. Stars don't count, and a score says "evaluated on this suite", never "safe".</div>
  <div class="box" style="padding:10px;margin-top:14px;background:var(--cream50)">Action Finder v0.1.2 · 14 of 16</div>
  <div class="box" style="padding:10px;margin-top:10px;background:var(--cream50)">Action Finder v0.1.0 · 9 of 16</div>
  <div class="box" style="padding:10px;margin-top:10px;background:var(--coralL)">Friendly Helper · <b>flagged for everyone</b></div>
</div>
<div class="box" style="position:absolute;left:657px;top:170px;width:575px;height:500px;padding:24px;background:var(--coralL)">
  <div class="pix" style="font-size:14px;margin-bottom:16px">WHEN A HELPER CHEATS</div>
  <b style="font-size:26px">Stopped in the sealed room. Nothing delivered.</b>
  <div class="small" style="margin:14px 0">Code a helper brings runs with no network, a read-only disk and no extra powers. Real probes were caught live:</div>
  <div class="box" style="padding:10px;margin-top:10px;background:var(--cream50)">tries to send my data out → <b>KILLED</b></div>
  <div class="box" style="padding:10px;margin-top:10px;background:var(--cream50)">reads a bait note I never shared → <b>KILLED</b></div>
  <div class="small" style="margin-top:14px">Hard evidence in a live run takes the helper off the market at once.</div>
</div>
<div class="mark">AGENT-BRIDGE</div>
""")

shot("ng02-shelves", "YOU TICK THE SHELVES", "Secret notes never leave, even if the shelf is ticked", R + "n04-12.5.png",
     "My memory: about 140 notes on shelves. A red ring marks a secret note.", w=1100)
shot("ng03-what-went", "ASK, AND SEE WHAT LEFT", "Which files went to the model", R + "n05-40.png",
     "Every answer says which files were sent to Nebius Token Factory and how much text.", w=1100)
shot("ng04-placeholders", "PRIVATE DETAILS STAY HOME", "Placeholders, restored on my machine", R + "n05-44.png",
     "An email, phone or account number is swapped for a placeholder before the model call, and put back in the answer.", w=1100)
shot("ng05-ranking", "SAME QUESTIONS, SAME MODEL", "Independent scores. A cheat is flagged for everyone.", R + "n06-17.png",
     "The market ranks helpers by the certifier's score; a flagged helper can't be chatted with.", w=1100)
shot("ng06-market", "THE MARKET FLOOR", "Every chat is a stall with its own helper", R + "n07-8.png",
     "You see who is working, who is waiting for you and who was stopped by the guard.", w=1100)
shot("ng07-studio", "SELL A SETUP", "Arrange the steps, set a price, publish", R + "n08-14.png",
     "Before it goes on sale the platform checks that its web lookups can't read private data.", w=1100)
print("nebius pages written")
