"""Makes the pictures for the Devpost pages: diagrams for the story and framed screenshots for the gallery.

    python tools/submission/make.py            writes tools/submission/pages/*.html
    node tools/submission/render.mjs           renders them to docs/submission/<entry>/{story,gallery}/*.png (1920 x 1280, 3:2)

Screenshots come from the recordings in video-out/ (made by tools/video), so they show the real console.
"""
from pathlib import Path

OUT = Path(__file__).parent / "pages"
OUT.mkdir(exist_ok=True)

CSS = """
@font-face{font-family:"Press Start 2P";src:url("/src/bridge/web/static/fonts/press-start-2p-latin-400.woff2") format("woff2")}
@font-face{font-family:"Inter";font-weight:100 900;src:url("/src/bridge/web/static/fonts/inter-latin-var.woff2") format("woff2")}
:root{--cream50:#FFFDF5;--cream100:#FFF8E7;--cream200:#F4E9C7;--ink:#1A1320;--ink700:#3D2E4A;--ink500:#6B5878;--ink300:#A899B5;
--coral:#D96A62;--coralL:#F3D3CD;--mint:#5CA97A;--mintL:#D2E7DA;--sky:#4F9FAF;--skyL:#CFE5E9;--lemon:#DCAB3C;--lemonL:#F3E4BC;--lilac:#9482D3;--lilacL:#E0DAF2;--blue:#0B6BCB}
*{box-sizing:border-box}
body{margin:0;width:1280px;height:853px;overflow:hidden;font-family:Inter,system-ui,sans-serif;color:var(--ink);background:linear-gradient(#FFF8E7,#F1E3B8);position:relative}
h1{margin:0;font-size:44px;font-weight:900;letter-spacing:-.02em;line-height:1.1}
.pix{font-family:"Press Start 2P",monospace;font-weight:400}
.top{padding:34px 48px 0}
.kicker{font-family:"Press Start 2P",monospace;font-size:14px;color:var(--ink500);margin-bottom:12px}
.box{border:3px solid var(--ink);background:var(--cream50);box-shadow:6px 6px 0 rgba(26,19,32,.2);border-radius:4px}
.chip{display:inline-block;border:3px solid var(--ink);background:var(--lemon);font-weight:800;padding:6px 12px;font-size:20px;box-shadow:4px 4px 0 rgba(26,19,32,.2)}
.foot{position:absolute;left:48px;right:48px;bottom:24px;font-size:18px;font-weight:600;color:var(--ink700)}
.mark{position:absolute;right:48px;bottom:22px;font-family:"Press Start 2P",monospace;font-size:14px;color:var(--ink)}
.arrow{font-size:40px;font-weight:900;color:var(--ink);align-self:center}
.coin{width:84px;height:84px;border-radius:50%;border:3px solid var(--ink);display:flex;align-items:center;justify-content:center;font-weight:900;font-size:26px;background:var(--lemon);box-shadow:4px 4px 0 rgba(26,19,32,.2)}
.coin.g{background:var(--mint);color:#fff}.coin.s{width:64px;height:64px;font-size:20px}
.small{font-size:17px;color:var(--ink700);line-height:1.35}
.step{position:absolute;display:flex;flex-direction:column;gap:8px;padding:16px 18px}
.step b{font-size:21px;line-height:1.2}
.n{font-family:"Press Start 2P",monospace;font-size:13px;color:var(--ink500)}
.api{font-family:ui-monospace,Consolas,monospace;font-size:14px;background:var(--cream200);padding:3px 7px;border:2px solid var(--ink);display:inline-block;margin-top:2px}
"""


def page(name, body, extra_css=""):
    html = f"""<!doctype html><meta charset="utf-8"><title>{name}</title><style>{CSS}{extra_css}</style><body>{body}<script>window.ready=true</script>"""
    (OUT / f"{name}.html").write_text(html, encoding="utf-8")


def shot(name, kicker, title, img, caption, crop=None, note=None, w=1184):
    """A real screenshot in a frame, with a title above and a sentence below. crop = (x, y, w, h) of the 1920 x 1080 frame to show."""
    if crop:
        x, y, cw, h = crop
        W = w
        scale = W / cw
        inner = (f'<div style="width:{W}px;height:{int(h*scale)}px;overflow:hidden;position:relative">'
                 f'<img src="{img}" style="position:absolute;left:{-x*scale}px;top:{-y*scale}px;width:{1920*scale}px"></div>')
    else:
        inner = f'<img src="{img}" style="display:block;width:{w}px">'
    page(name, f"""
<div class="top"><div class="kicker">{kicker}</div><h1>{title}</h1></div>
<div class="box" style="position:absolute;left:{(1280-w-6)//2}px;top:128px;padding:0;overflow:hidden">{inner}</div>
<div class="foot" style="bottom:20px">{caption}</div>
{('<div class="chip" style="position:absolute;right:60px;top:40px">'+note+'</div>') if note else ''}
""")


# ---------------------------------------------------------------- diagrams (for the story)
page("d1-problem", """
<div class="top"><div class="kicker">THE PROBLEM</div><h1>On a normal site you lock the door until they pay.<br><span style="color:var(--blue)">Here, there is no door to lock.</span></h1></div>
<div class="box" style="position:absolute;left:48px;top:200px;width:560px;height:560px;padding:20px">
  <div class="pix" style="font-size:15px;margin-bottom:14px">A NORMAL WEBSITE</div>
  <div style="display:flex;align-items:center;gap:14px;margin-top:40px">
    <div class="box" style="padding:16px;width:170px;text-align:center"><div style="font-size:54px">☁</div><b>Seller's server</b><div class="small">agent works here</div></div>
    <div style="font-size:60px">🔒</div>
    <div class="box" style="padding:16px;width:150px;text-align:center;background:var(--mintL)"><b>Result</b><div class="small">stays behind the door</div></div>
  </div>
  <div style="display:flex;gap:12px;align-items:center;margin-top:34px"><div class="coin s">$</div><div class="arrow" style="font-size:30px">→</div><div class="small"><b>Customer pays</b>, then the door opens.<br>Easy.</div></div>
  <div class="chip" style="margin-top:40px;background:var(--mintL)">Payment can gate the result</div>
</div>
<div class="box" style="position:absolute;left:672px;top:200px;width:560px;height:560px;padding:20px;background:#FFF1EE">
  <div class="pix" style="font-size:15px;margin-bottom:14px">AGORA: ON THE BUYER'S PC</div>
  <div class="box" style="margin-top:28px;padding:18px;background:var(--cream100)">
    <div style="display:flex;gap:14px;align-items:center">
      <div class="box" style="padding:12px;width:160px;text-align:center;background:var(--lilacL)"><div style="font-size:42px">🧙</div><b>Seller's agent</b></div>
      <div class="box" style="padding:12px;width:150px;text-align:center;background:var(--lemonL)"><div style="font-size:42px">📁</div><b>Private files</b></div>
      <div class="box" style="padding:12px;width:120px;text-align:center;background:var(--mintL)"><b>Result</b></div>
    </div>
    <div class="small" style="margin-top:12px"><b>The buyer's computer.</b> The work and the result are already on the buyer's side.</div>
  </div>
  <div style="display:flex;gap:16px;align-items:center;margin-top:26px"><div style="font-size:60px">🚪</div><div class="small"><b>No lock possible.</b><br>The agent can't hold the result back.</div></div>
  <div class="chip" style="margin-top:20px;background:var(--coralL)">The only lever left: money committed first</div>
</div>
<div class="foot">If builders can't get paid, the best agents never get shared.</div>
""")

page("d2-money-flow", """
<div class="top"><div class="kicker">HOW A JOB IS PAID</div><h1>Hold first. Do the work. Settle by what the run did.</h1></div>
<div class="step box" style="left:40px;top:180px;width:224px;height:250px;background:var(--lemonL)"><div class="n">1</div><b>Buyer approves a hold</b><div class="small">The ceiling: the most this helper can charge. Nothing is taken yet.</div><span class="api">Orders v2 · AUTHORIZE</span></div>
<div class="arrow" style="position:absolute;left:268px;top:285px">→</div>
<div class="step box" style="left:304px;top:180px;width:224px;height:250px;background:var(--lilacL)"><div class="n">2</div><b>Helper works on the buyer's machine</b><div class="small">Fails or crashes? The hold is released and the buyer pays nothing.</div><span class="api">void</span></div>
<div class="arrow" style="position:absolute;left:532px;top:285px">→</div>
<div class="step box" style="left:568px;top:180px;width:224px;height:250px;background:var(--skyL)"><div class="n">3</div><b>Price comes from recorded facts</b><div class="small">2 thinking steps, 3 files read = a Standard run. Never from what the helper says.</div></div>
<div class="arrow" style="position:absolute;left:796px;top:285px">→</div>
<div class="step box" style="left:832px;top:180px;width:224px;height:250px;background:var(--mintL)"><div class="n">4</div><b>Capture part, release the rest</b><div class="small">25¢ captured. 15¢ goes back to the buyer.</div><span class="api">capture · final_capture=false</span></div>
<div class="arrow" style="position:absolute;left:1060px;top:285px">→</div>
<div class="step box" style="left:1096px;top:180px;width:150px;height:250px"><div class="n">5</div><b>Buyer decides</b><div class="small">Accept → author paid out.</div><span class="api">Payouts</span></div>

<div class="box" style="position:absolute;left:40px;top:490px;width:1200px;height:230px;padding:22px 26px">
  <div class="pix" style="font-size:14px;margin-bottom:16px">ONE 40¢ HOLD, IN THE DEMO</div>
  <div style="display:flex;border:3px solid var(--ink);height:64px;font-weight:900;font-size:24px">
    <div style="width:62.5%;background:var(--mint);display:flex;align-items:center;justify-content:center;color:#fff">25¢ charged (Standard run)</div>
    <div style="width:37.5%;background:var(--lemonL);display:flex;align-items:center;justify-content:center;border-left:3px solid var(--ink)">15¢ released</div>
  </div>
  <div style="display:flex;gap:30px;margin-top:18px" class="small">
    <div><b>10¢ light · 25¢ standard · 40¢ deep.</b> The author picks the plan; the buyer sees the ceiling before starting.</div>
    <div><b>Partial capture</b> is what lets the price be set after the work.</div>
  </div>
</div>
<div class="foot">Test money, on a practice server that copies PayPal's API.</div><div class="mark">AGORA</div>
""")

page("d3-decisions", """
<div class="top"><div class="kicker">WHO DECIDES WHAT</div><h1>The buyer's word moves a little money.<br>Only evidence moves all of it.</h1></div>
<div class="box" style="position:absolute;left:40px;top:300px;width:230px;height:120px;padding:16px;text-align:center;background:var(--skyL)"><b style="font-size:22px">Result ready</b><div class="small">the hold is still in place</div></div>
<div style="position:absolute;left:270px;top:346px;font-size:36px;font-weight:900">→</div>

<div class="box" style="position:absolute;left:330px;top:200px;width:360px;height:110px;padding:14px;background:var(--mintL)"><b style="font-size:21px">Buyer accepts</b><div class="small">The author is paid out through PayPal.</div></div>
<div class="box" style="position:absolute;left:330px;top:330px;width:360px;height:110px;padding:14px;background:var(--lemonL)"><b style="font-size:21px">"Not helpful"</b><div class="small">Only a small fee is kept; the rest comes back. Most of it, never all of it.</div></div>
<div class="box" style="position:absolute;left:330px;top:460px;width:360px;height:130px;padding:14px;background:var(--coralL)"><b style="font-size:21px">Run stopped mid-way (cheat suspected)</b><div class="small">The money stays held. The buyer's word alone cannot cancel it.</div></div>

<div style="position:absolute;left:700px;top:496px;font-size:36px;font-weight:900">→</div>
<div class="box" style="position:absolute;left:750px;top:460px;width:230px;height:130px;padding:14px;text-align:center;background:var(--lilacL)"><b style="font-size:21px">Independent certifier</b><div class="small">has it flagged that helper?</div></div>
<div class="box" style="position:absolute;left:1030px;top:410px;width:220px;height:100px;padding:12px;background:var(--mintL)"><b>Flagged</b><div class="small">Full refund. The author earns nothing.</div></div>
<div class="box" style="position:absolute;left:1030px;top:540px;width:220px;height:100px;padding:12px;background:var(--lemonL)"><b>Not flagged</b><div class="small">Claim rejected. The author keeps the fee.</div></div>

<div class="box" style="position:absolute;left:40px;top:460px;width:250px;height:130px;padding:14px;background:#EEE"><b style="font-size:20px">Crash or outage</b><div class="small">Hold released. Nobody is charged.</div></div>
<div class="foot">Money follows evidence: an honest result is paid, a proven cheat is refunded, an outage costs nothing.</div><div class="mark">AGORA</div>
""")

page("d4-plans", """
<div class="top"><div class="kicker">HOW AUTHORS CHARGE</div><h1>Five plans. The hold is always the most one answer can cost.</h1></div>
<style>.pl{position:absolute;top:190px;width:226px;height:430px;padding:18px}.pl b{font-size:22px;line-height:1.15;display:block;margin-bottom:10px}.big{font-weight:900;font-size:30px;letter-spacing:-.02em;margin:18px 0 10px;line-height:1.1}</style>
<div class="box pl" style="left:40px;background:var(--cream50)"><b>One price</b><div class="small">The same price for every answer. Simple and predictable.</div><div class="big">25¢</div><div class="small">every time</div></div>
<div class="box pl" style="left:278px;background:var(--skyL)"><b>By files read</b><div class="small">A starting price plus a few cents per file the helper read, up to a maximum.</div><div class="big">start + ¢ per file</div><div class="small">good when work grows with the notes</div></div>
<div class="box pl" style="left:516px;background:var(--lilacL)"><b>By thinking used</b><div class="small">A starting price plus cents for every 1,000 tokens the run used, up to a maximum.</div><div class="big">start + ¢ per 1k tokens</div><div class="small">follows the model's work</div></div>
<div class="box pl" style="left:754px;background:var(--mintL);outline:5px solid var(--lemon)"><b>By how hard the question was</b><div class="small">Light, standard or deep, decided from the engine's own journal.</div><div class="big">10¢ · 25¢ · 40¢</div><div class="small">deep = a program ran, 3+ thinking steps, or 12+ files</div></div>
<div class="box pl" style="left:992px;background:var(--lemonL)"><b>Monthly plan</b><div class="small">One fee, a set number of answers, 30 days. Never renews by itself; the buyer can stop it.</div><div class="big">$5 for 100 answers</div><div class="small">starts when payment settles</div></div>
<div class="foot">Authors see what a light, standard or deep run would cost before they publish. Prices shown are demo test money.</div><div class="mark">AGORA</div>
""")

# ---------------------------------------------------------------- gallery
page("g05-paypal-api", """
<div class="top"><div class="kicker">WHAT WE USE FROM PAYPAL</div><h1>Each money step is one PayPal call</h1></div>
<style>.row{position:absolute;left:48px;right:48px;height:104px;display:flex;align-items:center;gap:22px;padding:0 24px}.row .l{width:300px;font-weight:900;font-size:24px}.row .r{flex:1}</style>
<div class="box row" style="top:150px;background:var(--lemonL)"><div class="l">Hold</div><div class="r small"><b>Orders v2, intent AUTHORIZE.</b> The buyer approves on PayPal's page. The author never sees the card.</div></div>
<div class="box row" style="top:272px;background:var(--mintL)"><div class="l">Price after the work</div><div class="r small"><b>Partial capture</b> (<span class="api">final_capture: false</span>). Charge 25¢ of a 40¢ hold.</div></div>
<div class="box row" style="top:394px;background:var(--skyL)"><div class="l">Release / fail</div><div class="r small"><b>Void</b> the rest of the authorization. A failed run releases it all.</div></div>
<div class="box row" style="top:516px;background:var(--coralL)"><div class="l">Proven cheat</div><div class="r small"><b>Refund</b>, only after the independent certifier flags the helper.</div></div>
<div class="box row" style="top:638px;background:var(--lilacL)"><div class="l">Author gets paid</div><div class="r small"><b>Payouts</b> to the author's email. Every call carries a <span class="api">PayPal-Request-Id</span> so a retry never charges twice.</div></div>
<div class="foot">Verified on a local practice server that copies PayPal's API. Test money only.</div><div class="mark">AGORA</div>
""")

R = "/video-out/shots/"
shot("g02-approve", "STEP 1 · THE CEILING", "I approve a hold of 40¢. That's the most it can cost.", R + "pay-11.5.png",
     "The card names the hold and says nothing is charged until there is an answer.", w=1100)
shot("g03-paypal-page", "STEP 1 · ON PAYPAL'S PAGE", "The buyer approves on the payment page", R + "pay-16.png",
     "Practice server that copies the PayPal approval page. The author never sees the card, only an email for payouts.",
     crop=(560, 0, 800, 450), note="Test money")
shot("g04-receipts", "STEP 3 · THE RECEIPT", "25¢ charged, not 40¢. Not helpful: deposit only.", R + "pay-40.png",
     "\"Standard: 2 thinking steps, 3 files read: 25¢ of the 40¢ hold.\" Every receipt lists what happened, in plain language.",
     crop=(577, 385, 765, 580), note="Test money", w=870)
shot("g06-plans", "AUTHORS SET THE PRICE", "Pick a plan, see what a run would cost", R + "p07-14.png",
     "The Publish panel shows light, standard and deep prices before the helper goes on sale.")

Path(OUT / "manifest.txt").write_text("\n".join(p.stem for p in sorted(OUT.glob("*.html"))), encoding="utf-8")
print("pages:", len(list(OUT.glob("*.html"))))
