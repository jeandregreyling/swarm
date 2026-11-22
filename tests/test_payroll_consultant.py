"""Tests for Phase 3A Payroll Consultant Engine & Business Centre Payroll API."""
from __future__ import annotations

from pathlib import Path
import sqlite3

from core.payroll_consultant import annual_au_income_tax, audit_pay_run, calculate_pay_run


def test_au_stage3_tax_and_fortnightly_payslip():
    assert annual_au_income_tax(18200) == 0.0
    assert annual_au_income_tax(45000) == round((45000 - 18200) * 0.16, 2)
    slip = calculate_pay_run({
        'employee': 'Alex Rivera',
        'annual_salary': 104000,
        'frequency': 'fortnightly',
        'overtime_15_hours': 4.0,
    })
    assert slip['ordinary_pay'] == 4000.0
    assert slip['overtime_pay'] > 0
    assert slip['gross_pay'] == round(slip['ordinary_pay'] + slip['overtime_pay'], 2)
    # SG Super applies to OTE (ordinary_pay), NOT overtime
    assert slip['superannuation_sg'] == round(4000.0 * 0.12, 2)
    assert slip['net_pay'] == round(slip['gross_pay'] - slip['total_tax_withheld'], 2)
    assert slip['leave_accruals']['annual_leave_hours'] > 5.0
    assert len(slip['stp_phase2']['checklist']) >= 3


def test_payroll_audit_catches_underpaid_super_and_variance():
    good = calculate_pay_run({'employee': 'Good', 'annual_salary': 78000, 'frequency': 'fortnightly'})
    bad = calculate_pay_run({'employee': 'UnderSuper', 'annual_salary': 78000, 'frequency': 'fortnightly', 'super_rate': 0.09})
    report = audit_pay_run([good, bad], prior_total_gross=4000.0)
    assert report['status'] == 'REVIEW'
    issues = ' '.join(f['issue'] for f in report['findings'])
    assert 'below statutory 12.0% SG' in issues
    assert 'variance' in issues


def test_business_blueprint_payroll_endpoints(tmp_path: Path, monkeypatch):
    import frontend.blueprints.business_bp as bbp
    db_file = tmp_path / 'payroll_test.db'

    def _conn():
        c = sqlite3.connect(db_file)
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr(bbp, 'connect', _conn)
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(bbp.business_bp)
    client = app.test_client()

    r1 = client.post('/api/business/payroll/calculate', json={'employee': 'JD', 'annual_salary': 130000, 'frequency': 'monthly'})
    assert r1.status_code == 200 and r1.get_json()['ok'] is True

    r2 = client.post('/api/business/payroll/commit', json={'employee': 'JD', 'annual_salary': 130000, 'frequency': 'monthly'})
    assert r2.status_code == 201
    assert len(r2.get_json()['ledger_entry_ids']) == 2

    r3 = client.get('/api/business/entries?kind=payroll')
    assert r3.status_code == 200 and r3.get_json()['count'] == 2

    r4 = client.post('/api/business/payroll/audit', json={'payslips': [r1.get_json()['payslip']]})
    assert r4.status_code == 200 and r4.get_json()['audit']['status'] == 'PASS'
