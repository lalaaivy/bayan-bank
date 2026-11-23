# Bayan Bank

Bayan Bank is a Django-based banking management system developed as an academic/demo project. It simulates common banking operations for clients and bank personnel, including savings, loans, repayments, transaction records, notifications, management reports, and an AI-assisted chatbot.

> **Important:** This is a demonstration system. It does not process real money and must not be used as a production banking platform.

## Features

### Client Portal
- Client dashboard and banking overview.
- Regular bank account and savings account information.
- Online savings deposits.
- Savings deposits with supported terms and interest calculations.
- Savings early-withdrawal request workflow.
- Loan applications with supporting-document uploads.
- Loan status and installment viewing.
- Loan agreement review and acceptance.
- Online loan repayments from the client's regular bank account.
- Notifications and account activity information.

### Loan Officer
- Centralized queue of submitted loan applications.
- Access to application details and uploaded supporting documents.
- Review of applicant and eligibility information.
- Approval or rejection of loan applications.

Loan officers make loan decisions. They do not release loan proceeds.

### Staff
- Staff dashboard and operational views.
- Processing of approved loan disbursements.
- Disbursement of loan proceeds to the client's regular `BankAccount`.
- Processing of applicable savings withdrawals and loan repayments.
- Access to operational loan information.

**Loan disbursement rule:** Approved loan proceeds are disbursed to the client's regular bank account, not to the savings account. The client must accept the loan agreement before disbursement.

### Administrator
- Administrative dashboard.
- Management reports with date-range filtering.
- Loan portfolio and delinquency summaries.
- Charts for loan activity, savings activity, interest credits, and loan status.
- PDF and Excel report exports.
- System and user administration, subject to configured permissions.

### Other System Components
- Double-entry-style transaction history through ledger records (where implemented by the application workflows).
- Notifications.
- Kabayan chatbot integration using Google's Gemini API.
- Audit/activity records for supported operations.

## Technology Stack

- **Backend:** Python, Django
- **Database:** SQLite by default in the current development setup; database configuration may be changed through project settings/environment variables.
- **Frontend:** Django Templates, HTML, CSS, JavaScript, Bootstrap
- **Charts:** Chart.js
- **Chatbot:** Google Gen AI SDK (Gemini)
- **Report exports:** PDF and Excel support

## Project Structure

The repository is organized into Django applications. The principal areas include:

| Directory | Purpose |
|---|---|
| `accounts/` | Authentication, roles, dashboards, and account-related views |
| `accounting/` | Bank accounts, ledger entries, and transaction records |
| `loans/` | Loan products, applications, eligibility, documents, agreements, installments, and payments |
| `savings/` | Savings accounts, deposits, interest, and early-withdrawal requests |
| `chatbot/` | Kabayan chatbot integration |
| `config/` | Django project settings and URL configuration |
| `templates/` | Shared and application-specific HTML templates |
| `static/` | Static assets such as stylesheets, scripts, and images |
| `private_uploads/` | Private uploaded documents at runtime; not intended for source control |

The exact files and modules may evolve as development continues.

## Requirements

- Python 3.13 or a compatible Python version supported by the installed Django dependencies.
- `pip`
- Git
- A supported web browser
- A Gemini API key if the chatbot feature is to be used.

Install the Python dependencies from the repository's `requirements.txt`.

## Installation and Setup

The following instructions use Windows Command Prompt.

### 1. Clone the repository

```cmd
git clone https://github.com/lalaaivy/bayan-bank.git
cd bayan-bank
```

To use the team's current integration branch:

```cmd
git checkout integration/bayan-bank
```

### 2. Create a virtual environment

```cmd
py -3.13 -m venv venv
```

Activate it:

```cmd
venv\Scripts\activate
```

If the `py` launcher does not select the intended Python installation, create the environment using the full path to your Python executable.

### 3. Install dependencies

```cmd
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 4. Configure environment variables

Create a local `.env` file if the project configuration uses environment variables. Do not commit this file.

Example configuration:

```env
DJANGO_SECRET_KEY=replace-with-a-long-random-secret
DJANGO_DEBUG=True
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-3.5-flash
```

Use the exact variable names expected by the current `config/settings.py`. The Gemini variables are used by the chatbot integration. Do not share or commit API keys, passwords, or production secrets.

For local development, configure the database using the project's current settings. The current development setup uses SQLite unless the settings are changed.

### 5. Apply database migrations

```cmd
venv\Scripts\python.exe manage.py migrate
```

### 6. Create an administrator account

```cmd
venv\Scripts\python.exe manage.py createsuperuser
```

Follow the prompts to create the account.

### 7. Run the development server

```cmd
venv\Scripts\python.exe manage.py runserver
```

Open the local development address shown by Django, normally:

```text
http://127.0.0.1:8000/
```

Stop the server with `Ctrl+C`.

## Main Banking Workflows

### Loan application and decision

1. An eligible, active client submits a loan application.
2. The client provides the required supporting documents.
3. The application appears in the loan officer's application queue.
4. The loan officer reviews the application, eligibility information, and documents.
5. The loan officer approves or rejects the application.
6. For an approved application, the client reviews and accepts the loan agreement.
7. Authorized staff disburse the approved loan to the client's regular bank account.

### Loan repayment

1. A client makes an online repayment using their regular bank account, or authorized staff process an applicable repayment.
2. The system records the payment and updates the relevant account and installment information.
3. Payment processing should be performed through the application's transaction workflow so related updates remain consistent.

### Savings

1. A client uses their savings account for supported deposit operations.
2. Eligible savings deposits accrue interest according to their configured terms and rates.
3. Interest credits and savings transactions are recorded in the ledger.
4. Early withdrawal requests follow their separate review workflow. Ordinary staff-processed withdrawals remain a separate operational process.

## Reports

The administrator's Management Reports page provides database-driven summaries and visualizations. Available report areas include:

- Loan status distribution.
- Loan disbursements and repayments over time.
- Savings deposits and withdrawals over time.
- Savings interest credits over time.
- Current active-loan and delinquency summaries.
- PDF and Excel exports.

Date filters apply to the report's period-based activity. Current loan portfolio figures are snapshots of the current database state, not historical snapshots.

**Accounting note:** Deposits, withdrawals, loan disbursements, and loan repayments are transaction flows. They should not automatically be interpreted as accounting revenue, expenses, or profit.

## Development and Validation

Run Django's system checks:

```cmd
venv\Scripts\python.exe manage.py check
```

Run the automated test suite:

```cmd
venv\Scripts\python.exe manage.py test
```

Compile Python files when diagnosing syntax issues:

```cmd
venv\Scripts\python.exe -m compileall .
```

Do not use production data for development testing. Use test accounts and clearly identified demonstration records.

## Security and Data Handling

- Never commit `.env`, API keys, passwords, private uploads, local databases, or database backups.
- Keep client-uploaded loan documents in private storage and serve them only through authorized views.
- Do not expose one client's account details, documents, or transactions to another client.
- Use role-based access controls for administrator, staff, loan officer, and client functions.
- Use HTTPS, secure cookies, production-grade secrets, and a properly configured production database before any real deployment.
- Review Django's deployment checklist before deployment:
  <https://docs.djangoproject.com/en/stable/howto/deployment/checklist/>

This project is for educational demonstration and is not certified or audited for real financial use.

## Git Branch

The team's integration branch is:

```text
integration/bayan-bank
```

To retrieve the latest integration branch:

```cmd
git fetch origin
git checkout integration/bayan-bank
git pull origin integration/bayan-bank
```

## Contributors

Developed collaboratively as an academic software project. Add the project members' names and assigned responsibilities here.

## License

This repository is an academic/demo project. Add the applicable license and usage terms before redistributing it publicly.
