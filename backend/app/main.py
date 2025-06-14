from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .routers import users, chat, transactions, reports
from .models.database import engine, Base, get_db
from .init_db import import_assistants
from .models.models import AIPersonality
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Create database tables
Base.metadata.create_all(bind=engine)

# 只有在助手表为空时才导入预设助手配置
db = next(get_db())
assistant_count = db.query(AIPersonality).count()
if assistant_count == 0:
    try:
        import_assistants()
        print("成功导入助手配置到数据库")
    except Exception as e:
        print(f"导入助手配置失败: {e}")
else:
    print(f"数据库中已存在 {assistant_count} 个助手配置，跳过导入")

app = FastAPI(
    title="叨叨记账 API", description="智能AI记账助手后端API", version="0.1.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)

# Include routers
app.include_router(users.router, prefix="/users", tags=["Users"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])
app.include_router(transactions.router, prefix="/transactions", tags=["Transactions"])
app.include_router(reports.router, prefix="/reports", tags=["Reports"])


@app.get("/")
def read_root():
    return {"message": "Welcome to 叨叨记账 API", "status": "running"}
