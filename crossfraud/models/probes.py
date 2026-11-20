"""Small out-of-template probe set for the messaging model.

These conversations were written by hand and do NOT come from the generator's templates. They are an
illustrative stress test (13 items), not a benchmark: too few to estimate any rate, but enough to show
whether a template-trained model transfers at all. Rule signals are reported next to the model score.
"""
from __future__ import annotations

PROBES = [
    {"name": "scam: payment + urgency + bad link (1 msg)", "label": 1,
     "conversation": "Hurry! Only 10 minutes left. Send Rs 4999 to quickcash77@ybl now and verify at http://claim-bonus.xyz/pay"},
    {"name": "scam: OTP request", "label": 1,
     "conversation": "Dear customer, your account is blocked. Please share the OTP you just received to verify immediately."},
    {"name": "scam: crypto paraphrase (3 msgs)", "label": 1,
     "conversation": [{"sender_id": "a", "message": "Brother I make 2 lakh monthly from crypto, join my signal group"},
                      {"sender_id": "b", "message": "how"},
                      {"sender_id": "a", "message": "send 3000 to rajesh.fx@oksbi to get entry, doubles in a week, trust me"}]},
    {"name": "scam: fake hotel-rating job", "label": 1,
     "conversation": "Earn 5k daily from home just by rating hotels on Google Maps. Registration fee Rs 500 to jobdesk9@paytm."},
    {"name": "scam: parcel customs fee", "label": 1,
     "conversation": "Your parcel is held at customs. Pay Rs 1850 clearance fee to customs.dept@okaxis within 2 hours or it will be returned."},
    {"name": "scam: bank KYC link", "label": 1,
     "conversation": "SBI YONO: your account will be blocked today. Update PAN now: http://sbi-kyc-update.top/login"},
    {"name": "normal: casual chat", "label": 0,
     "conversation": "Hey, are we still meeting for coffee tomorrow?"},
    {"name": "normal: urgent meeting", "label": 0,
     "conversation": "Urgent: the meeting is moved to 5 pm, please confirm ASAP"},
    {"name": "normal: bill split (2 msgs)", "label": 0,
     "conversation": [{"sender_id": "a", "message": "Dinner was great! Your share is Rs 450, UPI me at meera12@ybl"},
                      {"sender_id": "b", "message": "sending now"}]},
    {"name": "normal: bank OTP warning", "label": 0,
     "conversation": "Never share your OTP with anyone. This message is from your bank."},
    {"name": "normal: rent reminder", "label": 0,
     "conversation": "Rent reminder: please send Rs 12000 to landlord45@oksbi by tomorrow"},
    {"name": "normal: cab money back", "label": 0,
     "conversation": "Can you send the notes? Also pay me back Rs 200 for the cab, my UPI is rohit9@ybl"},
    {"name": "normal: cash on delivery", "label": 0,
     "conversation": "Your order 4521 is out for delivery. Keep Rs 599 ready for cash on delivery."},
]


def run_probes(model) -> dict:
    rows = []
    for p in PROBES:
        r = model.predict(p["conversation"], entity_id="probe")
        rows.append({"name": p["name"], "label": p["label"], "risk_score": r["risk_score"],
                     "predicted_class": r["predicted_class"], "risk_level": r["risk_level"],
                     "rule_signals": [s["name"] for s in r["signals"] if s["source"] == "rule"]})
    scam = [r for r in rows if r["label"] == 1]
    benign = [r for r in rows if r["label"] == 0]
    return {"note": "hand-written, out-of-template, illustrative only (13 items)",
            "scam_flagged_by_model": f"{sum(r['predicted_class'] for r in scam)}/{len(scam)}",
            "scam_with_any_rule_signal": f"{sum(bool(r['rule_signals']) for r in scam)}/{len(scam)}",
            "benign_flagged_by_model": f"{sum(r['predicted_class'] for r in benign)}/{len(benign)}",
            "items": rows}
