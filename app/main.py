from fastapi import FastAPI

from app.routes import accounts, transactions, transfers

app = FastAPI(title="advisor-accounts")
app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(transfers.router)
