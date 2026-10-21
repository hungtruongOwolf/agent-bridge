"""Writes examples/vault-library.json: a lived-in memory for a demo user, to show every case the memory has to handle.

    python examples/make_library.py
    bridge serve --vault examples/vault-library.json --state .bridge-library

The person is invented: Linh Tran, who runs Lumen Analytics, a six-person B2B software company in Austin. The library has
about 170 notes on 40-odd shelves, so it exercises:
  - shelves inside shelves, several levels deep, and names with accents (Tomás) that are found without typing the accent;
  - short facts, contacts, meeting logs, and long notes (1.5k to 6k characters) that are stored as passages;
  - secret notes (money, HR, documents, journal) that must never be shared, next to everyday notes on the same topic;
  - two people with the same first name, an old fact and the newer fact that replaced it, near-duplicate notes;
  - notes written at different times, so "newest first" and "anything new?" have something to say;
  - the sample sales and meeting helpers' subjects (Acme, Globex, Initech, Hooli, ...), so their answers are meaningful.
The first records keep the ids used by examples/vault.json (n1, n2, n4, n5, n3, c1, f1) so the sample tests still make sense.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from bridge.memory.chunking import guess_title, split_document  # noqa: E402

BASE = 1_792_454_400  # 2026-10-20, so the data is the same every time it is made
DAY = 86400
R: list[dict] = []
_n = {"m": 0, "c": 0}


def add(shelf, text, *, days=30, level="low", kind="note", id=None, edited=False):
    if id is None:
        key = "c" if kind == "contact" else "m"
        _n[key] += 1
        id = f"{key}{100 + _n[key]}"
    t = BASE - days * DAY
    R.append({"id": id, "type": kind, "sensitivity": level, "text": text.strip(), "path": shelf, "created": float(t),
              "updated": float(t + (3 * DAY if edited else 0)), "edited": edited})


def long(shelf, text, *, days=30, level="low", title=None, doc=None):
    n = len([r for r in R if r.get("doc")]) and len({r["doc"] for r in R if r.get("doc")}) + 1 or 1
    doc = doc or f"doc{n}"
    parts = split_document(text.strip())
    t = BASE - days * DAY
    for i, chunk in enumerate(parts, 1):
        R.append({"id": f"{doc}.{i}", "type": "note", "sensitivity": level, "text": chunk, "path": shelf, "created": float(t),
                  "updated": float(t), "edited": False, "doc": doc, "title": title or guess_title(text), "part": i})


# ================================================================== work / accounts
add("work/accounts", "Sales pipeline review: three large accounts (Acme, Globex, Initech) are at risk because their renewal budgets were cut this quarter.", days=14, id="n1")
add("work/accounts", "Accounts scorecard, end of September: Acme amber, Globex red, Initech amber, Hooli green, Umbrella green, Wayne Corp green. Revenue at risk: about 410k.", days=20)
add("work/accounts/acme", "Acme: renewal call is booked for November 12. Maria wants to talk about a discount before signing.", days=9)
add("work/accounts/acme", "Acme pays in euros and wants invoices sent on the first of the month.", days=120)
add("work/accounts/acme", "Acme expanded to a second office in Lisbon, which could mean more seats next year.", days=75)
add("work/accounts/acme", "Acme security questionnaire for this year is due on October 31. Last year it took nine days to answer; Sam owns it.", days=6)
add("work/accounts/acme", "Acme usage by team: support 61 percent, sales 22 percent, finance 9 percent, everyone else 8 percent. Support grew the most this year.", days=40)
add("work/accounts/acme", "Acme's old contact for billing was Tom Reyes (tom.reyes@acme.example). He left in August; send invoices to Maria Lopez now.", days=58, edited=True)
add("work/accounts/globex", "Globex froze hiring and cut its tools budget by thirty percent, so the renewal is at risk.", days=12)
add("work/accounts/globex", "Globex champion Dana Whitfield left in September; nobody new owns the relationship yet.", days=35)
add("work/accounts/globex", "Globex asked whether we can offer a monthly plan instead of annual. Finance would say yes only if there is no minimum seat count.", days=22)
add("work/accounts/globex", "Globex renewal date is December 15. They have not answered the last two emails.", days=4)
add("work/accounts/initech", "Initech asked for a security questionnaire before they will renew. Due at the end of the month.", days=16)
add("work/accounts/initech", "Initech support tickets dropped by half after the onboarding fix, which is good news for the renewal.", days=26)
add("work/accounts/initech", "Initech's new CTO, Bill Lumbergh, wants one invoice for all four of their subsidiaries instead of four separate ones.", days=11)
add("work/accounts/hooli", "Hooli renewed early for two years and asked for a case study.", days=33)
add("work/accounts/hooli", "Hooli case study: they are happy to be named, but legal must approve the quotes first. Priya is drafting it.", days=18)
add("work/accounts/umbrella", "Umbrella is a healthcare customer, so any data export needs a signed addendum first. Renewal in March.", days=50)
add("work/accounts/umbrella", "Umbrella asked for single sign-on. It is on the roadmap for Q1; do not promise a date.", days=28)
add("work/accounts/wayne-corp", "Wayne Corp is our largest account. Their procurement team requires a new vendor review every year in November.", days=45)
add("work/accounts/wayne-corp", "Wayne Corp's budget is cut but they say analytics is protected. Lee Chen asked for a price hold for one more year.", days=13)
long("work/accounts/acme", """# Acme account plan, Q4

## Where we stand
Acme has been a customer for three years and is our second largest account. Usage grew 18 percent last year, mostly from the support team. The renewal is due on December 1 and the budget owner, Maria Lopez, told us in October that finance cut every tools budget by about a third.

## What Maria cares about
Maria cares about two things: predictable cost and fewer tools to manage. She prefers email on Mondays and does not like surprise invoices. Last year a billing mistake delayed the renewal by six weeks, so any change in price needs to be explained in writing before it reaches her inbox.

## Risks
The main risk is the budget cut. A second risk is the champion on the product side, who is moving to another team in January. If the new owner has not met us before the renewal call, we should expect a slower decision. The third risk is the security questionnaire Acme's compliance team sends every year; last year it took us nine days to answer.

## Options we discussed
Option one is a two-year deal at a ten percent discount with annual billing. Option two is a smaller plan with fewer seats, which keeps the price flat but removes the analytics add-on. Priya prefers option one because it locks the account in; Sam prefers option two because it keeps the margin healthy. We agreed to prepare both and let Maria choose.

## Next steps
Priya prepares both quotes by Friday. Sam answers the security questionnaire early, before the renewal call. Lee books an introduction between the new product owner and our team in the first week of December. Everyone reviews the plan on Thursday.""", days=8)
long("work/accounts/globex", """# Globex renewal risk memo

Globex is red. Three things happened in the last two months. First, they froze hiring and cut the tools budget by thirty percent. Second, our champion, Dana Whitfield, left in September and nobody replaced her. Third, they have stopped answering email; the last two went unanswered for ten days.

## What we know about the budget
Their finance team publishes a quarterly review. The next one is on November 3. Until then we cannot know whether our line survives. Dana told us in July that analytics was safe because it feeds the board report, but that was before the cut.

## What we could offer
A monthly plan with no minimum seats would cost us margin but keep the logo. A pause of three months at no charge would keep the contract alive. A smaller read-only plan would keep dashboards on for the executives who read the board report.

## What I would do
Ask Priya to call the new head of operations directly, not through email. Offer the read-only plan first. Do not discount the full plan; it teaches them to ask again next year. Decide by November 5 so there is time before the December 15 renewal.""", days=15)
long("work/accounts/wayne-corp", """# Wayne Corp vendor review, November

Wayne Corp runs a vendor review every November, and passing it is required to renew. The review has four parts: security, financial health, support quality, and data handling.

## Security
They want the latest penetration test summary, our SOC 2 report, and the list of subprocessors. The test summary is from March and is still valid; the SOC 2 report is valid until January. Sam has both.

## Financial health
They ask for two years of revenue and a statement that we are not in default on any loan. Linh signs this. The accountant, Dr. Nguyen, prepares the numbers; send her the request by November 1.

## Support quality
They will read our support ticket statistics: first response time, resolution time, satisfaction. This year first response is 43 minutes, down from 71. Lee should prepare a one-page summary.

## Data handling
They ask where data lives and who can access it. All production data is in one region. Two engineers have production access, protected by hardware keys. Wayne's legal team also wants the retention policy in writing; it is ninety days after contract end.""", days=24)

# ================================================================== work / meetings
add("work/meetings", "Meeting notes, Monday: Priya will book the November offsite venue by Friday. Sam will send the renewal deck to Acme. Everyone reviews the Q4 plan before Thursday.", days=7, id="n4")
add("work/meetings", "Meeting notes, Wednesday: Lee agreed to fix the onboarding checklist this week. Maria will call Globex about their budget.", days=5, id="n5")
add("work/meetings", "Meeting notes, Friday: Planning moved to next week. Sam owns the security questionnaire for Initech.", days=3)
add("work/meetings", "Meeting notes, last Tuesday: We decided not to discount Acme before the call. Priya will prepare two options.", days=14)
add("work/meetings", "Product sync, October 8: the export feature slips to November. Dev will ship the bug fixes first. Nobody objected. Lee will tell Umbrella.", days=12)
add("work/meetings", "Board prep, October 1: Linh presents revenue and churn. Churn is 2.1 percent monthly, higher than the 1.5 percent target. Action: Priya to list the three accounts most likely to churn.", days=19)
add("work/meetings", "One-on-one with Sam, September 28: Sam feels overloaded by questionnaires. We agreed to write answer templates so each questionnaire takes two days, not nine.", days=22)
add("work/meetings", "Customer call with Hooli, September 25: they want a case study and a referral discount. I said we would think about the discount. Priya will follow up.", days=25)
add("work/meetings", "All-hands, September 15: offsite is in Santa Fe on November 14 to 16. Everyone books flights by October 25. Dietary needs go to Lee.", days=35)
add("work/meetings", "Retro, September 10: what went well was the onboarding fix. What did not was the late security questionnaire. Action: Sam creates the template library by October 15.", days=40)
long("work/meetings", """# Weekly log, week of October 12

## Monday
Standup. Dev reports the export bug is fixed in staging. Support has 14 open tickets, none urgent. Linh asks Priya for the Acme options by Thursday. Sam says the Initech questionnaire is half done.

## Tuesday
Customer call with Wayne Corp. Lee Chen asks for a price hold and a vendor review in November. Linh says yes to the review and will think about the price hold. Action: Linh to decide on the price hold by October 20. Dev asks for a code freeze on Friday; agreed.

## Wednesday
Planning for the offsite. Budget 14,000 for twenty people, flights not included. Priya proposes Santa Fe; Lee prefers Austin to save travel. Vote: Santa Fe wins 4 to 2. Action: Priya books the venue by Friday.

## Thursday
Acme options reviewed. Priya prefers the two-year deal; Sam prefers the smaller plan. Linh decides to offer both and let Maria choose. Action: Priya to send both quotes by Friday.

## Friday
Code freeze for the weekend. Support handoff to Lee, who covers while Sam is on leave. Reminder: Sam is on leave from the 3rd to the 17th of next month.""", days=2)

# ================================================================== work / team and process
add("work/team", "Team offsite planned for November. Sales and support will travel together.", days=30, id="n2")
add("work/team", "Offsite budget approved: 14,000 for twenty people, flights not included.", days=27)
add("work/team", "Support lead Sam is on leave from the 3rd to the 17th; Lee covers the queue.", days=10)
add("work/team", "Support handoff checklist: open tickets, customers waiting on us, anything promised for the week. Written by Lee, reviewed by Sam.", days=60)
add("work/team", "Working hours: core hours are 10 to 3 Central. Meetings only inside core hours. Dev may ship after 3 on Tuesdays and Thursdays.", days=200)
add("work/team", "Team birthdays: Priya in January, Sam in April, Lee in July, Dev in November. Bring cake, not a card.", days=150)
add("work/process", "Release process: tag on main, run the smoke test, deploy to staging, wait one hour, deploy to production. Never deploy on Fridays.", days=90)
add("work/process", "Incident process: whoever sees it says so in the incidents channel, Lee is incident lead by default, write the timeline while it happens.", days=95)
add("work/process", "Customer discount policy: up to 10 percent for two-year deals, up to 5 percent for annual prepay. Anything else needs Linh.", days=70)
add("work/process", "Refund policy: full refund within 30 days, prorated after that. Healthcare customers follow their own contract.", days=88)

# ================================================================== work / product
long("work/product/roadmap", """# Product roadmap, Q4 and Q1

## Q4: stabilise
Fix the export bug, ship the onboarding checklist, and cut the dashboard load time from six seconds to under two. These are the three things customers complain about most, and each one is tied to a renewal at risk. Export is needed by Umbrella. The onboarding checklist is what Initech asked for. Dashboard speed was Acme's complaint in the last review.

## Q1: grow
Single sign-on, a weekly digest email that lists accounts whose usage dropped more than twenty percent, and a read-only plan for executives. Single sign-on is requested by Umbrella and Wayne Corp. The digest email is an idea from Linh and has never been tested with customers. The read-only plan would have kept Globex.

## Not now
A mobile app, an API for partners, and a marketplace of templates. All three are interesting and all three would pull the team away from the renewals. Revisit in the summer.

## Risks
Dev is two people. If one is out, the plan slips by a quarter. The export fix depends on a database migration that nobody has done before.""", days=21)
add("work/product/requests", "Feature request from Umbrella: export all data as CSV for audits. Needs the signed addendum first.", days=30)
add("work/product/requests", "Feature request from Wayne Corp: single sign-on with their identity provider, required for the vendor review next year.", days=45)
add("work/product/requests", "Feature request from Initech: one consolidated invoice for four subsidiaries.", days=11)
add("work/product/bugs", "Bug: the export button times out for accounts with more than 50,000 rows. Workaround: ask support to run it overnight.", days=19)
add("work/product/bugs", "Bug: dashboards show the previous day's numbers until noon on Mondays. Cause: a timezone mismatch in the nightly job.", days=33)
add("work/product/bugs", "Bug fixed last week: duplicate emails on password reset. Released in version 4.12.", days=8)

# ================================================================== work / marketing, legal, hiring, hr
add("work/marketing", "Blog post idea: what we learned from cutting onboarding from three weeks to four days.", days=40)
add("work/marketing", "Webinar in November: churn early warning signs, with a guest from Hooli if legal approves the case study.", days=15)
add("work/marketing", "LinkedIn post that did well: a screenshot of the weekly digest idea with the line 'which accounts quietly stopped using your product?'. 41 reactions.", days=26)
add("work/legal", "NDA with Hooli signed on September 2, valid for three years. Copy is in the legal folder.", days=48)
add("work/legal", "The Umbrella addendum is still unsigned. Their lawyer asked to change clause 7 about subprocessors. Linh is reviewing.", days=17)
long("work/legal", """# Contract summary: Wayne Corp master agreement

The agreement runs for three years from January 2025 with automatic one-year renewals. Either side may end it with ninety days' notice before a renewal date.

## Price
Fixed per seat for the first two years. In year three the price may rise by at most five percent. Wayne has asked for a price hold for a fourth year.

## Service levels
Ninety-nine point five percent monthly availability. If we miss it, Wayne gets a credit of ten percent of the monthly fee per half point missed, capped at thirty percent.

## Data
Wayne owns its data. We delete it ninety days after the contract ends and certify the deletion in writing on request. Subprocessors must be listed and any change needs thirty days' notice.

## Liability
Capped at twelve months of fees, except for data breaches caused by gross negligence, which are uncapped. This clause was negotiated hard by both sides and should not be reopened lightly.""", days=60)
add("work/hiring", "Candidate: Rin Okada, backend engineer, strong on databases, wants a remote contract. Interview on Thursday with Dev.", days=10, level="high")
add("work/hiring", "Candidate: Marcus Webb, support specialist, good references from a bank. Salary expectation above our band.", days=22, level="high")
add("work/hiring", "Hiring plan: one engineer in Q1, one support person in Q2, only if two renewals close.", days=40)
add("work/hr", "Salary table for every employee. Strictly confidential.", days=100, level="high", id="n3")
add("work/hr", "Performance review drafts for the support team. Do not share.", days=70, level="high")
add("work/hr", "Priya asked for a raise; compare with the salary table before the budget meeting.", days=9, level="high")

# ================================================================== people
add("people/customers", "Maria Lopez, head of sales at Acme, prefers email on Mondays.", days=100, kind="contact", id="c1")
add("people/customers", "Dana Whitfield, former product owner at Globex, now at a competitor; still friendly.", days=34, kind="contact")
add("people/customers", "Priya Nair, head of sales at Hooli, prefers calls on Fridays.", days=80, kind="contact")
add("people/customers", "Lee Chen, procurement lead at Wayne Corp. Formal, wants everything in writing; replies within a day.", days=45, kind="contact")
add("people/customers", "Bill Lumbergh, new CTO at Initech since September. Wants one invoice for all subsidiaries.", days=11, kind="contact")
add("people/customers", "Dr. Alma Reyes, data protection officer at Umbrella. The person who must sign the addendum.", days=30, kind="contact")
add("people/team", "Priya Shah, our head of customer success. Not the same person as Priya Nair at Hooli. Birthday in January.", days=150, kind="contact")
add("people/team", "Sam Ortiz, support lead. Best at writing answers to security questionnaires.", days=150, kind="contact")
add("people/team", "Lee Park, support and operations. Not related to Lee Chen at Wayne Corp. Covers the queue when Sam is out.", days=150, kind="contact")
add("people/team", "Dev Kapoor, one of the two engineers. Prefers written requests over meetings.", days=150, kind="contact")
add("people/advisors", "Dr. Nguyen, our accountant. Prepares the revenue statements for vendor reviews. Needs a week's notice.", days=120, kind="contact")
add("people/advisors", "Jordan Blake, lawyer for contracts. Bills in six-minute units; email first, call only for emergencies.", days=120, kind="contact")
add("people/friends", "Tomás from university, lives in Lisbon, loves hiking and bad puns.", days=300, kind="contact")
add("people/friends", "Hana, runs a ceramics studio in East Austin; wants help with her shop's bookkeeping spreadsheet.", days=60, kind="contact")
add("people/friends", "Marcus from the running club. Training for the Austin half marathon in February.", days=45, kind="contact")
add("people/family", "Mum's birthday is on March 3rd; she likes tulips and anything from the bakery on Elm Street.", days=200, kind="contact")
add("people/family", "My brother Khoa lives in San Jose. His daughter is called Mai and she starts school next year.", days=180, kind="contact")
add("people/family", "Grandma lives in Da Nang; call on Sunday mornings, it is evening there.", days=90, kind="contact")

# ================================================================== family (shelves inside shelves, and a long note)
add("family/mum", "Mum likes tulips and anything from the bakery on Elm Street. Her birthday is on March 3rd.", days=190)
add("family/mum", "Mum's knees hurt on long walks; do not suggest anything over an hour on foot.", days=75)
add("family/mum", "Mum wants to learn video calls so she can talk to Grandma every week.", days=40)
add("family/grandma", "Grandma lives in Da Nang. Call on Sunday mornings, because it is evening there. She likes hearing about work.", days=88)
add("family/grandma", "Her best dish is fish noodle soup. Write the recipe down before she forgets it.", days=250)
add("family/trip home", "Planning to fly home in February: round trip is about 1,450 dollars, two weeks. Renew the passport before December.", days=16)
long("family/trip home", """# Plan for the February trip home

## Dates
Fly from Austin through Seoul to Da Nang on February 8 and come back on February 22. Two weeks is enough to see Grandma, spend a day in Hoi An and meet old friends in Saigon.

## Before leaving
Renew the passport before December because the current one expires soon. Change some cash. Buy gifts for Grandma: joint supplements and a warm cardigan. Tell customers that the last week of the trip is remote work.

## Work while away
Sam and Lee keep the support queue. Priya takes the customer calls. Check email only in the morning local time. For any major incident, call the local number.""", days=14)
add("family/learning", "New words this week: renew, budget, customer. Practise them in the meeting with Priya for fun.", days=6)

# ================================================================== personal
add("personal/health", "Dentist appointment on Tuesday at 9:30. Bring the insurance card.", days=5)
add("personal/health", "Doctor said to walk thirty minutes a day and cut down on coffee after lunch.", days=45)
add("personal/health", "Blood test in January showed vitamin D slightly low. Take 2000 IU a day through winter.", days=280, level="high")
add("personal/health", "Therapy on Thursday evenings at 6, every two weeks. Do not schedule meetings then.", days=60, level="high")
add("personal/health", "Half marathon training plan: three runs a week, long run on Sunday, add one mile every week until ten miles.", days=20)
long("personal/travel", """# Lisbon trip notes

Flight lands at 9:40 on November 20. Take the metro red line to Alameda, then the green line to Baixa. The hotel is a ten minute walk from there, on a steep street, so pack light.

## Food
Tomás recommends the small place near Alfama for grilled fish, and a bakery on the way to the castle for pastel de nata in the morning. Reserve dinner for Friday, the restaurants fill up fast.

## Things to remember
Bring the adapter and a rain jacket. The tram 28 is crowded, walk instead. Buy the transport card at the airport, it works on trams and the metro. Call the dentist before leaving to move the appointment to the week after the trip.""", days=12)
add("personal/travel", "Flight to Lisbon on November 20, seat 14C, returning the 27th. Hotel near Alfama is booked.", days=12)
add("personal/travel", "Santa Fe offsite, November 14 to 16: drive with Priya and Sam, leave Austin at 7am, hotel booked by the company.", days=17)
add("personal/travel", "Packing list for Lisbon: adapter, rain jacket, the good walking shoes.", days=11)
add("personal/home", "The landlord will fix the boiler on Thursday between 10 and 12.", days=4)
add("personal/home", "Wi-Fi router replaced in August; the admin password is on the sticker, but change it. Internet plan renews in March.", days=60, level="high")
add("personal/home", "Lease ends in July. Landlord said rent goes up about four percent. Decide by April whether to renew.", days=100)
add("personal/documents", "Passport number and the locker code for the safe deposit box.", days=250, level="high")
add("personal/documents", "Passport expires in March; renewal takes eight weeks, so apply before December.", days=30)
add("personal/documents", "Driver's licence renewal due in August. Social security number is in the safe, not in this app.", days=130, level="high")
long("personal/journal", """# Journal, October 14

Today I realised that most of what stresses me is not the work, it is the waiting. Waiting for Globex to answer, waiting for the lawyer, waiting for the vitamin D to do anything. When I wrote the three open loops down they looked small.

I was short with Sam this morning about the questionnaire and apologised at lunch. He said he feels like the only person who can write them, which is exactly the problem I should fix, not him. Templates are the answer. I will block Friday afternoon for it.

In the evening I called Mum. She asked when I am coming home. I said February. She was quiet for a while and then asked whether I would bring Khoa's daughter a book. I want to find a good Vietnamese picture book in Austin, if there is one.

Private thought, not for anyone: I am worried that the company is too dependent on two or three renewals, and I do not know how to say it to the team without sounding afraid. Maybe I should say it exactly like that.""", days=6, level="high")
add("personal/learning", "Learning Spanish for the Lisbon trip? No: Portuguese. Duolingo streak is 23 days; goal is to order dinner without English.", days=19)
add("personal/learning", "Reading list for winter: finish the book about pricing, start the one about negotiating. One chapter a day.", days=30)

# ================================================================== money (secret)
add("money", "Bank account 000111222, balance 91000 USD, routing 021000021.", days=3, kind="finance", level="high", id="f1")
add("money", "Monthly budget: rent 1800, food 600, travel 300, savings 700.", days=70, kind="finance", level="high")
add("money", "Quarterly tax estimate is due on January 15. Dr. Nguyen says set aside 28 percent of net.", days=25, kind="finance", level="high")
add("money", "Credit card ends 4417, limit 15000. Pay in full on the 27th.", days=90, kind="finance", level="high")
add("money/investments", "Index fund balance about 62000. Contribute 500 a month on the first. Do not sell during a downturn.", days=40, kind="finance", level="high")
add("money/receipts", "Coffee budget is 40 a month; I spent 63 last month, mostly on client meetings.", days=14, kind="finance")
add("money/receipts", "Software subscriptions total 312 a month: analytics, design tool, password manager, two chat apps.", days=33, kind="finance")

# ================================================================== projects: this hackathon
add("projects/hackathon", "Nebius x NVIDIA hackathon: submission deadline October 30, 10:00 Pacific. Submit by October 29 to be safe.", days=3)
add("projects/hackathon", "PayPal AI hackathon: deadline November 12 at noon Pacific. Submit by November 11. Needs a three minute demo video.", days=3)
add("projects/hackathon", "Decision: helpers run on the buyer's machine (pull mode). The helper sees only the shelves the buyer opens; secret files never leave.", days=9)
add("projects/hackathon", "Decision: payments are test money first, PayPal sandbox second. Never imply real money in the demo.", days=8)
add("projects/hackathon", "Open question: which model do we use for the live demo? Nemotron on Nebius is the plan; keep the thinking mode off for speed.", days=7)
long("projects/hackathon", """# Architecture notes, pull mode

## The idea
A helper is a short workflow: read some of the buyer's notes, think, check, hand over. In pull mode the workflow runs on the buyer's computer, not the author's. The author never sees the buyer's data. The buyer sees exactly what the helper was given.

## The guard
Every answer passes a guard before it reaches the buyer. The guard checks the shape of the answer, its size, whether it copies a decoy file, and whether it repeats a long run of a private note word for word. A helper that fails any of these is stopped, nothing is delivered, and the buyer is not charged.

## Memory
The buyer's notes live on shelves. A chat opens some shelves and the helper can only search inside those. Secret notes never leave, even if the buyer ticks them. Long notes are stored as passages so the helper reads only the part that matters.

## Money
The buyer places a hold when hiring. After an answer, a floor fee is captured. The rest is captured when the buyer keeps chatting or accepts the answer, and refunded if the answer was marked not helpful. A helper caught cheating earns nothing and the hold is released.""", days=5)

# ================================================================== reading, recipes, ideas
long("reading/books", """# Notes on the pricing book

The main claim is that price is the strongest lever a small software company has, and that most founders set it once and never look again. A one percent improvement in price gives more profit than a one percent improvement in volume or cost.

## Three ideas to try
First, offer three plans, not one, and make the middle one the obvious choice. Second, tie the price to something the customer values, like the number of accounts monitored, not to seats. Third, raise prices on new customers before existing ones, and watch what happens to the close rate.

## What I disagree with
The book assumes customers compare prices. Ours compare us with doing it in a spreadsheet, and the spreadsheet is free. The right comparison is the cost of a missed churn warning, not the price of other tools.""", days=50)
add("reading/articles", "Article: why customer success should own renewals, not sales. Key line: the person who answers the support tickets knows who is unhappy first.", days=35)
add("reading/articles", "Article about monthly churn benchmarks for B2B software: under 1 percent is excellent, 2 percent is common, above 3 percent is a warning.", days=28)
add("recipes", "Grilled pork with noodles (bun cha): grill pork patties and belly with fish sauce, sugar, garlic, shallots; serve with rice noodles, herbs, and a dipping sauce of fish sauce, lime, sugar, chili.", days=140)
add("recipes", "Beef noodle soup (pho) broth: char onion and ginger, simmer beef bones for six hours with star anise, cinnamon, cloves, coriander seed. Skim often.", days=160)
add("recipes", "Weeknight dinner: lemongrass chicken, rice, a bag of salad. Twenty minutes, one pan.", days=21)
add("recipes", "Dipping sauce: 3 spoons fish sauce, 2 spoons sugar, 1 spoon lime juice, minced garlic and chili, half a cup of warm water.", days=100)
add("ideas/product", "Idea: let customers see a one-page health score for their own account.", days=40)
add("ideas/product", "Idea: a weekly digest that lists accounts whose usage dropped more than twenty percent.", days=26)
add("ideas/product", "Idea: show a renewal countdown on every account page, with the three open risks next to it.", days=9)
add("ideas/writing", "Blog post idea: what we learned from cutting onboarding from three weeks to four days.", days=40)
add("ideas/writing", "Short book idea: 'The renewal calendar', one chapter per month of the year, for founders of small software companies.", days=170)

# ================================================================== an uneven tree: some subjects go many levels down, most do not
DEEP = "work/accounts/acme/2026/q4/renewal/pricing/discounts"
add(DEEP, "Acme discount approvals: anything above ten percent needs Linh's sign-off, and anything above fifteen needs the board.", days=6)
add(DEEP + "/approved", "Approved on October 14: twelve percent for Acme on a two-year term, signed by Linh. Valid until the renewal date.", days=7)
add(DEEP + "/approved/conditions", "Condition on the twelve percent: Acme must pay annually up front and agree to be a reference customer.", days=7)
add("work/accounts/acme/2026/q4/renewal/legal", "Acme legal asked to change the data-processing clause. Our lawyer says the change is fine if the deletion window stays at thirty days.", days=5)
add("work/accounts/acme/2026/q4/renewal", "Acme renewal plan: price hold agreed, legal review in progress, signature expected before December 1.", days=4)
add("work/accounts/acme/2026/q3", "Q3 review with Acme: usage grew eighteen percent; two open support tickets about exports.", days=60)
add("work/accounts/acme/2025", "Acme first year: signed in November 2025, pilot with the sales team, expanded to support in the spring.", days=300)
add("projects/hackathon/nebius/demo/script/scene-two", "Scene two of the demo: tick the Work shelf, ask about Acme, and point at the opened shelves under the answer.", days=2)
add("family/mum/recipes/soups/pho/broth", "Mum's pho broth: add a piece of rock sugar at the end and let it rest for ten minutes before serving.", days=90)

out = Path(__file__).with_name("vault-library.json")
out.write_text(json.dumps(R, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
docs = {r["doc"] for r in R if r.get("doc")}
print(f"wrote {len(R)} records ({len(R) - sum(1 for r in R if r.get('doc')) + len(docs)} notes, {len(docs)} long) to {out.name}")
