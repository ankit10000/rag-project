#!/usr/bin/env python3
"""Calculate a fail-closed Lightsail spending preflight; never creates resources.

Inputs are saved AWS GetBundles/GetAccountPlanState responses, not credentials.
The 730-hour monthly divisor is an estimate, not a quoted hourly tariff. The
reserve is retained, and neither a FREE plan nor a successful result upgrades an
account or authorizes additional services. AWS Budgets notifications are delayed
advisories; they are not a spending cap.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import json
from pathlib import Path


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_CEILING))


def number(value: object) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError("amounts must be finite and non-negative")
    return result


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def assess(bundle: dict, plan: dict, *, start: datetime, days: Decimal,
           reserve: Decimal = Decimal("10"), initial_allowance: Decimal = Decimal("100"),
           other_cost: Decimal = Decimal("0"), eligible: bool = False,
           hourly_usd: Decimal | None = None) -> dict:
    """No implied account mutation or claim that unknown taxes are covered."""
    blockers: list[str] = []
    if days <= 0 or reserve < Decimal("10") or initial_allowance > Decimal("100"):
        raise ValueError("positive duration, at least $10 reserve and at most $100 allowance required")
    monthly = number(bundle.get("price"))
    credits_info = plan.get("accountPlanRemainingCredits", {})
    if credits_info.get("unit") != "USD":
        raise ValueError("remaining credits must be denominated in USD")
    remaining = min(number(credits_info.get("amount")), initial_allowance)
    hours = days * Decimal("24")
    rate = hourly_usd if hourly_usd is not None else monthly / Decimal("730")
    compute = hours * rate
    total = compute + other_cost
    usable = max(Decimal("0"), remaining - reserve)
    end = start + timedelta(seconds=float(hours * Decimal("3600")))
    if not eligible:
        blockers.append("Lightsail credit and account eligibility have not been verified")
    if plan.get("accountPlanStatus") != "ACTIVE":
        blockers.append("account plan is not ACTIVE")
    if plan.get("accountPlanType") not in ("FREE", "PAID"):
        blockers.append("account plan type is unknown")
    expiry = plan.get("accountPlanExpirationDate")
    if not expiry or end > timestamp(expiry):
        blockers.append("planned operation extends beyond verified account/credit expiry")
    if bundle.get("isActive") is not True:
        blockers.append("selected regional bundle is not active")
    if number(bundle.get("ramSizeInGb")) != 4 or number(bundle.get("cpuCount")) != 2:
        blockers.append("only the authorized 4 GB / 2 vCPU bundle is permitted")
    if total > usable:
        blockers.append("estimated consumption exceeds remaining credits minus contingency")
    return {
        "status": "BUDGET_PREFLIGHT_PASS" if not blockers else "BUDGET_PREFLIGHT_BLOCKED",
        "bundle_id": bundle.get("bundleId"),
        "monthly_usd": money(monthly),
        "start_utc": start.isoformat(), "end_utc": end.isoformat(),
        "days": str(days), "hours": str(hours),
        "account_plan": plan.get("accountPlanType"),
        "remaining_credits_usd": money(remaining),
        "contingency_usd": money(reserve), "usable_credits_usd": money(usable),
        "compute_estimate_usd": money(compute), "other_consumption_usd": money(other_cost),
        "total_estimate_usd": money(total), "headroom_after_reserve_usd": money(usable - total),
        "rate_basis": "verified hourly input" if hourly_usd is not None else "monthly price / 730 hours (estimate)",
        "blockers": blockers,
        "limits": [
            "Taxes are not covered by promotional credits; billing jurisdiction must be checked separately.",
            "Transfer overage, extra services, Gemini billing and unattached static IPs are excluded unless supplied as other consumption.",
            "Stopped Lightsail instances remain billable; deleting disposable containers does not stop host charges.",
            "This calculation is not an automatic spending cap or deployment approval.",
        ],
    }


def budget_template(account_id: str, email: str, start: datetime, end: datetime) -> dict:
    if not (len(account_id) == 12 and account_id.isdigit() and "@" in email):
        raise ValueError("valid account ID and explicit notification email required")
    return {
        "AccountId": account_id,
        "Budget": {
            "BudgetName": "rag-demo-credit-window", "BudgetType": "COST", "TimeUnit": "CUSTOM",
            "TimePeriod": {"Start": start.isoformat(), "End": end.isoformat()},
            "BudgetLimit": {"Amount": "90", "Unit": "USD"},
            "CostTypes": {"IncludeCredit": False, "IncludeRefund": False, "IncludeTax": True},
        },
        "NotificationsWithSubscribers": [
            {"Notification": {"NotificationType": "ACTUAL", "ComparisonOperator": "GREATER_THAN",
                              "Threshold": threshold, "ThresholdType": "ABSOLUTE_VALUE"},
             "Subscribers": [{"SubscriptionType": "EMAIL", "Address": email}]}
            for threshold in (25, 50, 75, 90)
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundles", type=Path, required=True)
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--account-plan", type=Path, required=True)
    parser.add_argument("--start", default=datetime.now(timezone.utc).isoformat())
    parser.add_argument("--days", default="110")
    parser.add_argument("--reserve", default="10")
    parser.add_argument("--other-consumption", default="0")
    parser.add_argument("--hourly-usd")
    parser.add_argument("--eligibility-verified", action="store_true")
    parser.add_argument("--budget-email")
    parser.add_argument("--account-id")
    args = parser.parse_args()
    try:
        bundles = json.loads(args.bundles.read_text())
        bundle = next(row for row in bundles["bundles"] if row["bundleId"] == args.bundle_id)
        plan = json.loads(args.account_plan.read_text())
        start = timestamp(args.start)
        report = assess(bundle, plan, start=start, days=number(args.days), reserve=number(args.reserve),
                        other_cost=number(args.other_consumption), eligible=args.eligibility_verified,
                        hourly_usd=number(args.hourly_usd) if args.hourly_usd else None)
        if args.budget_email:
            report["budget_create_input"] = budget_template(args.account_id or "", args.budget_email,
                                                            start, timestamp(report["end_utc"]))
        print(json.dumps(report, indent=2))
        return 0 if report["status"] == "BUDGET_PREFLIGHT_PASS" else 2
    except (ValueError, TypeError, KeyError, StopIteration, InvalidOperation, OSError) as error:
        parser.error(f"invalid preflight input ({type(error).__name__})")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
