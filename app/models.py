from pydantic import BaseModel, Field


class TransferRequest(BaseModel):
    from_account: str
    to_account: str
    amount: float = Field(gt=0)


class TransferResponse(BaseModel):
    transfer_id: str
    from_balance: str
    to_balance: str
