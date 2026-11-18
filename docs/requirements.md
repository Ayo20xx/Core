# CORE Banking Service — Requirements Specification

**Version:** 1.0  
**Status:** Draft  
**Technology:** Python, FastAPI, PostgreSQL, SQLAlchemy

## 1. Project Overview

CORE is a banking backend responsible for managing customers, accounts, wallets, balances and financial transactions.

It serves as the source of truth for internal financial operations.

CORE will eventually integrate with FORGE, an independent banking integration service responsible for retrieving, normalising and synchronising external banking information.

## 2. Scope of V1

CORE V1 will support:

- Customer registration and authentication.
- Customer account creation.
- Automatic EUR wallet creation.
- Wallet balance management.
- Administrator-initiated deposits.
- Internal transfers between customers.
- Double-entry bookkeeping.
- Transaction history.
- Idempotent financial operations.
- Transaction reversals.
- Audit records for financial operations.

**Currency:** EUR only in V1.

The database and application architecture must support additional currencies in the future without requiring a fundamental redesign.

## 3. Functional Requirements

### 3.1 Customer Management

- Customers must be able to register.
- Customer email addresses must be unique.
- Passwords must be securely hashed.
- Customers must be able to authenticate.
- Customers must only access their own financial information.

### 3.2 Account Management

- Each customer can have one account in V1.
- Each account must belong to exactly one customer.
- Each account must have a unique UUID identifier.
- Each account must have a tracked lifecycle status.
- Supported statuses include PENDING, ACTIVE, SUSPENDED and CLOSED.
- Account status changes must be auditable.
- An account cannot perform financial operations unless its status permits them.
- The architecture should allow multiple accounts per customer in future versions.

### 3.3 Wallet Management

- Every newly created account automatically receives an EUR wallet.
- Each wallet belongs to one account.
- Each wallet represents one currency.
- An account cannot have multiple wallets of the same currency.
- Wallet balances are stored in integer minor units (cents).
- Wallet balances cannot become negative.
- Additional currencies can be enabled in future versions.

### 3.4 Deposits

- Authorised administrators can initiate deposits.
- Deposits must identify their source.
- Deposits must generate balanced ledger entries.
- Every deposit must be associated with a transaction record.
- Administrative deposits must be auditable.
- Test deposits must be distinguishable from verified external funding.

### 3.5 Internal Transfers

- Customers can transfer funds to other customers.
- Transfers must initially support EUR only.
- The sender must have sufficient available funds.
- The sender must be debited and receiver credited.
- Both operations must succeed or fail together.
- Transfers must generate balanced ledger entries.
- Duplicate requests must not produce duplicate transfers.

### 3.6 Ledger Management

- CORE must implement double-entry bookkeeping.
- Every posted financial transaction must have balanced debit and credit entries.
- Ledger entries must be immutable after posting.
- Posted entries must never be deleted or silently modified.
- Corrections must be performed through compensating entries.
- Ledger records must identify the affected financial accounts.
- Ledger records must preserve the source and destination of funds.

### 3.7 Transaction Management

- Every financial operation must have a unique identifier.
- Transactions must track their type, amount, currency, status and timestamps.
- Transactions must reference their corresponding ledger records.
- Supported transaction types include deposits, transfers and reversals.
- Transaction history must be retrievable by authorised customers.

### 3.8 Idempotency

- Financial operations must support idempotency keys.
- Repeated requests with the same key and payload must not execute twice.
- Reusing an idempotency key with a different payload must be rejected.
- Previously completed operations must return their original result.

### 3.9 Reversals

- Posted transactions must not be deleted.
- Reversals must create new compensating ledger entries.
- Reversals must reference their original transactions.
- A transaction must not be reversed more than once.
- Reversal operations must be atomic.

## 4. Non-Functional Requirements

### Data Integrity
- PostgreSQL constraints must enforce critical data invariants.
- Financial operations must use database transactions.
- Concurrent transfers must not cause double spending.
- Monetary values must never use floating-point arithmetic.

### Security
- Passwords must be securely hashed.
- Authentication and authorisation must be enforced.
- Administrative operations must require appropriate permissions.
- Sensitive operations must be auditable.

### Reliability
- Financial operations must be atomic.
- Failed operations must not leave partially updated financial records.
- Database migrations must be managed through Alembic.

### Testability
- Unit tests must cover business logic.
- Integration tests must cover database operations.
- End-to-end tests must cover complete financial workflows.
- Concurrency and failure scenarios must be tested.

## 5. Future Scope — Not V1

The following capabilities are planned for future development:

- FORGE integration.
- External bank transaction synchronisation.
- Additional currencies (USD, GBP, NGN).
- Currency conversion.
- External withdrawals and payments.
- Bank reconciliation.
- Advanced fraud detection.
- Transaction notifications.

## 6. Architectural Principles

1. CORE owns internal financial records and wallet balances.
2. FORGE owns external banking integrations and synchronisation.
3. The ledger is the financial source of truth.
4. Wallet balances are controlled projections of ledger activity.
5. Posted ledger entries are immutable.
6. Financial operations must be atomic and idempotent.
7. Database constraints complement application-level validation.

## 7. Definition of Done

CORE V1 is considered complete when:

- Customers can register and receive EUR wallets automatically.
- Administrators can initiate auditable test deposits.
- Customers can transfer funds internally.
- All financial operations produce balanced ledger entries.
- Duplicate requests cannot create duplicate financial operations.
- Failed operations cannot leave inconsistent balances.
- Posted transactions can be reversed without deleting history.
- Automated tests cover normal and failure scenarios.
