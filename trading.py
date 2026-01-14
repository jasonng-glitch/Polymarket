"""
Polymarket 基础交易脚本,后面按需求做成专门自用的交易模块
"""

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs
from py_clob_client.order_builder.constants import BUY, SELL
import asyncio
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


def find_token_id(market_name: str = None, market_id: str = None, outcome: str = None) -> str:
    """
    从 tradable_tokens.json 中查找指定条件的 token_id（可选辅助函数）
    
    Args:
        market_name: 市场名称（可以是部分匹配）
        market_id: 市场ID（可以是部分匹配）
        outcome: 结果（可选，如 "No", "Yes"）
        
    Returns:
        token_id (hex 字符串) 或 None
    """
    try:
        import json
        with open("tradable_tokens.json", "r", encoding="utf-8") as f:
            tokens = json.load(f)
        
        for token in tokens:
            token_market_name = token.get("market_name", "").lower()
            token_market_id = token.get("market_id", "")
            token_outcome = token.get("outcome", "")
            
            name_match = not market_name or market_name.lower() in token_market_name
            id_match = not market_id or (token_market_id.startswith(market_id) if market_id.startswith("0x") else market_id in token_market_id)
            outcome_match = not outcome or token_outcome.upper() == outcome.upper()
            
            if name_match and id_match and outcome_match:
                return token.get("token_id", "")
        
        return None
    except Exception:
        return None


async def create_client() -> ClobClient:
    """
    创建并初始化 ClobClient
    
    Returns:
        ClobClient 实例
    """
    private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
    if not private_key:
        raise ValueError("POLYMARKET_PRIVATE_KEY 环境变量未设置，请检查 .env 文件")
    
    host = "https://clob.polymarket.com"
    chain_id = 137  # Polygon mainnet
    
    # 创建客户端并获取 API 凭证
    client = ClobClient(
        host=host,
        chain_id=chain_id,
        key=private_key
    )
    
    # 获取或创建 API 凭证
    api_creds = client.create_or_derive_api_creds()
    
    # 创建带凭证的客户端
    client_with_creds = ClobClient(
        host=host,
        chain_id=chain_id,
        key=private_key,
        creds=api_creds,
        signature_type=0
    )
    
    return client_with_creds


async def place_order(
    client: ClobClient,
    token_id: str,
    side: str,
    price: float,
    size: float
) -> dict:
    """
    下单
    
    Args:
        client: ClobClient 实例
        token_id: Token ID (hex 字符串)
        side: "BUY" 或 "SELL"
        price: 价格 (0-1 之间)
        size: 数量
        
    Returns:
        订单响应字典
    """
    # 参数验证
    if price <= 0 or price > 1:
        raise ValueError(f"价格必须在 0-1 之间，当前值: {price}")
    if size <= 0:
        raise ValueError(f"数量必须大于 0，当前值: {size}")
    if side.upper() not in {"BUY", "SELL"}:
        raise ValueError(f"方向必须是 BUY 或 SELL，当前值: {side}")
    
    # 处理 token_id 格式
    if isinstance(token_id, int):
        token_id = hex(token_id)
    elif isinstance(token_id, str) and token_id.isdigit():
        token_id = hex(int(token_id))
    elif not isinstance(token_id, str) or not token_id.startswith("0x"):
        raise ValueError(f"token_id 格式不正确: {token_id}")
    
    # 创建订单参数
    order_args = OrderArgs(
        token_id=token_id,
        price=price,
        size=size,
        side=BUY if side.upper() == "BUY" else SELL
    )
    
    # 创建并提交订单
    response = await client.create_and_post_order(order_args)
    
    return response


async def main():
    """主函数 - 示例用法"""
    # 创建客户端
    client = await create_client()
    
    # 示例：下单（请修改为实际的参数）
    # token_id = hex(83611158965142644032342884775225842534369349471539204930193487214925429417037)  # 替换为实际的 token ID
    token_id = "0x184d2a8baad696ea1c79dd126a5270287444fd310e7ab401b48cd6884c075d0c"
    response = await place_order(
        client=client,
        token_id=token_id,
        side="BUY",
        price=0.1,
        size=0.1
    )
    print(f"订单已提交! ID: {response.get('orderID', response)}")
    
    print("交易脚本已准备好")
    print("请取消注释示例代码并填入实际参数来下单")


if __name__ == "__main__":
    asyncio.run(main())
