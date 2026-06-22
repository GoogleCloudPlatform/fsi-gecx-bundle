# Story 1.4: Refactoring Database Access via Repository Pattern

## Overview
This plan defines the architectural transition of the `banking-service` database layers from inline SQLAlchemy engine queries and raw `.sql` file lookups to a formal, type-safe **Repository Pattern**.

This aligns the backend codebase with enterprise-grade Python conventions, facilitating unit testing without real database connections (mocking), and decoupling API routers from database schema details.

---

## 📐 1. Architectural Strategy

### Design Guidelines:
1.  **Repository Class Injection**: Each repository class will accept a SQLAlchemy `Session` instance via its constructor. The database session lifecycle (commit, rollback, close) remains managed by the caller (typically FastAPI dependency injection or Celery tasks).
2.  **No Dynamic Raw SQL Loading**: Standard CRUD operations (retrieval, insertion, simple filtering) will be written using type-safe SQLAlchemy ORM syntax.
3.  **Strict Parameterization**: Any raw SQL queries that remain for complex analytical operations will use SQLAlchemy `text()` binders or parameterized formats to protect against SQL injections.
4.  **Security & BOLA Access Checks**: Repositories must enforce customer context checks (e.g. `customer_id` parameters) where appropriate to prevent Broken Object Level Authorization (BOLA) vulnerabilities.

---

## 🛠️ 2. Detailed Task Breakdown

### Task 1: Create Base Repository & Core Repositories
*   Create a base repository layer if shared helper structures are needed.
*   Implement three core repository files:
    1.  `repositories/credit_card.py`: Manages `FinancialAccount`, `IssuedCard`, `TransactionAuthorization`, and `AccountLedger`.
    2.  `repositories/support.py`: Manages `Escalation`.
    3.  `repositories/settings.py`: Manages `SystemSetting`.

#### Example Code Blueprint:
```python
# repositories/support.py
from typing import Optional, List
from sqlalchemy.orm import Session
from models.support import Escalation

class SupportRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_escalation_by_id(self, escalation_id: str) -> Optional[Escalation]:
        return self.db.query(Escalation).filter(Escalation.id == escalation_id).first()

    def get_escalations_by_customer(self, customer_id: str) -> List[Escalation]:
        return self.db.query(Escalation).filter(Escalation.customer_id == customer_id).all()

    def create(self, escalation: Escalation) -> Escalation:
        self.db.add(escalation)
        self.db.flush()
        return escalation
```

---

### Task 2: Refactor FastAPI Routers & Services
*   Remove inline `db.query(...)` expressions from:
    *   `routers/mcp/credit_card.py`
    *   `routers/mcp/support.py`
    *   `services/credit_card.py`
*   Define FastAPI dependency providers for each repository class:
    ```python
    def get_credit_card_repo(db: Session = Depends(get_db)) -> CreditCardRepository:
        return CreditCardRepository(db)
    ```
*   Inject repositories using `Depends(get_X_repo)` in all endpoints.

---

### Task 3: Migrate In-Memory DB Unit Tests to Mocks
*   Update unit tests in `tests/test_credit_services.py` and `tests/test_support_escalations.py`.
*   Replace standard SQLite table seeding with clean unit test mocks of the repository layer, allowing fast, sub-second test execution.

---

## 🧪 3. Success & Verification Criteria
*   [ ] All FastAPI routes continue to behave identically, validated by the integration tests.
*   [ ] Direct queries and database actions are 100% centralized within the `repositories/` package.
*   [ ] Unit tests mock repository endpoints instead of writing directly to SQLite files where business logic is being verified.
*   [ ] All Ruff and Mypy static check tasks pass cleanly.
