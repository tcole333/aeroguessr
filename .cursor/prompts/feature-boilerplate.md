<!-- Cursor Feature Boilerplate Template -->

### Goal

Implement new FastAPI route **`<METHOD> /api/vX/<resource>`**.

### Deliverables

1. **Pydantic model(s)** – request & response in `backend/schemas/<resource>.py`.
2. **Router function** in `backend/routes/<resource>.py`.
3. **Service logic** (if needed) in `backend/services/<resource>.py`.
4. **Unit test** in `tests/backend/<area>/test_<action>.py`.
5. **OpenAPI** auto-regen (`make openapi`).
6. **README snippet** under _Endpoints_ section (if significant).

### Steps

- [ ] Create/extend Pydantic schema(s).
- [ ] Implement route logic (`async def`) in router.
- [ ] Implement business logic in service layer.
- [ ] Add Swagger example/description in route docstring.
- [ ] Write positive + negative/edge-case unit tests.
- [ ] Run `pre-commit run --all-files`.
- [ ] Run `make openapi` and review changes.
- [ ] Commit updated `.docs/api_openapi.yaml`.

### Important Context

### Example Stub Code

```python
# Example Route Stub (in backend/routes/items.py)
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.schemas.item import ItemCreate, ItemOut
from backend.services.item_service import create_new_item

router = APIRouter()

@router.post("/items", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
async def create_item_endpoint(
    item_in: ItemCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new item.

    - **item_in**: Item data to create.
    - **Returns**: The newly created item.
    """
    try:
        new_item = create_new_item(db=db, item_create=item_in)
        return new_item
    except Exception as e: # Be more specific in real code
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

```
