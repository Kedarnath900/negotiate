import json
import math
import re
import pandas as pd
from pathlib import Path

DEFAULT_PLAYBOOK = {
 "currency":"INR",
 "price":{"target_tolerance_pct":2.0,"counter_max_pct":10.0,"reject_above_pct":25.0},
 "delivery":{"max_days":20,"counter_max_extra_days":10},
 "payment":{"minimum_days":30,"advance_payment_allowed":False},
 "risk":{"escalate_if_missing_fields":True,"escalate_if_advance_requested":True},
 "approval":{"human_approval_required":True}
}

def load_playbook():
    path = Path(__file__).resolve().parent / "data" / "acme_playbook.json"
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                merged = json.loads(json.dumps(DEFAULT_PLAYBOOK))
                for section in ("price", "delivery", "payment", "risk", "approval"):
                    if isinstance(loaded.get(section), dict):
                        merged[section].update(loaded[section])
                for key in ("currency",):
                    if key in loaded:
                        merged[key] = loaded[key]
                return merged
        except (OSError, json.JSONDecodeError):
            pass
    return DEFAULT_PLAYBOOK

def validate_playbook(playbook):
    issues = []
    if not isinstance(playbook, dict):
        return ["Playbook must be a JSON object."]

    rules = {
        ("price", "target_tolerance_pct"): (0, None),
        ("price", "counter_max_pct"): (0, None),
        ("price", "reject_above_pct"): (0, None),
        ("delivery", "max_days"): (0, None),
        ("delivery", "counter_max_extra_days"): (0, None),
        ("payment", "minimum_days"): (0, None),
    }
    for (section, key), (minimum, maximum) in rules.items():
        value = playbook.get(section, {}).get(key) if isinstance(playbook.get(section), dict) else None
        number = _number({key: value}, key)
        if number is None or number < minimum or (maximum is not None and number > maximum):
            issues.append(f"{section}.{key} must be a number >= {minimum}.")
    return issues

def _number(d,k,default=None):
    try:
        value = float(d.get(k,default))
        return value if math.isfinite(value) else default
    except (TypeError,ValueError):
        return default

def analyze_proposal(p, playbook, _history):
    del _history
    if not isinstance(p, dict):
        p = {}
    if not isinstance(playbook, dict):
        playbook = DEFAULT_PLAYBOOK

    price_config = playbook.get("price", {})
    delivery_config = playbook.get("delivery", {})
    payment_config = playbook.get("payment", {})
    risk_config = playbook.get("risk", {})
    risk_config = risk_config if isinstance(risk_config, dict) else {}
    price_config = price_config if isinstance(price_config, dict) else {}
    delivery_config = delivery_config if isinstance(delivery_config, dict) else {}
    payment_config = payment_config if isinstance(payment_config, dict) else {}
    target_tolerance = _number(price_config, "target_tolerance_pct", 2.0)
    counter_max = _number(price_config, "counter_max_pct", 10.0)
    reject_above = _number(price_config, "reject_above_pct", 25.0)
    configured_max_delivery = _number(delivery_config, "max_days", 20)
    counter_extra_days = _number(delivery_config, "counter_max_extra_days", 10)
    configured_min_payment = _number(payment_config, "minimum_days", 30)
    advance_allowed = payment_config.get("advance_payment_allowed", False)
    escalate_missing = risk_config.get("escalate_if_missing_fields", True)
    escalate_advance = risk_config.get("escalate_if_advance_requested", True)

    price=_number(p,"quoted_price")
    target=_number(p,"target_price")
    delivery=_number(p,"delivery_days")
    max_delivery=_number(p,"max_delivery_days",configured_max_delivery)
    payment=_number(p,"payment_days")
    min_payment=_number(p,"min_payment_days",configured_min_payment)
    required=["supplier","quoted_price","target_price","delivery_days","payment_days"]
    missing=[k for k in required if p.get(k) in (None,"")]
    invalid=[]
    if price is None or price < 0:
        invalid.append("quoted_price")
    if target is None or target <= 0:
        invalid.append("target_price")
    if delivery is None or delivery < 0:
        invalid.append("delivery_days")
    if max_delivery is None or max_delivery < 0:
        invalid.append("max_delivery_days")
    if payment is None or payment < 0:
        invalid.append("payment_days")
    if min_payment is None or min_payment < 0:
        invalid.append("min_payment_days")
    notes=str(p.get("notes","")).lower()
    advance=bool(re.search(r"\b(advance|upfront|prepay|pre-payment)\b",notes))
    reasons=[]
    checks=[]
    if missing:
        reasons.append("Required fields are missing: "+", ".join(missing)+".")
        checks.append(False)
    else: checks.append(True)
    if invalid:
        reasons.append("Invalid numeric fields: "+", ".join(invalid)+".")
        checks.append(False)
    else:
        checks.append(True)
    if not price or not target or target<=0:
        variance=0
        reasons.append("Price or target is invalid; a reliable price comparison cannot be made.")
        checks.append(False)
    else:
        variance=(price-target)/target*100
        checks.append(variance <= target_tolerance)
        if variance <= target_tolerance:
            reasons.append("Quoted price is within Acme's configured target tolerance.")
        else:
            reasons.append(f"Quoted price is {variance:.1f}% above Acme's target.")
    checks.append(delivery is not None and max_delivery is not None and delivery>=0 and max_delivery>=0 and delivery<=max_delivery)
    if delivery is not None and max_delivery is not None and delivery>=0 and max_delivery>=0 and delivery>max_delivery:
        reasons.append(f"Delivery is {delivery:.0f} days, exceeding the {max_delivery:.0f}-day limit.")
    else: reasons.append("Delivery meets the configured limit.")
    checks.append(payment is not None and min_payment is not None and payment>=0 and min_payment>=0 and payment>=min_payment)
    if payment is not None and min_payment is not None and payment>=0 and min_payment>=0 and payment<min_payment:
        reasons.append(f"Payment term is {payment:.0f} days; Acme requires at least {min_payment:.0f} days.")
    else: reasons.append("Payment term meets the configured minimum.")
    if advance:
        reasons.append("Proposal notes mention advance/upfront payment; verify this against policy.")
    # Conservative routing: uncertain data / advance / extreme price -> escalate or reject.
    if ((missing and escalate_missing) or invalid or price is None or target is None or
            (advance and escalate_advance and not advance_allowed)):
        decision="ESCALATE"
        next_action="Route to a procurement manager to resolve missing information or review the advance-payment request."
    elif variance > reject_above:
        decision="REJECT"
        next_action="Reject the current commercial offer or request a completely revised proposal."
    elif (variance <= target_tolerance and delivery<=max_delivery and payment>=min_payment):
        decision="ACCEPT"
        next_action="Recommend acceptance subject to human approval, supplier due diligence and contract review."
    elif variance <= counter_max and delivery <= max_delivery + counter_extra_days and payment >= min_payment:
        decision="COUNTER"
        next_action=f"Counter at or below ₹{target:,.0f} per unit and confirm delivery within {max_delivery} days."
    else:
        decision="ESCALATE"
        next_action="Escalate to the procurement lead because one or more terms fall outside the configured negotiation envelope."
    passed=sum(1 for x in checks if x)
    confidence=max(55,min(96,65+passed*7-(15 if missing else 0)-(10 if advance else 0)))
    counter=(f"Thank you for your proposal. To proceed, Acme would like to propose a unit price of ₹{target:,.0f}, "
             f"delivery within {max_delivery} days, and payment terms of at least {min_payment} days. "
             "Please confirm whether you can meet these terms. This draft is subject to internal approval.")
    return {"decision":decision,"confidence":confidence,"price_variance_pct":round(variance,2),
            "checks_passed":passed,"checks_total":len(checks),"reasons":reasons,
            "next_action":next_action,"counteroffer":counter}

def retrieve_similar(proposal, history, n=3):
    if history is None or len(history)==0: return []
    df=history.copy()
    target_cat=str(proposal.get("category","")).lower()
    if "category" in df.columns:
        same=df[df["category"].astype(str).str.lower()==target_cat]
        if len(same): df=same
    for col in ["quoted_price","target_price","delivery_days","payment_days"]:
        if col not in df.columns:
            df[col]=0
        df[col]=pd.to_numeric(df[col], errors="coerce").fillna(0)
    pprice=_number(proposal,"quoted_price",0) or 0
    ptarget=_number(proposal,"target_price",0) or 0
    df["_distance"]=(df["quoted_price"]-pprice).abs()/(pprice or 1)+(df["target_price"]-ptarget).abs()/(ptarget or 1)
    cols=[c for c in ["supplier","category","quoted_price","target_price","delivery_days","payment_days","outcome"] if c in df.columns]
    return df.sort_values("_distance").head(n)[cols].to_dict("records")
