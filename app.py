"""Credit Card Fraud Detection - Flask backend (JSON file storage)."""
import csv, io, json, threading, uuid
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, Response, jsonify, render_template, request

app = Flask(__name__)
DATA = Path(__file__).parent / "data"
CARDS_F, TXN_F = DATA / "cards.json", DATA / "transactions.json"
lock = threading.Lock()

DEFAULT_CARDS = [
    {"id": "c1", "holder": "Sami K", "last4": "4821", "home_country": "IN",
     "txn_limit": 25000, "daily_limit": 60000, "frozen": False},
    {"id": "c2", "holder": "Ananya R", "last4": "9033", "home_country": "IN",
     "txn_limit": 50000, "daily_limit": 100000, "frozen": False},
]
RISKY = {"crypto": 25, "gambling": 20, "wire_transfer": 25, "gift_cards": 20,
         "jewelry": 10, "electronics": 8}


def load(path, default):
    if not path.exists():
        save(path, default)
        return json.loads(json.dumps(default))
    return json.loads(path.read_text())


def save(path, data):
    DATA.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def parse(ts):
    return datetime.fromisoformat(ts)


def score(card, txns, t, now):
    """Return (risk 0-100, reasons, limit_breach)."""
    s, reasons, breach = 0, [], False
    amt = t["amount"]
    mine = [x for x in txns if x["card_id"] == card["id"] and x["status"] != "BLOCKED"]

    if card["frozen"]:
        return 100, ["Card is frozen"], False

    if amt > card["txn_limit"]:
        s += 40; breach = True
        reasons.append(f"Over per-transaction limit (₹{card['txn_limit']:,})")

    today = now.date().isoformat()
    spent = sum(x["amount"] for x in mine if x["time"][:10] == today)
    if spent + amt > card["daily_limit"]:
        s += 45; breach = True
        reasons.append(f"Daily limit breached (₹{spent + amt:,.0f} of ₹{card['daily_limit']:,})")

    recent = [x for x in mine if now - parse(x["time"]) <= timedelta(minutes=10)]
    if len(recent) >= 3:
        s += 25; reasons.append(f"{len(recent)} transactions in the last 10 minutes")

    if t["country"] != card["home_country"]:
        s += 20; reasons.append(f"Foreign country ({t['country']})")
        last = mine[-1] if mine else None
        if last and last["country"] != t["country"] and now - parse(last["time"]) < timedelta(hours=2):
            s += 25; reasons.append("Impossible travel: different country within 2 hours")

    if now.hour < 5:
        s += 10; reasons.append("Unusual hour (midnight to 5 AM)")

    if t["category"] in RISKY:
        s += RISKY[t["category"]]; reasons.append(f"High-risk category ({t['category'].replace('_', ' ')})")

    past = [x["amount"] for x in mine]
    if len(past) >= 3 and amt > 4 * (sum(past) / len(past)):
        s += 15; reasons.append("Amount is 4x higher than this card's average")

    return min(s, 100), reasons, breach


@app.route("/")
def index():
    return render_template("index.html")


@app.get("/api/cards")
def cards():
    cs, tx = load(CARDS_F, DEFAULT_CARDS), load(TXN_F, [])
    today = datetime.now().date().isoformat()
    for c in cs:
        c["spent_today"] = sum(x["amount"] for x in tx if x["card_id"] == c["id"]
                               and x["status"] != "BLOCKED" and x["time"][:10] == today)
    return jsonify(cs)


@app.post("/api/cards")
def add_card():
    d = request.get_json(force=True)
    try:
        card = {"id": "c" + uuid.uuid4().hex[:6], "holder": str(d["holder"])[:40],
                "last4": str(d["last4"])[-4:], "home_country": str(d.get("home_country", "IN")).upper()[:2],
                "txn_limit": float(d["txn_limit"]), "daily_limit": float(d["daily_limit"]), "frozen": False}
    except (KeyError, ValueError):
        return jsonify(error="Fill holder, last 4 digits and both limits"), 400
    with lock:
        cs = load(CARDS_F, DEFAULT_CARDS); cs.append(card); save(CARDS_F, cs)
    return jsonify(card), 201


@app.post("/api/cards/<cid>/toggle")
def toggle(cid):
    with lock:
        cs = load(CARDS_F, DEFAULT_CARDS)
        for c in cs:
            if c["id"] == cid:
                c["frozen"] = not c["frozen"]; save(CARDS_F, cs)
                return jsonify(c)
    return jsonify(error="Card not found"), 404


@app.post("/api/check")
def check():
    d = request.get_json(force=True)
    try:
        amount = float(d["amount"])
        assert amount > 0
    except (KeyError, ValueError, AssertionError):
        return jsonify(error="Enter a valid amount"), 400
    with lock:
        cs, tx = load(CARDS_F, DEFAULT_CARDS), load(TXN_F, [])
        card = next((c for c in cs if c["id"] == d.get("card_id")), None)
        if not card:
            return jsonify(error="Pick a card"), 400
        now = datetime.now()
        t = {"amount": amount, "merchant": str(d.get("merchant") or "Unknown")[:40],
             "category": d.get("category", "other"), "country": str(d.get("country", "IN")).upper()[:2]}
        risk, reasons, breach = score(card, tx, t, now)
        status = "BLOCKED" if risk >= 70 else "REVIEW" if risk >= 40 else "APPROVED"
        rec = {"id": uuid.uuid4().hex[:8], "card_id": card["id"], "card": f"{card['holder']} •••• {card['last4']}",
               **t, "time": now.isoformat(timespec="seconds"), "risk": risk, "status": status,
               "reasons": reasons, "limit_breach": breach}
        tx.append(rec); save(TXN_F, tx)
    return jsonify(rec)


@app.get("/api/transactions")
def transactions():
    tx = load(TXN_F, [])
    status = request.args.get("status")
    if status:
        tx = [x for x in tx if x["status"] == status.upper()]
    return jsonify(tx[::-1][:100])


@app.get("/api/stats")
def stats():
    tx = load(TXN_F, [])
    by = lambda s: [x for x in tx if x["status"] == s]
    return jsonify(total=len(tx), approved=len(by("APPROVED")), review=len(by("REVIEW")),
                   blocked=len(by("BLOCKED")), breaches=sum(x["limit_breach"] for x in tx),
                   amount_blocked=sum(x["amount"] for x in by("BLOCKED")))


@app.get("/api/export.csv")
def export():
    tx = load(TXN_F, [])
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["time", "card", "merchant", "category", "country", "amount", "risk", "status", "reasons"])
    for x in tx:
        w.writerow([x["time"], x["card"], x["merchant"], x["category"], x["country"],
                    x["amount"], x["risk"], x["status"], "; ".join(x["reasons"])])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=transactions.csv"})


@app.post("/api/reset")
def reset():
    with lock:
        save(CARDS_F, DEFAULT_CARDS); save(TXN_F, [])
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(debug=True)
