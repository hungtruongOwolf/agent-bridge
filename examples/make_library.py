"""Writes examples/vault-library.json: a small library with shelves, to show the memory tree in a demo.

    python examples/make_library.py
    bridge serve --vault examples/vault-library.json --state .bridge-library

The records are invented. The first seven keep the ids of examples/vault.json so the sample helpers behave the same.
"""
import json
from pathlib import Path

R = []


def add(id, shelf, text, kind="note", level="low"):
    R.append({"id": id, "type": kind, "sensitivity": level, "text": text, "path": shelf})


# work / accounts
add("n1", "work/accounts", "Sales pipeline review: three large accounts (Acme, Globex, Initech) are at risk because their renewal budgets were cut this quarter.")
add("a1", "work/accounts/acme", "Acme: renewal call is booked for November 12. Maria wants to talk about a discount before signing.")
add("a2", "work/accounts/acme", "Acme pays in euros and wants invoices sent on the first of the month.")
add("a3", "work/accounts/acme", "Acme expanded to a second office in Lisbon, which could mean more seats next year.")
add("g1", "work/accounts/globex", "Globex froze hiring and cut its tools budget by thirty percent, so the renewal is at risk.")
add("g2", "work/accounts/globex", "Globex champion Dana Whitfield left in September; nobody new owns the relationship yet.")
add("i1", "work/accounts/initech", "Initech asked for a security questionnaire before they will renew. Due at the end of the month.")
add("i2", "work/accounts/initech", "Initech support tickets dropped by half after the onboarding fix, which is good news for the renewal.")
add("h1", "work/accounts/hooli", "Hooli renewed early for two years and asked for a case study.")
# work / team and meetings
add("n2", "work/team", "Team offsite planned for November. Sales and support will travel together.")
add("t1", "work/team", "Offsite budget approved: 14,000 for twenty people, flights not included.")
add("t2", "work/team", "Support lead Sam is on leave from the 3rd to the 17th; Lee covers the queue.")
add("n4", "work/meetings", "Meeting notes, Monday: Priya will book the November offsite venue by Friday. Sam will send the renewal deck to Acme. Everyone reviews the Q4 plan before Thursday.")
add("n5", "work/meetings", "Meeting notes, Wednesday: Lee agreed to fix the onboarding checklist this week. Maria will call Globex about their budget.")
add("m1", "work/meetings", "Meeting notes, Friday: Planning moved to next week. Sam owns the security questionnaire for Initech.")
add("m2", "work/meetings", "Meeting notes, last Tuesday: We decided not to discount Acme before the call. Priya will prepare two options.")
# work / hr (secret)
add("n3", "work/hr", "Salary table for every employee. Strictly confidential.", level="high")
add("hr2", "work/hr", "Performance review drafts for the support team. Do not share.", level="high")
# people
add("c1", "people/customers", "Maria Lopez, head of sales at Acme, prefers email on Mondays.", "contact")
add("c2", "people/customers", "Dana Whitfield, former product owner at Globex, now at a competitor; still friendly.", "contact")
add("c3", "people/customers", "Priya Nair, head of sales at Hooli, prefers calls on Fridays.", "contact")
add("c4", "people/friends", "Tomás from university, lives in Lisbon, loves hiking and bad puns.", "contact")
add("c5", "people/family", "Mum's birthday is on March 3rd; she likes tulips and anything from the bakery on Elm Street.", "contact")
# personal
add("p1", "personal/health", "Dentist appointment on Tuesday at 9:30. Bring the insurance card.")
add("p2", "personal/health", "Doctor said to walk thirty minutes a day and cut down on coffee after lunch.")
add("p3", "personal/travel", "Flight to Lisbon on November 20, seat 14C, returning the 27th. Hotel near Alfama is booked.")
add("p4", "personal/travel", "Packing list for Lisbon: adapter, rain jacket, the good walking shoes.")
add("p5", "personal/home", "The landlord will fix the boiler on Thursday between 10 and 12.")
add("s1", "personal/documents", "Passport number and the locker code for the safe deposit box.", level="high")
# ideas
add("d1", "ideas/product", "Idea: let customers see a one-page health score for their own account.")
add("d2", "ideas/product", "Idea: a weekly digest that lists accounts whose usage dropped more than twenty percent.")
add("d3", "ideas/writing", "Blog post idea: what we learned from cutting onboarding from three weeks to four days.")
# money (secret)
add("f1", "money", "Bank account 000111222, balance 91000 USD, routing 021000021.", "finance", "high")
add("f2", "money", "Monthly budget: rent 1800, food 600, travel 300, savings 700.", "finance", "high")

out = Path(__file__).with_name("vault-library.json")
out.write_text(json.dumps(R, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"wrote {len(R)} records to {out.name}")
