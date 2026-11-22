"""Australian & Global Payroll Consultant Engine for Hummingbird Business Centre.

Implements AU FY2025-26 Stage-3 resident PAYG withholding brackets, Medicare levy (2%),
statutory Superannuation Guarantee (12.0% from 1 Jul 2025), NES leave accruals,
overtime multipliers, STP Phase 2 disaggregation buckets, and pay-run compliance audits.
"""
from __future__ import annotations

from typing import Any

# Periods per year
PAY_PERIODS = {
    'weekly': 52.0,
    'fortnightly': 26.0,
    'monthly': 12.0,
    'annual': 1.0,
}

# Australian Stage-3 resident individual income tax brackets (FY2024-25 / FY2025-26+)
AU_RESIDENT_BRACKETS = (
    (18200.0, 0.00),
    (45000.0, 0.16),
    (135000.0, 0.30),
    (190000.0, 0.37),
    (float('inf'), 0.45),
)

DEFAULT_SG_RATE = 0.12          # 12.0% Superannuation Guarantee (effective 1 Jul 2025)
DEFAULT_MEDICARE_RATE = 0.02    # 2.0% Medicare levy
STANDARD_FULLTIME_HOURS_PW = 38.0


def annual_au_income_tax(annual_taxable: float, resident: bool = True) -> float:
    """Compute annual Australian income tax (rounded to cents)."""
    income = max(0.0, float(annual_taxable))
    if not resident:
        # Foreign resident flat bands: 30% up to 135k, 37% up to 190k, 45% above
        tax = 0.0
        for low, high, rate in ((0.0, 135000.0, 0.30), (135000.0, 190000.0, 0.37), (190000.0, float('inf'), 0.45)):
            if income > low:
                tax += (min(income, high) - low) * rate
        return round(tax, 2)

    tax = 0.0
    prev = 0.0
    for cap, rate in AU_RESIDENT_BRACKETS:
        if income <= prev:
            break
        slice_amt = min(income, cap) - prev
        tax += slice_amt * rate
        prev = cap
    return round(tax, 2)


def calculate_pay_run(payload: dict[str, Any]) -> dict[str, Any]:
    """Calculate a complete single-employee payslip, Superannuation, leave accruals, and STP Phase 2 buckets."""
    employee = str(payload.get('employee') or 'Employee').strip()
    frequency = str(payload.get('frequency') or 'fortnightly').strip().lower()
    if frequency not in PAY_PERIODS:
        raise ValueError(f'frequency must be one of {tuple(PAY_PERIODS.keys())}')
    periods = PAY_PERIODS[frequency]
    currency = str(payload.get('currency') or 'AUD').strip().upper()
    resident = bool(payload.get('resident', True))
    claim_threshold = bool(payload.get('claim_tax_free_threshold', True))
    sg_rate = float(payload.get('super_rate', DEFAULT_SG_RATE))
    if sg_rate < 0 or sg_rate > 0.5:
        raise ValueError('super_rate must be between 0.0 and 0.5')

    ordinary_hours = float(payload.get('ordinary_hours') or 0.0)
    hourly_rate = float(payload.get('hourly_rate') or 0.0)
    ot_15_hours = max(0.0, float(payload.get('overtime_15_hours') or 0.0))
    ot_20_hours = max(0.0, float(payload.get('overtime_20_hours') or 0.0))
    allowances = max(0.0, float(payload.get('allowances') or 0.0))
    salary_sacrifice = max(0.0, float(payload.get('salary_sacrifice') or 0.0))

    if payload.get('gross_period') is not None:
        ordinary_pay = max(0.0, float(payload['gross_period']))
    elif payload.get('annual_salary') is not None:
        ordinary_pay = max(0.0, float(payload['annual_salary']) / periods)
    else:
        ordinary_pay = max(0.0, ordinary_hours * hourly_rate)

    if hourly_rate <= 0 and ordinary_pay > 0:
        est_hours = STANDARD_FULLTIME_HOURS_PW * (52.0 / periods)
        hourly_rate = ordinary_pay / est_hours if est_hours else 0.0
        if ordinary_hours <= 0:
            ordinary_hours = est_hours

    overtime_pay = round((ot_15_hours * hourly_rate * 1.5) + (ot_20_hours * hourly_rate * 2.0), 2)
    ordinary_pay = round(ordinary_pay, 2)
    gross_pay = round(ordinary_pay + overtime_pay + allowances, 2)
    taxable_period = max(0.0, gross_pay - salary_sacrifice)

    # Annualize for PAYG withholding estimate
    annual_taxable = taxable_period * periods
    if resident and not claim_threshold:
        # No tax-free threshold: treat first $18,200 as taxed at 16%
        annual_tax = annual_au_income_tax(annual_taxable + 18200.0, resident=True)
    else:
        annual_tax = annual_au_income_tax(annual_taxable, resident=resident)

    medicare_annual = round(annual_taxable * DEFAULT_MEDICARE_RATE, 2) if (resident and annual_taxable > 26000.0) else 0.0
    payg_period = round(annual_tax / periods, 2)
    medicare_period = round(medicare_annual / periods, 2)
    total_tax = round(payg_period + medicare_period, 2)
    net_pay = round(max(0.0, gross_pay - salary_sacrifice - total_tax), 2)

    # Ordinary Time Earnings (OTE) excludes overtime for SG by ATO rule
    ote = round(ordinary_pay + allowances, 2)
    super_sg = round(ote * sg_rate, 2)
    total_super = round(super_sg + salary_sacrifice, 2)
    total_employer_cost = round(gross_pay + super_sg, 2)

    # NES leave accruals (full-time/pro-rata on ordinary hours: 4 wks annual = 4/52, 10 days personal = 2/52)
    annual_leave_hrs = round(ordinary_hours * (4.0 / 52.0), 3)
    personal_leave_hrs = round(ordinary_hours * (2.0 / 52.0), 3)

    return {
        'employee': employee,
        'frequency': frequency,
        'currency': currency,
        'resident': resident,
        'gross_pay': gross_pay,
        'ordinary_pay': ordinary_pay,
        'overtime_pay': overtime_pay,
        'allowances': round(allowances, 2),
        'salary_sacrifice': round(salary_sacrifice, 2),
        'payg_withholding': payg_period,
        'medicare_levy': medicare_period,
        'total_tax_withheld': total_tax,
        'net_pay': net_pay,
        'ote': ote,
        'super_rate': sg_rate,
        'superannuation_sg': super_sg,
        'superannuation_total': total_super,
        'total_employer_cost': total_employer_cost,
        'leave_accruals': {
            'annual_leave_hours': annual_leave_hrs,
            'personal_leave_hours': personal_leave_hrs,
        },
        'stp_phase2': {
            'gross_disaggregated': {
                'ordinary_time_earnings': ordinary_pay,
                'overtime': overtime_pay,
                'allowances': round(allowances, 2),
            },
            'salary_sacrifice_super': round(salary_sacrifice, 2),
            'super_liability': super_sg,
            'payg_withholding': total_tax,
            'checklist': [
                'Verify employee TFN declaration & tax-free threshold flag',
                'Confirm OTE excludes overtime hours for SG calculation',
                'Reconcile PAYG + Super clearing house batch before STP submit',
            ],
        },
    }


def audit_pay_run(payslips: list[dict[str, Any]], prior_total_gross: float | None = None) -> dict[str, Any]:
    """Run automated Payroll Consultant compliance & variance checks on a batch of payslips."""
    findings: list[dict[str, str]] = []
    total_gross = 0.0
    total_net = 0.0
    total_tax = 0.0
    total_super = 0.0

    for idx, slip in enumerate(payslips or []):
        emp = str(slip.get('employee') or f'Row {idx + 1}')
        gross = float(slip.get('gross_pay') or 0.0)
        net = float(slip.get('net_pay') or 0.0)
        tax = float(slip.get('total_tax_withheld') or slip.get('payg_withholding') or 0.0)
        ote = float(slip.get('ote') or slip.get('ordinary_pay') or gross)
        sg = float(slip.get('superannuation_sg') or 0.0)
        sg_rate = float(slip.get('super_rate') if slip.get('super_rate') is not None else DEFAULT_SG_RATE)

        total_gross += gross
        total_net += net
        total_tax += tax
        total_super += sg

        if gross <= 0:
            findings.append({'severity': 'error', 'employee': emp, 'issue': 'Gross pay is zero or negative.'})
        if net < 0:
            findings.append({'severity': 'error', 'employee': emp, 'issue': 'Net pay is negative — check deductions.'})
        if sg_rate < DEFAULT_SG_RATE - 1e-6:
            findings.append({'severity': 'warning', 'employee': emp, 'issue': f'Super rate {sg_rate*100:.2f}% is below statutory 12.0% SG.'})
        expected_sg = round(ote * DEFAULT_SG_RATE, 2)
        if ote > 0 and sg + 0.05 < expected_sg:
            findings.append({'severity': 'warning', 'employee': emp, 'issue': f'SG ${sg:.2f} below statutory 12% of OTE (${expected_sg:.2f}).'})
        if gross > 0 and tax > gross * 0.50:
            findings.append({'severity': 'warning', 'employee': emp, 'issue': 'Withholding exceeds 50% of gross pay — verify tax scale.'})

    variance_pct = None
    if prior_total_gross and prior_total_gross > 0:
        variance_pct = round(((total_gross - prior_total_gross) / prior_total_gross) * 100.0, 2)
        if abs(variance_pct) >= 15.0:
            findings.append({
                'severity': 'warning',
                'employee': 'BATCH',
                'issue': f'Total gross variance vs prior run is {variance_pct:+.2f}% (>=15% threshold).',
            })

    errors = sum(1 for f in findings if f['severity'] == 'error')
    warnings = sum(1 for f in findings if f['severity'] == 'warning')
    return {
        'ok': errors == 0,
        'status': 'FAIL' if errors else ('REVIEW' if warnings else 'PASS'),
        'employees_checked': len(payslips or []),
        'totals': {
            'gross_pay': round(total_gross, 2),
            'net_pay': round(total_net, 2),
            'tax_withheld': round(total_tax, 2),
            'superannuation_sg': round(total_super, 2),
        },
        'variance_pct': variance_pct,
        'findings': findings,
    }
