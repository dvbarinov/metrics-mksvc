from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.core.broadcaster import metrics_aggregator
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(metrics_aggregator())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)

# подключить роутеры...