import json

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form, Body
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime, date
import os
import openai
from dotenv import load_dotenv
import base64
import io
import uuid
import shutil
from PIL import Image


from ..models.database import get_db
from ..models.models import (
    User,
    ChatMessage,
    AIPersonality,
    Transaction,
    TransactionType,
)
from ..prompts.assistant import get_assistant, get_all_assistants_metadata
from .users import get_current_user

# 加载 .env 文件中的环境变量
load_dotenv()
router = APIRouter()

# Initialize API key from environment variable
openai.api_key = os.getenv("API_KEY")
# 配置API基础URL(可选)
openai.api_base = os.getenv("API_URL")
use_model = "gemini-2.5-flash-preview-05-20"
# 打印环境变量以进行调试
print("====== 环境变量检查 ======")
print(f"API_KEY: {os.getenv('API_KEY')}")
print(f"API_URL: {os.getenv('API_URL') or '未设置'}")
print("=========================")


# Pydantic models
class MessageBase(BaseModel):
    content: str
    personality_id: Optional[int] = None


class MessageCreate(MessageBase):
    pass


class MessageResponse(MessageBase):
    id: int
    user_id: int
    is_user: bool
    created_at: datetime

    class Config:
        orm_mode = True


class ChatResponse(BaseModel):
    message: MessageResponse
    extracted_info: Optional[Dict[str, Any]] = None
    needs_confirmation: bool = False


# 新的Pydantic模型用于交易确认
class TransactionConfirmation(BaseModel):
    message_id: int  # 关联的聊天消息ID
    confirm: bool  # 是否确认创建交易
    # 以下字段允许用户在确认前修改
    type: Optional[str] = None
    amount: Optional[float] = None
    description: Optional[str] = None
    category: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None


# Utility functions for AI interaction
def extract_financial_data(message_content: str):
    """
    Use LLM to extract financial transaction data from user messages.

    Implements:
    - FR-EXTRACT-001: 记账意图识别
    - FR-EXTRACT-002: 关键财务实体提取
    - FR-EXTRACT-003: 交易分类智能推断
    - FR-EXTRACT-004: 日期时间标准化处理
    - FR-EXTRACT-005: 金额信息规范化

    Returns:
        Dict with extracted information or None if no financial data found.
    """
    print("\n***** 开始提取财务信息 *****")
    print(f"用户消息: {message_content}")

    try:
        # 获取当前日期用于相对日期处理
        current_date = datetime.now().strftime("%Y-%m-%d")
        print(f"当前日期: {current_date}")

        # 构建详细的提示以满足所有提取需求
        prompt = f"""
        请分析以下用户消息，判断是否包含记账意图，并提取财务信息。

        ## 任务要求
        1. 首先判断是否存在记账意图（明确或隐含表达的收入/支出记录需求）
        2. 如果存在记账意图，提取以下财务实体:
           - 交易类型: "income"(收入) 或 "expense"(支出)
           - 金额: 数值，处理各种表述形式（中文数字、单位、非标准表述如"2k"）
           - 交易日期: 格式为YYYY-MM-DD，处理相对日期表述
           - 交易时间: 格式为HH:MM，如有提及
           - 交易描述: 描述交易的具体事由或物品
           - 交易分类: 根据描述推断最匹配的分类

        ## 交易分类选项
        - 餐饮美食
        - 交通出行
        - 服饰美容
        - 日用百货
        - 住房物业
        - 医疗健康
        - 文教娱乐
        - 人情往来
        - 工资薪酬
        - 投资理财
        - 奖金
        - 退款
        - 兼职收入
        - 租金收入
        - 礼金收入
        - 中奖收入
        - 意外所得
        - 其他收入
        - 其他支出
        - 未分类（仅当无法确定时使用）
        必须是以上的选项，不能有其他选项

        ## 处理规则
        - 日期处理: 相对日期（如"昨天"、"上周五"）转换为绝对日期，今天是{current_date}
        - 未提及日期时使用当前日期{current_date}
        - 金额标准化: 将各种金额表述转换为标准数值（如"五十块五"→50.5）
        - 隐含意图: 若消息未明确提及"记录"但暗示有收支行为，也应识别意图

        ## 输出格式
        以JSON格式返回，包含以下字段：
        - "has_intent": true/false（是否存在记账意图）
        - "type": "income"/"expense"（若有意图）
        - "amount": 数值（若有意图）
        - "date": "YYYY-MM-DD"（若有意图）
        - "time": "HH:MM"（若有意图且提及时间）
        - "description": 字符串（若有意图）
        - "category": 字符串（若有意图）
        - "confidence": 0-1之间的数值（提取信息的确信度）
        - "missing_fields": []（缺失的必要字段列表，如缺少金额等）

        ## 分析对象
        用户消息: "{message_content}"
        """

        print("调用AI API进行财务信息提取...")
        # print(f"API密钥: {openai.api_key[:5]}...")
        print(f"API基础URL: {openai.api_base}")

        response = openai.ChatCompletion.create(
            model=use_model,
            messages=[
                {
                    "role": "system",
                    "content": "你是一个专业的财务信息提取助手，精通中文财务语言处理，擅长从自然语言中识别记账意图并提取关键财务实体。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )

        print("API调用成功!")
        result = response.choices[0].message.content
        print(f"API原始返回: {result[:100]}...")

        # 解析JSON响应
        import json
        import re

        # 尝试从响应中提取JSON部分
        json_match = re.search(r"({[\s\S]*})", result)
        if json_match:
            json_str = json_match.group(1)
            print(f"提取的JSON字符串: {json_str[:100]}...")

            extracted_data = json.loads(json_str)
            print(f"解析后的数据: {extracted_data}")

            # 如果没有记账意图，返回None
            if not extracted_data.get("has_intent", False):
                print("未检测到记账意图")
                print("***** 财务信息提取完成: 无记账意图 *****\n")
                return None

            # 移除has_intent字段，保持与前端接口兼容
            if "has_intent" in extracted_data:
                del extracted_data["has_intent"]

            print(f"成功提取财务信息: {extracted_data}")
            print("***** 财务信息提取完成: 成功 *****\n")
            return extracted_data
        else:
            # 如果无法提取JSON，返回None
            print("无法从API响应中提取JSON数据")
            print("***** 财务信息提取完成: 提取JSON失败 *****\n")
            return None

    except Exception as e:
        print(f"***** 财务信息提取过程中发生错误 *****")
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {str(e)}")
        import traceback

        print(f"错误堆栈:\n{traceback.format_exc()}")
        print("***** 错误信息结束 *****\n")
        return None


def get_ai_response(user_message: str, personality_id: Optional[int], db: Session):
    """
    Generate AI response using the specified personality.

    Args:
        user_message: The user's message
        personality_id: The ID of the AI personality to use
        db: Database session

    Returns:
        str: AI generated response
    """
    print("\n------ 开始生成AI回复 ------")
    print(f"用户消息: {user_message}")
    print(f"指定的AI性格ID: {personality_id}")

    try:
        # 从助手系统获取对应的提示词
        system_prompt, metadata = get_assistant(personality_id)
        print(f"使用AI性格: {metadata['name']} ({metadata['personality_type']})")
        print(f"系统提示词: {system_prompt[:50]}...")

        print("调用AI API...")
        # print(f"API密钥: {openai.api_key[:5]}...")
        print(f"API基础URL: {openai.api_base}")

        # Call the API
        response = openai.ChatCompletion.create(
            model=use_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.7,
            max_tokens=1000,
        )

        print("API调用成功!")
        content = response.choices[0].message.content
        if content is not None:
            print(f"获取到的回复: {content[:50]}...")
        else:
            print("警告: API返回的content为None")
        print("------ AI回复生成完成 ------\n")
        return content

    except Exception as e:
        print(f"------ 生成AI回复时发生错误 ------")
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {str(e)}")
        import traceback

        print(f"错误堆栈:\n{traceback.format_exc()}")
        print("------ 错误信息结束 ------\n")
        return "抱歉，我现在无法正常回应，请稍后再试。"


# Endpoints
@router.post("/", response_model=ChatResponse)
def create_chat_message(
    message: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    print("\n\n========= 接收到聊天请求 =========")
    print(f"用户: {current_user.username}, 消息内容: {message.content}")
    print(f"AI性格ID: {message.personality_id}")

    try:
        # Save the user message to the database
        print("保存用户消息到数据库...")
        db_user_message = ChatMessage(
            user_id=current_user.id,
            content=message.content,
            is_user=True,
            personality_id=message.personality_id,
        )
        db.add(db_user_message)
        db.commit()
        db.refresh(db_user_message)
        print(f"用户消息已保存，ID: {db_user_message.id}")

        # Extract financial information if present
        print("开始提取财务信息...")
        extracted_info = extract_financial_data(message.content)
        needs_confirmation = extracted_info is not None
        print(f"财务信息提取结果: {extracted_info}")
        print(f"需要确认: {needs_confirmation}")

        # Generate AI response
        print("正在生成AI回复...")
        ai_response_content = get_ai_response(
            message.content, message.personality_id, db
        )
        print(f"AI回复内容: {ai_response_content[:100]}...")

        # Save AI response to database
        print("保存AI回复到数据库...")
        db_ai_message = ChatMessage(
            user_id=current_user.id,
            content=ai_response_content,
            is_user=False,
            personality_id=message.personality_id,
        )
        db.add(db_ai_message)
        db.commit()
        db.refresh(db_ai_message)
        print(f"AI回复已保存，ID: {db_ai_message.id}")

        print("========= 请求处理完成 =========\n")
        return ChatResponse(
            message=MessageResponse(
                id=db_ai_message.id,
                content=db_ai_message.content,
                personality_id=db_ai_message.personality_id,
                user_id=db_ai_message.user_id,
                is_user=db_ai_message.is_user,
                created_at=db_ai_message.created_at,
            ),
            extracted_info=extracted_info,
            needs_confirmation=needs_confirmation,
        )

    except Exception as e:
        print(f"========= 请求处理出错 =========")
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {str(e)}")
        import traceback

        print(f"错误堆栈:\n{traceback.format_exc()}")
        print("========= 错误信息结束 =========\n")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/history", response_model=List[MessageResponse])
def get_chat_history(
    limit: int = 50,
    skip: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == current_user.id)
        .order_by(ChatMessage.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return messages


@router.get("/personalities", response_model=List[dict])
def get_ai_personalities(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    # 使用新的模块获取所有助手元数据
    result = get_all_assistants_metadata()
    return result


@router.post("/confirm-transaction", response_model=Dict[str, Any])
def confirm_transaction(
    confirmation: TransactionConfirmation,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    print("\n\n========= 接收到交易确认请求 =========")
    print(f"消息ID: {confirmation.message_id}, 确认: {confirmation.confirm}")

    try:
        if confirmation.confirm:
            print("用户确认，创建交易...")

            # 特殊处理：如果message_id为-1，表示这是一个直接提交的交易，跳过消息验证
            if confirmation.message_id != -1:
                # 获取聊天消息
                chat_message = (
                    db.query(ChatMessage)
                    .filter(ChatMessage.id == confirmation.message_id)
                    .first()
                )
                if not chat_message:
                    raise HTTPException(
                        status_code=404, detail="Chat message not found"
                    )

                # 确认聊天消息属于当前用户
                if chat_message.user_id != current_user.id:
                    raise HTTPException(
                        status_code=403,
                        detail="Not authorized to confirm this transaction",
                    )
            else:
                print("使用特殊ID -1，跳过消息验证")

            # 构建交易数据
            transaction_data = {
                "user_id": current_user.id,
                "amount": confirmation.amount,
                "description": confirmation.description,
                "category": confirmation.category,
            }

            # 设置类型 - 小写处理并添加详细日志
            print(f"接收到的交易类型: '{confirmation.type}'")

            # 确保类型为字符串并转换为小写
            type_lower = str(confirmation.type).lower() if confirmation.type else ""
            print(f"处理后的类型(小写): '{type_lower}'")

            # 映射到正确的枚举值
            if type_lower == "income":
                transaction_type = TransactionType.INCOME
                print(f"映射为 TransactionType.INCOME: {TransactionType.INCOME}")
            elif type_lower == "expense":
                transaction_type = TransactionType.EXPENSE
                print(f"映射为 TransactionType.EXPENSE: {TransactionType.EXPENSE}")
            else:
                error_msg = f"无效的交易类型: '{confirmation.type}'"
                print(error_msg)
                raise HTTPException(status_code=400, detail=error_msg)

            transaction_data["type"] = transaction_type

            # 处理日期和时间
            if confirmation.date:
                try:
                    print(f"处理日期: {confirmation.date}")
                    transaction_date = datetime.strptime(
                        confirmation.date, "%Y-%m-%d"
                    ).date()
                    # 使用正确的字段名称transaction_date而不是date
                    transaction_data["transaction_date"] = datetime.combine(
                        transaction_date, datetime.min.time()
                    )
                    print(
                        f"设置transaction_date为: {transaction_data['transaction_date']}"
                    )
                except ValueError as e:
                    error_msg = f"无效的日期格式: {str(e)}"
                    print(error_msg)
                    raise HTTPException(status_code=400, detail=error_msg)

            if confirmation.time:
                try:
                    print(f"处理时间: {confirmation.time}")
                    time_obj = datetime.strptime(confirmation.time, "%H:%M").time()
                    # 使用正确的字段名称transaction_time而不是time
                    if "transaction_date" in transaction_data:
                        # 如果已经有日期，则将时间合并到同一个字段中
                        date_part = transaction_data["transaction_date"].date()
                        transaction_data["transaction_time"] = datetime.combine(
                            date_part, time_obj
                        )
                    else:
                        # 如果没有日期，则使用当前日期
                        transaction_data["transaction_time"] = datetime.combine(
                            datetime.now().date(), time_obj
                        )
                    print(
                        f"设置transaction_time为: {transaction_data['transaction_time']}"
                    )
                except ValueError as e:
                    error_msg = f"无效的时间格式: {str(e)}"
                    print(error_msg)
                    raise HTTPException(status_code=400, detail=error_msg)

            # 创建交易
            transaction = Transaction(**transaction_data)
            db.add(transaction)
            db.commit()
            db.refresh(transaction)

            print(f"交易已创建，ID: {transaction.id}")

            # 准备返回数据
            print("准备返回交易数据...")

            # 为了调试，输出transaction对象的所有属性
            print(f"交易ID: {transaction.id}")
            print(f"交易金额: {transaction.amount}")
            print(f"交易类型: {transaction.type}")
            print(f"交易描述: {transaction.description}")
            print(f"交易分类: {transaction.category}")
            print(f"交易日期: {transaction.transaction_date}")
            print(f"交易时间: {transaction.transaction_time}")

            # 构建返回数据，使用正确的属性名
            result = {
                "confirmed": True,
                "transaction": {
                    "id": transaction.id,
                    "amount": transaction.amount,
                    "type": str(transaction.type.value) if transaction.type else None,
                    "description": transaction.description,
                    "category": transaction.category,
                    "date": (
                        transaction.transaction_date.isoformat()
                        if transaction.transaction_date
                        else None
                    ),
                    "time": (
                        transaction.transaction_time.isoformat()
                        if transaction.transaction_time
                        else None
                    ),
                },
            }
            print("响应数据构建完成")

        else:
            print("用户拒绝，不创建交易")
            result = {"confirmed": False}

        print("========= 交易确认请求处理完成 =========\n")
        return result

    except HTTPException:
        raise

    except Exception as e:
        print(f"========= 交易确认请求处理出错 =========")
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {str(e)}")
        import traceback

        print(f"错误堆栈:\n{traceback.format_exc()}")
        print("========= 错误信息结束 =========\n")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/image-recognition", response_model=Dict[str, Any])
async def recognize_image(
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    接收用户上传的交易凭证图片，进行OCR识别并提取交易信息
    """
    print("\n\n========= 接收到图片识别请求 =========")
    print(f"用户: {current_user.username}")
    print(f"文件名: {image.filename}")

    try:
        # 创建临时目录存储上传的图片
        temp_dir = os.path.join("temp", "uploads")
        os.makedirs(temp_dir, exist_ok=True)

        # 生成唯一文件名
        file_extension = os.path.splitext(image.filename)[1]
        temp_file_name = f"{uuid.uuid4()}{file_extension}"
        temp_file_path = os.path.join(temp_dir, temp_file_name)

        # 保存上传的图片
        print(f"保存图片到临时路径: {temp_file_path}")
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)

        # 读取图片并转换为base64编码用于API调用
        with open(temp_file_path, "rb") as image_file:
            encoded_image = base64.b64encode(image_file.read()).decode("utf-8")

        # 调用AI API提取图片中的交易信息
        print("调用AI API识别图片中的交易信息...")

        try:
            # 构建提示词，要求AI提取图片中的交易信息
            prompt = """
            请分析这张交易凭证/收据图片，提取以下关键财务信息:
            1. 交易类型: "income"(收入) 或 "expense"(支出)
            2. 交易金额: 以数字形式表示
            3. 交易日期和时间: 格式化为YYYY-MM-DD和HH:MM
            4. 交易描述: 交易的目的、项目或购买的商品/服务
            5. 交易分类: 例如"餐饮美食"、"交通出行"、"服饰美容"、"日用百货"等

            请按以下JSON格式返回结果：
            {
              "type": "expense",
              "amount": 123.45,
              "date": "2023-05-20",
              "time": "14:30",
              "description": "在XX超市购买日用品",
              "category": "日用百货"
            }

            如果无法识别某些字段，请提供你能提取的信息，缺失字段可设为null或合理默认值。
            如果无法确定是收入还是支出，请根据图像中的上下文(如购物小票通常是支出)进行最佳猜测。
            """

            response = openai.ChatCompletion.create(
                model=use_model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的交易凭证识别助手，擅长从图片中提取财务信息。",
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{encoded_image}"
                                },
                            },
                        ],
                    },
                ],
                temperature=0.1,
            )

            print("API调用成功!")
            result = response.choices[0].message.content
            print(f"API原始返回: {result[:200]}...")

            # 解析JSON响应
            import json
            import re

            # 尝试从响应中提取JSON部分
            json_match = re.search(r"({[\s\S]*})", result)
            if json_match:
                json_str = json_match.group(1)
                print(f"提取的JSON字符串: {json_str[:100]}...")

                extracted_data = json.loads(json_str)
                print(f"解析后的数据: {extracted_data}")

                # 生成AI响应消息
                ai_message = (
                    f"我已从图片中识别出以下交易信息：\n"
                    f"类型：{'收入' if extracted_data.get('type') == 'income' else '支出'}\n"
                    f"金额：¥{extracted_data.get('amount')}\n"
                    f"日期：{extracted_data.get('date')}\n"
                    f"描述：{extracted_data.get('description')}\n"
                    f"分类：{extracted_data.get('category')}\n\n"
                    f"请核对以上信息，确认无误后可点击确认按钮进行记账。"
                )

                # 保存AI消息到数据库
                db_ai_message = ChatMessage(
                    user_id=current_user.id,
                    content=ai_message,
                    is_user=False,
                )
                db.add(db_ai_message)
                db.commit()
                db.refresh(db_ai_message)

                # 删除临时文件
                os.remove(temp_file_path)

                print("图片识别完成，返回提取的交易信息")
                return {
                    "message": ai_message,
                    "extracted_info": extracted_data,
                    "needs_confirmation": True,
                }
            else:
                error_msg = "无法从API响应中提取JSON数据"
                print(error_msg)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_msg
                )

        except Exception as e:
            print(f"图片识别过程中出错: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"图片识别失败: {str(e)}",
            )
    except Exception as e:
        print(f"处理图片上传请求时出错: {str(e)}")
        import traceback

        print(f"错误堆栈:\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"处理图片失败: {str(e)}",
        )




@router.post("/batch-import", response_model=Dict[str, Any])
async def process_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    接收用户上传的EXCEL表格，提取交易信息
    """
    print("\n\n========= 接收到EXCEL处理请求 =========")
    print(f"用户: {current_user.username}")
    print(f"文件名: {file.filename}")

    try:
        # 创建临时目录存储上传的文档
        temp_dir = os.path.join("temp", "uploads")
        os.makedirs(temp_dir, exist_ok=True)

        # 生成唯一文件名
        file_extension = os.path.splitext(file.filename)[1]
        temp_file_name = f"{uuid.uuid4()}{file_extension}"
        temp_file_path = os.path.join(temp_dir, temp_file_name)

        # 保存上传的EXCEL文件
        print(f"保存文件到临时路径: {temp_file_path}")
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        #将EXCEL文件转换为文本，用于AI处理
        file_content = read_file_batch(temp_file_path)

        print(f"成功读取文件内容，长度: {len(file_content)}字符")

        print("调用AI API识别文件的交易信息...")
        max_len_limit = 6000  # 每次API调用的最大字符数，太长AI返回信息会被截断
        all_extracted_data = []  # 存储所有提取的数据

        # 分块处理文件内容
        for i in range(0, len(file_content), max_len_limit):
            start_chunk = max(i-20,0) #max_len_limit会截断EXCEL信息，所以设置一个20字符的缓冲区
            end_chunk = min(i+max_len_limit, len(file_content))
            chunk = file_content[start_chunk:end_chunk]
            print(f"正在处理第 {i // max_len_limit + 1} 块内容，长度: {len(chunk)}字符")
            try:
                # 构建提示词
                prompt = """
                    # 指令说明
                    请严格按以下步骤处理输入文件：
                    --- 第一步：文件类型验证 ---
                    1. 若输入文件明显不是财务类数据（如纯文本、图片描述等），直接返回：[]，注意不是返回[]```
                    --- 第二步：数据提取规则 ---
                    2. 仅当确认是财务数据时，按以下规则提取：
                    交易类型(type):
                        必须为 "income"(收入) 或 "expense"(支出)
                    金额(amount):
                        必须为数字（允许小数）
                        金额前带符号的需自动修正（如"-15" → 15，"+"可保留）
                    日期(date):
                        格式必须为 YYYY-MM-DD
                        原始格式为"20250509"需转为"2025-05-09"
                    时间(time):
                        格式必须为 HH:MM（24小时制）
                        缺失时可设为 "00:00"
                    分类(category):
                        从预定义列表选择：[餐饮美食, 交通出行, 服饰美容, 日用百货, 住房物业, 医疗健康, 文教娱乐, 
                            人情往来, 工资薪酬, 投资理财, 奖金, 退款, 兼职收入, 租金收入, 礼金收入, 中奖收入, 
                            意外所得, 其他收入, 其他支出, 未分类]  
                        无法归类时设为 null
                    --- 第三步：输出规范 ---
                    3. 请直接输出纯JSON格式，不要包含任何Markdown代码块符号或额外说明，示例：
                    [
                      {
                        "type": "expense",
                        "amount": 14.00,
                        "date": "2025-06-09",
                        "time": "12:38",
                        "description": "东三港式烧腊25",
                        "category": "餐饮美食"
                      },
                      {
                        "type": "income",
                        "amount": 9.5,
                        "date": "2025-06-05",
                        "time": "12:23",
                        "description": "二维码收款",
                        "category": null
                      }
                    ]
                    4.错误示例:```json
                """
                response = openai.ChatCompletion.create(
                    model=os.getenv('AI_MODEL'),
                    messages=[
                        {
                            "role": "system",
                            "content": "你是一个专业的交易凭证识别助手，擅长从文件中提取财务信息。",
                        },
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "text", "text": chunk}
                            ],
                        },
                    ],
                    temperature=0.1,
                    stream=False,
                    top_p=0.7
                )
                print(f"第 {i // max_len_limit + 1} 块API调用成功!")
                result = response.choices[0].message.content
                print(f"第 {i // max_len_limit + 1} 块API原始返回: {result}")
                print("---------------------------------")

                # 解析JSON响应
                try:
                    # 尝试去除 Markdown 代码块标记
                    cleaned_result = re.sub(r'```(?:json)?\n?|\n```', '', result).strip()
                    extracted_data = json.loads(cleaned_result )
                    if not isinstance(extracted_data, list):
                        print(f"第 {i // max_len_limit + 1} 块返回数据不是有效的列表格式")
                        continue

                    all_extracted_data.extend(extracted_data)
                    print(f"第 {i // max_len_limit + 1} 块成功提取{len(extracted_data)}条交易记录")

                except Exception as e:
                    print(f"第 {i // max_len_limit + 1} 块解析JSON响应时出错: {str(e)}")
                    continue

            except Exception as e:
                print(f"第 {i // max_len_limit + 1} 块API调用失败: {str(e)}")
                continue

        # 处理最终结果
        if not all_extracted_data:
            ai_message = "未能从文件中识别出有效的交易记录，请检查文件内容或尝试其他文件。"
        else:
            # 生成AI响应消息
            ai_message = (
                f"我已从文件中识别出{len(all_extracted_data)}条交易记录。"
            )

        # 保存AI消息到数据库
        # db_ai_message = ChatMessage(
        #     user_id=current_user.id,
        #     content=ai_message,
        #     is_user=False,
        # )
        # db.add(db_ai_message)
        # db.commit()
        # db.refresh(db_ai_message)

        # 删除临时文件
        os.remove(temp_file_path)

        print(f"文件识别完成，共提取 {len(all_extracted_data)} 条交易信息")
        return {
            "message": ai_message,
            "extracted_info": all_extracted_data,
            "needs_confirmation": True,
        }

    except Exception as e:
        print(f"处理文件上传请求时出错: {str(e)}")
        import traceback

        print(f"错误堆栈:\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"处理文件失败: {str(e)}",
        )


@router.post("/batch-confirm", response_model=Dict[str, Any])
async def batch_import(
    request_data: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    批量确认并导入交易记录
    """
    print("\n\n========= 接收到批量确认请求 =========")
    print(f"请求数据条数: {len(request_data.get('transactions', []))}")

    try:
        # 验证请求数据
        if not request_data.get("confirmed", False):
            return {
                "message": "批量导入未确认",
                "imported_count": 0,
                "skipped_count": 0,
                "results": []
            }

        transactions = request_data.get("transactions", [])
        if not transactions:
            return {
                "message": "没有可导入的交易记录",
                "imported_count": 0,
                "skipped_count": 0,
                "results": []
            }

        imported_count = 0
        skipped_count = 0
        results = []
        batch_errors = []

        # 使用事务处理批量导入
        try:
            for idx, transaction_data in enumerate(transactions, start=1):
                try:
                    # 数据预处理
                    processed_data = {
                        "message_id": -1,  # 批量导入特殊标识
                        "confirm": True,
                        "type": (transaction_data.get("type") or "").lower(),
                        "amount": float(transaction_data.get("amount", 0)),
                        "description": transaction_data.get("description", ""),
                        "category": transaction_data.get("category", "未分类"),
                        "date": transaction_data.get("date"),
                        "time": transaction_data.get("time", "00:00")
                    }
                    # 日期格式处理
                    if processed_data["date"] and "T" in processed_data["date"]:
                        processed_data["date"] = processed_data["date"].split("T")[0]
                    # 验证必填字段
                    if processed_data["amount"] <= 0:
                        raise ValueError("金额无效")
                    # 创建确认对象
                    confirmation = TransactionConfirmation(**processed_data)
                    # 调用单条确认接口
                    result = confirm_transaction(confirmation, db, current_user)

                    if result["confirmed"]:
                        imported_count += 1
                        results.append({
                            "status": "success",
                            "transaction_id": result["transaction"]["id"],
                            "data": transaction_data,
                            "message": "导入成功"
                        })
                    else:
                        skipped_count += 1
                        results.append({
                            "status": "skipped",
                            "data": transaction_data,
                            "message": "交易未确认"
                        })
                except Exception as e:
                    skipped_count += 1
                    error_msg = f"第{idx}条记录错误: {str(e)}"
                    results.append({
                        "status": "failed",
                        "data": transaction_data,
                        "message": error_msg
                    })
                    batch_errors.append(error_msg)
                    print(f"跳过无效记录: {error_msg}")

            db.commit()  # 提交整个批量事务

        except Exception as e:
            db.rollback()  # 出错时回滚
            raise HTTPException(
                status_code=400,
                detail=f"批量导入过程中出错: {str(e)}"
            )
        # 构建响应
        response = {
            "message": f"批量导入完成，成功导入{imported_count}条，跳过{skipped_count}条",
            "imported_count": imported_count,
            "skipped_count": skipped_count,
            "results": results
        }

        if batch_errors:
            response["batch_errors"] = batch_errors[:10]  # 最多返回10条错误

        print(f"批量导入结果: {response['message']}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        print(f"批量导入过程中出错: {str(e)}")
        import traceback
        print(f"错误堆栈:\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"批量导入失败: {str(e)}"
        )


import os
import re
import pandas as pd
def read_file_batch(file_path):
    """
    读取文件并转换为AI处理所需的标准化文本格式
    返回: 纯文本字符串 (CSV格式)
    """
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()
    if ext in ['.txt', '.csv', '.log']:
        # 文本文件，尝试多种编码
        encodings = ['utf-8-sig', 'utf-8', 'gbk', 'gb18030']
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        raise ValueError(f"无法解码文本文件 {file_path}")

    elif ext in ['.xlsx', '.xls']:
        try:
            df = pd.read_excel(file_path)  # 读取整个Excel文件
            return df.to_csv(index=False)
        except Exception as e:
            raise ValueError(f"无法读取Excel文件 {file_path}: {str(e)}")
    else:
        raise ValueError(f"不支持的文件类型: {ext}")

