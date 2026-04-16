"""
lib/knowledge/seed.py — Built-in knowledge documents for the Library.

SAP Corner: Australia payroll, global payroll, ABAP, EC/ECP, schemas/PCRs,
            functions/operations, BAPIs, infotypes, wage types, features.
Programming: Python best practices, code review guidelines, testing strategies.

Each entry is a dict with: title, content, category, subcategory, tags.
Seeding is idempotent — check_duplicate() prevents re-adding same content.
"""

import logging
import threading

logger = logging.getLogger('seven.knowledge.seed')


# ════════════════════════════════════════════════════════════════════════════════
# SAP CORNER — Australia Payroll
# ════════════════════════════════════════════════════════════════════════════════

_SAP_PAYROLL_AU = [
    {
        'title': 'Australian Payroll Overview — Key Concepts',
        'subcategory': 'payroll_au',
        'tags': ['payroll', 'sap_hcm'],
        'content': """Australian SAP Payroll — Key Concepts

Payroll Area: A grouping of employees processed together. In Australia, commonly configured per pay frequency (weekly, fortnightly, monthly). Transaction PA03 manages payroll control records.

Pay Frequency: Australia commonly uses Weekly (01), Fortnightly (02), and Monthly (04). The payroll period parameter (ABKRS) determines which payroll area an employee belongs to.

Tax: PAYG (Pay As You Go) withholding. Tax scales are updated annually by the ATO. Infotype 0188 (Tax AU) stores tax file number (TFN), tax scale, HELP/SFSS debt indicators, tax offset claims, and Medicare levy variation. Tax-free threshold is claimed via the TFN declaration (NAT 3092).

Superannuation: Mandatory employer contributions (Super Guarantee). Current rate defined by legislation. IT0220 stores super fund details. Multiple funds supported via Superannuation Clearing House integration. Choice of fund compliance is required.

Leave: Annual Leave (4 weeks standard, loading varies by award/EBA), Personal/Carer's Leave (10 days), Long Service Leave (state-based — 10 years in most states, 7 years in some). Leave loading typically 17.5%. IT2001 (Absences) stores leave taken; IT2006 stores absence quotas.

Award Interpretation: Many Australian employees are covered by Modern Awards or Enterprise Bargaining Agreements (EBAs). SAP handles this through schemas, PCRs, and custom wage type logic. Common awards: Clerks Private Sector, Manufacturing, Health Professionals.""",
    },
    {
        'title': 'Australian Tax — PAYG and Tax Scales',
        'subcategory': 'payroll_au',
        'tags': ['payroll', 'sap_hcm', 'infotype'],
        'content': """Australian PAYG Withholding in SAP

Key Infotypes:
- IT0188 (Tax AU): TFN, tax scale, HELP/HECS indicator, SFSS indicator, tax-free threshold claimed, Medicare levy variation, tax offset amount.
- IT0588 (Superannuation AU): Fund details, membership number, contribution percentages.

Tax Scales:
- Scale 1: With tax-free threshold claimed (most common)
- Scale 2: No tax-free threshold — for second jobs or unclaimed
- Scale 3: Foreign residents
- Scale 4: TFN not provided (maximum rate 47%)
- Scale 5: Full exemption (rare, e.g. certain visa holders)
- Scale 6: Horticulture/shearing (seasonal workers)

HELP/HECS Debt: Additional withholding when income exceeds threshold. Stored as indicator on IT0188. Calculated as percentage of repayment income.

Medicare Levy: Standard 2% levy. Surcharge (1-1.5%) applies if no private health insurance above income threshold. Reduction/exemption available for low-income earners.

Processing: Tax calculation runs in payroll schema AU01 via function AUTAX (or equivalent). Tax rounding rules apply — round to whole dollar. End-of-year: Payment Summary (now STP — Single Touch Payroll) replaces group certificates.

STP Reporting: Single Touch Payroll is mandatory. Phase 1 covers gross, tax, super. Phase 2 adds income types (salary/wages, closely held, working holiday, etc.), country codes, and tax treatment codes. SAP delivers STP via standard BAdIs and program RPCSTPA0.""",
    },
    {
        'title': 'Australian Superannuation — Configuration & Processing',
        'subcategory': 'payroll_au',
        'tags': ['payroll', 'sap_hcm', 'infotype'],
        'content': """Superannuation in SAP (Australia)

Infotype 0220 (Superannuation AU):
- Stores fund SPIN/USI, membership number, contribution rates (employer/employee).
- Multiple records allowed for salary sacrifice + employer additional.
- Fund details maintained in V_T7AU40 (Super Fund table).

Infotype 0588 (Additional Super AU):
- Used for additional voluntary contributions, salary sacrifice arrangements.

Super Guarantee (SG):
- Employer must contribute SG rate (check current ATO rate) on Ordinary Time Earnings (OTE).
- OTE = base salary + allowances + commissions + bonuses + leave loading (generally).
- OTE excludes: overtime, reimbursements, lump sum termination payments.
- Maximum contribution base applies per quarter.

Salary Sacrifice:
- Pre-tax contributions reduce taxable income. Reported as Reportable Employer Super Contributions (RESC) on payment summary/STP.
- Configuration via wage type mapping to contribution type.

Super Clearing House:
- SAP generates SuperStream-compliant files for clearing house submission.
- Format: SAFF (Small Business) or proprietary clearing house format.
- Program RPCAUPA0 or custom ABAP for file generation.

Choice of Fund:
- Employees can nominate their own fund (Stapled Super Fund if no choice made — from Nov 2021).
- ATO Stapled Super Fund lookup via API integration.""",
    },
    {
        'title': 'Australian Leave — Annual, Personal, Long Service',
        'subcategory': 'payroll_au',
        'tags': ['payroll', 'sap_hcm'],
        'content': """Leave Management in Australian SAP Payroll

Annual Leave:
- Standard entitlement: 4 weeks (20 days) per year for full-time. Pro-rata for part-time.
- Shift workers may receive 5 weeks under certain awards.
- Leave loading: 17.5% typically. Some EBAs vary. Loading may be paid on accrual or on taking leave.
- Configuration: Absence type, counting rules, quota type, accrual rules (via RPTQTA00 or schema-based Time Evaluation).
- Annual leave cashed out: Limited conditions under NES (National Employment Standards) — employee must retain 4 weeks after cash-out.

Personal/Carer's Leave:
- 10 days per year, cumulative (no cap). Evidence required for 2+ consecutive days.
- Unpaid carer's leave: 2 days per occasion when paid leave exhausted.

Long Service Leave (LSL):
- State/territory based — varies significantly:
  - NSW: 2 months after 10 years, then pro-rata from 5 years on termination.
  - VIC: 8.6667 weeks after 10 years (effective rate).
  - QLD: 8.6667 weeks after 10 years.
  - SA: Similar to VIC.
  - WA: 8.6667 weeks after 10 years.
- Some awards/EBAs provide more generous LSL.
- SAP configuration: Different absence types per state, quota generation rules, state-based processing in schema.

Parental Leave:
- 12 months unpaid (NES minimum). Government Paid Parental Leave scheme separate from employer payroll but may be administered through employer.
- Keeping-in-touch days allowed.

Leave Provisioning:
- Crucial for balance sheet reporting. SAP provides standard leave provision reports (RPCPRWA0) or custom ABAP.
- Provision = leave balance × current rate (or projected rate for annual leave loading).""",
    },
]


# ════════════════════════════════════════════════════════════════════════════════
# SAP CORNER — Schemas & PCRs
# ════════════════════════════════════════════════════════════════════════════════

_SAP_SCHEMAS_PCR = [
    {
        'title': 'Payroll Schema Fundamentals — AU01 and Key Subschemas',
        'subcategory': 'schemas_pcr',
        'tags': ['schema', 'payroll'],
        'content': """Payroll Schema Fundamentals

The payroll schema is the central control program for payroll calculation. It defines the sequence of functions, operations, and PCRs that process employee data into payroll results.

AU01 — Australia Main Schema:
The top-level driver schema for Australian payroll. Calls subschemas for:
- Initialisation (XINI / AUI0)
- Gross calculation (AUGR / AUG0)
- Net calculation (AUNN / AUN0)
- Tax (AUTX)
- Superannuation
- Leave loading
- Deductions
- Bank transfers (AUBT)

Key Subschemas:
- XAUS — Australia-specific processing
- AUGR — Gross calculation (processes basic pay, allowances, overtime, deductions)
- AUNN — Net calculation (post-tax deductions, net pay)
- AUTX — Tax calculation (calls PAYG withholding logic)

Schema Structure:
Each line in a schema is: Function | Rule | Op | Variable | Condition
- Functions: Built-in SAP routines (WPBP, PIT, GRS, NET, etc.)
- Rules (PCRs): Custom processing logic created in PE02
- Operations: Low-level instructions within PCRs (ADDWT, MULTI, etc.)

Transaction PE01: Schema editor. PE02: PCR editor. PE03: Feature editor.

Processing Flow:
1. Initialisation → read master data, set period parameters
2. Gross calculation → process wage types, calculate amounts
3. Tax calculation → apply PAYG rules
4. Net calculation → deductions, super, net pay
5. Bank transfer → split net pay across bank accounts
6. Results storage → write to payroll cluster (PCL2)""",
    },
    {
        'title': 'PCR (Personnel Calculation Rule) Development',
        'subcategory': 'schemas_pcr',
        'tags': ['pcr', 'schema', 'payroll'],
        'content': """Personnel Calculation Rules (PCRs)

PCRs are custom rule programs written in transaction PE02. They contain decision logic and operations to process wage types and amounts during payroll.

Structure:
Each PCR line has:
- Variable key (left side) — condition to match
- Operation (right side) — action to execute

Variable Types:
- * — wildcard (always matches)
- Wage type (e.g., /001, M010)
- Infotype field value
- Constant or variable from payroll

Common Operations:
- ADDWT  : Add a wage type to the results table (IT/OT)
- MULTI  : Multiply current amount by a factor
- DIVID  : Divide current amount
- ROUND  : Round to specified precision
- AMT=   : Set amount directly
- NUM=   : Set number/rate
- RTE=   : Set rate
- Table  : Table lookup (e.g., T511K)
- VARC   : Check a variable condition
- GOTO   : Jump to a label/rule
- NEXTR  : Next rule (skip remaining lines)
- ZERO   : Zero out current amount

PCR Best Practices:
1. Keep rules short and focused — one rule per business concept.
2. Comment extensively — use //* lines for documentation.
3. Always handle the default/else case.
4. Test with PC_PAYRESULT and simulation (PC00_M13_CALC_SIMU).
5. Copy standard rules to Z-namespace before modifying.
6. Document in a PCR catalogue (maintain a cross-reference list).

Debugging:
- PE04: Display PCR as a flowchart.
- Payroll log (RPCLSTAU) shows which rules fired and what they produced.
- Trace mode in payroll simulation shows step-by-step execution.""",
    },
]


# ════════════════════════════════════════════════════════════════════════════════
# SAP CORNER — Functions & Operations
# ════════════════════════════════════════════════════════════════════════════════

_SAP_FUNCTIONS = [
    {
        'title': 'Key Payroll Functions — WPBP, PIT, GRS, NET, TAX',
        'subcategory': 'functions_ops',
        'tags': ['schema', 'payroll'],
        'content': """Key Payroll Functions

Payroll functions are the built-in SAP routines called within schemas. Each function reads specific data, performs calculations, and writes results.

WPBP — Work Place / Basic Pay:
- Reads IT0001 (Org Assignment), IT0008 (Basic Pay), IT0007 (Planned Working Time).
- Creates the internal table WPBP with periods/splits.
- Splits occur when master data changes mid-period (retroactive changes).
- Each split gets its own WPBP row with from/to dates and all relevant master data.

PIT — Provide Internal Table:
- Reads specified infotype data and makes it available for processing.
- Commonly used: PIT 0014 (recurring deductions), PIT 0015 (additional payments), PIT 2010 (EE remuneration info).

GRS — Gross Calculation:
- Processes all wage types from basic pay, additional payments, and recurring deductions.
- Applies valuation rules and processing classes.

NET — Net Calculation:
- Calculates net pay after tax and deductions.
- Processes statutory and voluntary deductions.

TAX (AUTAX for Australia):
- Calculates PAYG withholding based on taxable gross.
- Reads IT0188 for tax scale, TFN, HELP debt indicator.
- Applies ATO coefficient tables.

SUCC / PRE:
- SUCC: Set up successor period processing (for retroactive calculations).
- PRE: Process previous period data.

IT — Input Table:
- Reads data into the internal payroll table from specific infotypes.

OT — Output Table:
- Writes processed wage types to the output/results table.

BT — Bank Transfer:
- Processes IT0009 (Bank Details) to split net pay across accounts.
- Handles multiple bank accounts, residual account logic.

Cumulation Functions:
- CUM: Cumulate wage types into cumulation identifiers for reporting.
- Used for year-to-date totals, quarter-to-date, etc.""",
    },
]


# ════════════════════════════════════════════════════════════════════════════════
# SAP CORNER — ABAP
# ════════════════════════════════════════════════════════════════════════════════

_SAP_ABAP = [
    {
        'title': 'ABAP Best Practices for SAP HCM/Payroll',
        'subcategory': 'abap',
        'tags': ['abap', 'payroll'],
        'content': """ABAP Best Practices for SAP HCM/Payroll

Naming Conventions:
- Custom objects: Z or Y namespace (Z* for customer, Y* for partner).
- Programs: ZHRPY_* for payroll, ZHRCM_* for core HR, ZHREC_* for EC integration.
- Function modules: Z_HR_* prefix.
- Tables: ZHR_* prefix.
- Wage types: Z* wage types (9000-9999 range or customer-designated).

Payroll-Specific ABAP:
- Reading payroll results: Use macros (RP-PROVIDE-FROM-LAST, RP-IMPORT-C2-yy) or class CL_HRPA_READ_PAYROLL_RESULT.
- Cluster access: PCL2 (payroll results), PCL1 (time results). Use IMPORT FROM DATABASE.
- Evaluation path: Use RH_STRUC_GET for org structure traversal.

Performance:
- Always use FOR ALL ENTRIES with sorted internal tables.
- Avoid SELECT * — specify only needed columns.
- Use HASHED or SORTED table types for lookups.
- Buffer master data reads — employee data is read repeatedly.
- Use logical databases (PNP/PNPCE) for HR reports.

Error Handling:
- Use TRY...CATCH for exception-based flow.
- Log errors to application log (BAL_LOG_CREATE / BAL_LOG_MSG_ADD).
- Never silently swallow errors in payroll exits.

Testing:
- Unit test payroll exits with CL_ABAP_UNIT_ASSERT.
- Test payroll schemas with PC00_M13_CALC_SIMU.
- Compare results with PC00_M99_CIPE (Payroll Results Comparison).

Common Payroll Exits/BAdIs:
- HRPAYAU_PROCESS: Australian payroll processing exit.
- EXIT_RPCALCX0_001: Customer exit for payroll calculation.
- HRPAYXX_GROSS: Gross calculation enhancement.
- BADI_HRPAY00_CEDT: Payslip enhancement.""",
    },
]


# ════════════════════════════════════════════════════════════════════════════════
# SAP CORNER — EC / ECP
# ════════════════════════════════════════════════════════════════════════════════

_SAP_EC_ECP = [
    {
        'title': 'Employee Central Payroll (ECP) — Architecture & Integration',
        'subcategory': 'ec_ecp',
        'tags': ['ecp', 'payroll'],
        'content': """Employee Central Payroll (ECP) Architecture

ECP runs SAP payroll in the cloud, consuming master data from SuccessFactors Employee Central (EC).

Architecture:
- EC (SuccessFactors): Cloud HCM — stores employee master data, org structure, positions.
- ECP (SAP S/4HANA Cloud or BTP): Runs the payroll engine with replicated data.
- Replication: EC → ECP via SAP Integration Center (middleware) or HCI-based integration.
- Pay Statement: Generated in ECP, viewable in EC self-service.

Replication Mapping:
EC entities map to SAP infotypes:
- Employment Information → IT0001 (Org Assignment)
- Compensation Information → IT0008 (Basic Pay)
- Personal Information → IT0002 (Personal Data)
- Job Information → IT0001 fields
- Pay Component (Recurring) → IT0014 (Recurring Deductions/Payments)
- Pay Component (Non-Recurring) → IT0015 (Additional Payments)
- Bank Details → IT0009

Key Points:
1. Replication runs on schedule or on-demand. Monitor via /SAPHR/INT_MON.
2. Not all EC fields are relevant to payroll — mapping is selective.
3. Custom fields in EC require custom mapping configurations.
4. ECP uses the same payroll schemas and PCRs as on-premise SAP payroll.
5. Time data can come from EC Time Off or external time systems.

Troubleshooting Replication:
- /SAPHR/INT_MON — Integration monitoring
- /SAPHR/INT_SIMUL — Simulation mode
- /SAPHR/INT_ERROR — Error log
- Check mapping in /SAPHR/INT_MAP for field-level issues.

Side-by-side vs Full Migration:
- Side-by-side: EC for HR, ECP for payroll. Most common current approach.
- Full: SAP S/4HANA HCM with EC as front-end. Rarer.""",
    },
    {
        'title': 'EC Onboarding (SAP SuccessFactors) — Process & Integration',
        'subcategory': 'onboarding_sap',
        'tags': ['ecp', 'sap_hcm'],
        'content': """SAP SuccessFactors Onboarding

Onboarding 2.0 (ONB 2.0) is the current generation. ONB 1.0 is legacy.

Key Components:
1. Onboarding Dashboard: Hiring manager and new hire see tasks, documents, forms.
2. Document Generation: Offer letters, contracts, compliance forms (via DocuSign or native).
3. Data Collection: New hire enters personal data, tax declarations, bank details, super choice.
4. Compliance: Work rights verification, background checks integration.
5. Equipment & Provisioning: Task assignments for IT, facilities.
6. Buddy/Mentor Assignment: Social onboarding features.

Integration with EC:
- New hire record created in EC Recruiting → triggers ONB process.
- Data collected in ONB flows to EC Employment record.
- Upon "hire complete" in ONB, EC record activates → replicates to ECP.
- Time-critical: payroll needs complete data before first pay run.

Australia-Specific Onboarding:
- TFN Declaration (NAT 3092): Tax file number, tax scale, HELP debt.
- Super Choice Form: Employee nominates super fund.
- Fair Work Information Statement: NES entitlements.
- Modern Slavery statement (large employers).
- Working With Children Check (state-based).
- Right to Work verification.

Configuration:
- Onboarding Templates in Provisioning: Define steps, panels, task flows.
- Responsible Group: Assign tasks to HR, line manager, IT, etc.
- Custom Data Collection: Map to EC custom fields.
- Email Notifications: Welcome emails, task reminders, deadline alerts.

Key Tables/APIs:
- OData APIs for ONB entities.
- SuccessFactors Extensions: Can build custom pages via BTP.
- Integration Center: For pushing onboarding data to external systems.""",
    },
]


# ════════════════════════════════════════════════════════════════════════════════
# SAP CORNER — BAPIs & Infotypes
# ════════════════════════════════════════════════════════════════════════════════

_SAP_BAPIS = [
    {
        'title': 'Key HR BAPIs — Master Data & Payroll',
        'subcategory': 'bapis',
        'tags': ['abap', 'sap_hcm'],
        'content': """Key SAP HR BAPIs

Master Data BAPIs:
- BAPI_EMPLOYEE_GETDATA: Read employee master data records. Parameters include infotype, employee number, date range. Returns all records for that infotype.
- BAPI_EMPLOYEET_CREATE_: Infotype-specific creation BAPIs (e.g., BAPI_EMPLOYEET_CREATE_0001 for Org Assignment). Note the suffix pattern.
- BAPI_EMPLOYEET_CHANGE_: Infotype-specific modification BAPIs.
- BAPI_EMPLOYEET_DELETE_: Infotype-specific deletion BAPIs.
- BAPI_EMPLOYEE_ENQUEUE / DEQUEUE: Lock/unlock employee records for concurrent access.

Org Management BAPIs:
- BAPI_ORGUNIT_GETDETAIL: Read org unit details.
- BAPI_POSITION_GETDETAIL: Read position details.
- RH_STRUC_GET: Evaluate org structure along an evaluation path.

Payroll BAPIs:
- BAPI_PR_READ: Read payroll results for an employee.
- HR_PAYROLL_SIMULATE: Simulate payroll run.

Time BAPIs:
- BAPI_ABSENCE_CREATE / CHANGE / DELETE: Manage absence records (IT2001).
- BAPI_ATTENDANCE_CREATE: Create attendance records (IT2002).
- BAPI_QUOTA_GETDETAIL: Read absence quota balances.

Best Practices:
1. Always use BAPI_EMPLOYEE_ENQUEUE before modifying and DEQUEUE after.
2. Check RETURN table for errors after every BAPI call.
3. Call BAPI_TRANSACTION_COMMIT after successful write BAPIs.
4. Use date parameters (BEGINDATE/ENDDATE) to scope reads.
5. For batch operations, consider HR_INFOTYPE_OPERATION as an alternative (more flexible but requires more setup).
6. BAPIs respect HR authorisations (P_ORGIN, P_PERNR, P_ORGXX).

HR_INFOTYPE_OPERATION:
- More versatile than individual BAPIs for infotype maintenance.
- Supports all infotypes with single interface.
- Parameters: infotype, subtype, operation (INSERT/MOD/DEL/COPY), record data.
- Returns RETURN structure with messages.""",
    },
]

_SAP_INFOTYPES = [
    {
        'title': 'Key Infotypes — Australia & Global',
        'subcategory': 'infotypes',
        'tags': ['infotype', 'sap_hcm'],
        'content': """Key SAP HR Infotypes

Global Infotypes (0000–0999):
- IT0000: Actions (hire, terminate, transfer, org change — the event log).
- IT0001: Organizational Assignment (company code, personnel area, cost center, position).
- IT0002: Personal Data (name, DOB, gender, nationality, marital status).
- IT0003: Payroll Status (payroll area, locked indicator, earliest retro date).
- IT0006: Addresses (permanent, mailing, emergency contact).
- IT0007: Planned Working Time (work schedule rule, employment percent, daily/weekly hours).
- IT0008: Basic Pay (pay scale, wage types, amounts, currency, pay frequency).
- IT0009: Bank Details (bank key, account number, payment method, amount/percentage split).
- IT0014: Recurring Payments/Deductions (wage type, amount, frequency, start/end dates).
- IT0015: Additional Payments (one-time payments, bonuses, back-pays).
- IT0016: Contract Elements (contract type, probation date, notice period).
- IT0021: Family/Related Persons (dependants, beneficiaries, emergency contacts).
- IT0041: Date Specifications (seniority dates, custom dates for LSL, probation end, etc.).

Australia-Specific Infotypes:
- IT0188: Tax AU — TFN, tax scale, HELP/STSL debt, tax-free threshold, Medicare variation.
- IT0220: Superannuation AU — Fund USI/SPIN, membership number, employer/employee rates.
- IT0588: Additional Super AU — Salary sacrifice, additional voluntary contributions.

Time Infotypes:
- IT2001: Absences (all leave types — annual, personal, LSL, parental, etc.).
- IT2002: Attendances (overtime, training, travel, etc.).
- IT2006: Absence Quotas (leave balances — entitlement, used, remaining).
- IT2010: Employee Remuneration Info (variable payments, commission, bonuses from external).

Payroll Result Infotypes (Internal):
Stored in payroll cluster (PCL2), not directly in PA tables:
- RT: Results Table (all calculated wage types).
- CRT: Cost Results Table.
- WPBP: Work Place / Basic Pay periods.
- BT: Bank Transfer results.
- VERSC: Insurance contributions.""",
    },
]

_SAP_WAGE_TYPES = [
    {
        'title': 'Wage Types — Configuration & Processing Classes',
        'subcategory': 'wage_types',
        'tags': ['payroll', 'schema'],
        'content': """Wage Types in SAP Payroll

Wage Type Categories:
- Model wage types (/xxx): System-generated during payroll (e.g., /001 Base salary, /101 PAYG tax).
- Primary wage types (Mxxx or 1xxx-4xxx): Entered on master data infotypes (IT0008, IT0014, IT0015).
- Secondary/Technical wage types (/xxx, 5xxx-9xxx): Generated by payroll processing.
- Customer wage types (9xxx or Zxxx): Custom-defined.

Key Australian Wage Types:
- /001: Basic salary/wages
- /101: PAYG tax
- /3F1: Super Guarantee (employer)
- /560: Net pay
- Mxxx: Master data wage types (Basic Pay IT0008)

Processing Classes:
Processing classes control HOW a wage type behaves during payroll. Configured in V_512W_D.
- PC01: General categorisation (payment/deduction/technical).
- PC03: Tax treatment (taxable, exempt, FBT, etc.).
- PC10: Cost assignment (how wage type posts to cost center/GL).
- PC20: Cumulation — which cumulation wage types this feeds.
- PC30: Net/gross indicator.
- PC40: Partial period factor — how pro-rating works on period splits.
- PC52: Super Guarantee — whether the wage type is OTE (Ordinary Time Earnings).

Cumulation Identifiers (/Cxx):
Wage types accumulate into cumulation identifiers for reporting:
- /101 to /110: Tax-related cumulations
- /1A0 to /1A9: Australia-specific cumulations
- Configure via V_52C0 → V_52C3.

Valuation (V_T512W):
- Indirect valuation: Wage type amount derived from pay scale (modif type A).
- Direct valuation: Amount entered on infotype.
- Special valuation: Amount calculated by payroll function/PCR.

Configuration Path:
PM → Payroll → Payroll: Australia → Basic Settings → Wage Types → ...
Key tables: T512W (wage type characteristics), T512Z (wage type valuation), T511 (pay scale).""",
    },
]

_SAP_FEATURES = [
    {
        'title': 'SAP Features (PE03) — Decision Trees for Config',
        'subcategory': 'features',
        'tags': ['payroll', 'sap_hcm'],
        'content': """SAP Features (PE03) — Dynamic Configuration

Features are decision trees that return a value based on employee master data.
They replace hard-coded table entries with dynamic, employee-specific logic.

Transaction PE03: Feature editor.

Common Payroll Features:
- ABKRS: Determines payroll area from org assignment fields.
- LGMST: Default pay scale for basic pay.
- TARIF: Pay scale type and area.
- SCHKZ: Work schedule rule.
- VESSION: Evaluation class for statistics.
- QUOMO: Quota type selection for time management.
- TMSTA: Time management status.

How Features Work:
A feature evaluates employee data (infotype fields) through a decision tree.
Each node checks a field (e.g., Personnel Area, Employee Group, Company Code).
Leaf nodes return a value.

Example — Feature ABKRS:
IF Personnel Area = 1000
  IF Employee Group = 1 (Active)
    IF Employee Subgroup = DL (Daily)
      RETURN = D1 (payroll area for daily employees)
    IF Employee Subgroup = MN (Monthly)
      RETURN = M1 (payroll area for monthly employees)
  IF Employee Group = 2 (Inactive)
    RETURN = XX (excluded from payroll)

Feature Variants:
- PINCH: Default personnel area/subarea for hiring.
- NUMKR: Number range for personnel numbers.
- IGMOD: Infotype menu grouping.

Best Practices:
1. Document every branch — features can become very deep trees.
2. Always have a default return value (catch-all).
3. Test with specific employee records using PE03's test function.
4. Copy SAP-delivered features to customer namespace before heavy modification.
5. Keep the tree balanced — avoid deep nesting on one branch.""",
    },
]


# ════════════════════════════════════════════════════════════════════════════════
# PROGRAMMING
# ════════════════════════════════════════════════════════════════════════════════

_PROGRAMMING = [
    {
        'title': 'Python Best Practices — Clean Code',
        'category': 'programming',
        'subcategory': 'python',
        'tags': [],
        'content': """Python Best Practices

Code Structure:
- One module = one concern. Keep files under 400 lines.
- Use __init__.py sparingly — prefer explicit imports.
- Functions should do one thing and be under 30 lines.
- Use type hints for function signatures (def foo(x: int) -> str:).

Naming:
- snake_case for functions and variables.
- PascalCase for classes.
- UPPER_CASE for module-level constants.
- Prefix private items with underscore (_helper).
- Use descriptive names — avoid single-letter variables except in short lambdas/comprehensions.

Error Handling:
- Catch specific exceptions, never bare `except:`.
- Use custom exception classes for domain errors.
- Log exceptions with logger.exception() for full traceback.
- Fail fast at system boundaries, handle gracefully at user boundaries.

Testing:
- Use pytest, not unittest. Fixtures over setup/teardown.
- Test behaviour, not implementation. Test public interfaces.
- Use parametrize for data-driven tests.
- Aim for fast tests — mock I/O, use in-memory databases for tests.

Performance:
- Profile before optimising. Use cProfile or py-spy.
- Prefer generators/itertools for large sequences.
- Use dict/set for lookups instead of list scanning.
- dataclasses or NamedTuple over plain dicts for structured data.

Patterns:
- Prefer composition over inheritance.
- Use context managers (with statement) for resource management.
- Prefer pathlib over os.path.
- Use f-strings for formatting (f"{name}"), not % or .format().""",
    },
    {
        'title': 'Code Review Guidelines',
        'category': 'programming',
        'subcategory': 'code_review',
        'tags': [],
        'content': """Code Review Guidelines

What to Check:
1. Correctness: Does the code do what it claims? Edge cases handled?
2. Readability: Can someone new understand it in 2 minutes?
3. Security: Input validation, SQL injection, XSS, auth checks present.
4. Performance: N+1 queries, unbounded loops, memory leaks.
5. Testing: Are tests present? Do they test behaviour, not just happy path?
6. Naming: Are names clear and consistent with codebase conventions?
7. Error handling: Are exceptions caught appropriately? Are errors logged?

How to Review:
- Read the PR description first — understand intent before reading code.
- Check the diff file by file in logical order (models → logic → API → tests).
- Run the code locally if the change is non-trivial.
- Leave comments on specific lines, not vague general feedback.
- Use "nit:" prefix for style/preference suggestions (not blocking).
- Ask questions when unclear — "Why X instead of Y?" not "This is wrong".

How to Respond to Reviews:
- Address every comment, even if just "Done" or "Won't change because X".
- Don't take feedback personally — the code is being reviewed, not you.
- If you disagree, explain your reasoning — then accept the team's decision.
- Batch your responses — don't update one comment at a time.

Red Flags:
- Functions over 50 lines.
- More than 3 levels of nesting.
- Commented-out code.
- Magic numbers without constants.
- No error handling around I/O operations.
- Tests that test implementation details (mocking internals).""",
    },
    {
        'title': 'Testing Strategies — Pyramids and Pragmatism',
        'category': 'programming',
        'subcategory': 'testing',
        'tags': [],
        'content': """Testing Strategies

Test Pyramid:
- Unit tests (70%): Fast, isolated, test one function/class.
- Integration tests (20%): Test component interactions (DB, API, services).
- E2E tests (10%): Test full user workflows. Slow but high confidence.

Unit Testing:
- Test public interfaces, not private methods.
- Use parametrize/table-driven tests for variations.
- Mock external dependencies (network, database, file system).
- One assertion per test concept (multiple asserts OK if testing one thing).
- Arrange → Act → Assert pattern.

Integration Testing:
- Use test databases (SQLite in-memory for Python).
- Test API endpoints with test client (Flask's test_client()).
- Verify database state after operations.
- Test error paths — bad input, missing data, timeouts.

Testing Anti-Patterns:
- Testing implementation details (breaks on refactor).
- Excessive mocking (test becomes a mirror of implementation).
- Slow test suites (tests should run in seconds, not minutes).
- Flaky tests (random failures). Fix or delete them.
- Tests that depend on execution order.

What to Test:
- Business logic (calculations, rules, transformations).
- Error handling (what happens when things fail).
- Edge cases (empty input, max values, concurrent access).
- Security (auth required, input validation, rate limiting).

What NOT to Test:
- Framework code (Flask routing, ORM queries — those are tested by the framework).
- Trivial getters/setters.
- Third-party library internals.""",
    },
]


# ════════════════════════════════════════════════════════════════════════════════
# Seed function
# ════════════════════════════════════════════════════════════════════════════════

def _all_sap_docs():
    """Collect all SAP Corner documents."""
    docs = []
    for doc in (_SAP_PAYROLL_AU + _SAP_SCHEMAS_PCR + _SAP_FUNCTIONS +
                _SAP_ABAP + _SAP_EC_ECP + _SAP_BAPIS + _SAP_INFOTYPES +
                _SAP_WAGE_TYPES + _SAP_FEATURES):
        d = dict(doc)
        d.setdefault('category', 'sap_corner')
        docs.append(d)
    return docs


def _all_programming_docs():
    """Collect all Programming documents."""
    docs = []
    for doc in _PROGRAMMING:
        d = dict(doc)
        d.setdefault('category', 'programming')
        docs.append(d)
    return docs


def seed_collection(collection='all'):
    """
    Seed the library with built-in knowledge documents.
    Returns (added_count, skipped_count).
    """
    from lib.knowledge.store import add_source, check_duplicate, ensure_schema
    from lib.knowledge.ingest import process_source

    ensure_schema()

    docs = []
    if collection in ('all', 'sap_corner'):
        docs.extend(_all_sap_docs())
    if collection in ('all', 'programming'):
        docs.extend(_all_programming_docs())

    added = 0
    skipped = 0

    for doc in docs:
        content = doc['content'].strip()
        existing = check_duplicate(content)
        if existing:
            skipped += 1
            continue

        source_id = add_source(
            title=doc['title'],
            source_type='text',
            raw_text=content,
            domain_tags=doc.get('tags', []),
            added_by='system',
            category=doc.get('category', 'general'),
            subcategory=doc.get('subcategory'),
        )

        # Embed in background thread
        def _embed(sid=source_id, text=content):
            try:
                process_source(sid, text)
            except Exception as exc:
                logger.error(f'[Seed] embed error source={sid}: {exc}')

        threading.Thread(target=_embed, daemon=True).start()
        added += 1

    logger.info(f'[Seed] collection={collection}: added={added}, skipped={skipped}')
    return added, skipped
