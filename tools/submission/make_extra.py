"""Extra pictures for the Agora (PayPal) entry: the proof of the run on PayPal's own sandbox. Same look as make.py.
    python tools/submission/make_extra.py && node tools/submission/render.mjs"""
from make import page

page("d5-sandbox", """
<div class="top"><div class="kicker">VERIFIED ON PAYPAL'S OWN SANDBOX · 2026-10-30</div><h1>The whole flow ran on the real sandbox.<br><span style="color:var(--blue)">Each step read back from PayPal's API.</span></h1></div>
<style>.r{position:absolute;left:48px;right:48px;height:96px;display:flex;align-items:center;gap:22px;padding:0 24px}.r .l{width:330px;font-weight:900;font-size:24px}.r .m{flex:1}.r .s{font-weight:900;font-size:22px;border:3px solid var(--ink);padding:6px 14px;background:var(--mintL)}</style>
<div class="box r" style="top:230px;background:var(--lemonL)"><div class="l">1 · Hold 0.40 USD</div><div class="m small">Orders v2, intent AUTHORIZE. Approved by a sandbox buyer on PayPal's page.<br><span class="api">order 72976802Y2886202H</span></div><div class="s">COMPLETED</div></div>
<div class="box r" style="top:342px;background:var(--mintL)"><div class="l">2 · Partial capture 0.25</div><div class="m small">final_capture false: the price is set after the work.<br><span class="api">capture 8KM340019E533435E</span></div><div class="s">COMPLETED</div></div>
<div class="box r" style="top:454px;background:var(--skyL)"><div class="l">3 · Void the rest</div><div class="m small">The 15 cents not used are released to the buyer.<br><span class="api">authorization 938379318G574340P</span></div><div class="s">VOIDED</div></div>
<div class="box r" style="top:566px;background:var(--lilacL)"><div class="l">4 · Pay the author 0.23</div><div class="m small">Payouts, after the platform fee.<br><span class="api">payout batch 2BAZVTRQ8LG34</span></div><div class="s">SUCCESS</div></div>
<div class="foot">Test money. The refund path and the in-app approval redirect have so far been exercised on the practice server only.</div><div class="mark">AGORA</div>
""")
print("extra pages written")
