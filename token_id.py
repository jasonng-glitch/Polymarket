"""
获取所有可交易市场的 token_id
包含市场名称和市场ID
"""

import os
import requests
from dotenv import load_dotenv
from py_clob_client.client import ClobClient

# 加载环境变量
load_dotenv()

# 配置参数
HOST = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon mainnet
PRIVATE_KEY = os.getenv("POLYMARKET_PRIVATE_KEY")


def create_client() -> ClobClient:
    """创建 ClobClient 实例"""
    if not PRIVATE_KEY:
        raise ValueError("POLYMARKET_PRIVATE_KEY 环境变量未设置，请检查 .env 文件")
    
    client = ClobClient(
        host=HOST,
        chain_id=CHAIN_ID,
        key=PRIVATE_KEY
    )
    
    # 获取 API 凭证（如果需要）
    try:
        api_creds = client.create_or_derive_api_creds()
        client.set_api_creds(api_creds)
    except Exception as e:
        print(f"警告: 无法获取 API 凭证: {e}")
        print("继续尝试获取市场信息...")
    
    return client


def update_market_names(client: ClobClient, tokens: list) -> list:
    """
    更新 token 列表中的市场名称
    通过 get_market() 方法获取每个市场的详细信息
    
    Args:
        client: ClobClient 实例
        tokens: token 列表
        
    Returns:
        更新后的 token 列表
    """
    print(f"\n更新市场名称...")
    unique_market_ids = set()
    market_names_cache = {}
    
    # 收集所有唯一的 market_id
    for token in tokens:
        market_id = token.get("market_id", "")
        if market_id and market_id not in unique_market_ids:
            unique_market_ids.add(market_id)
    
    print(f"找到 {len(unique_market_ids)} 个唯一市场，开始获取市场名称...")
    
    # 为每个市场获取名称
    total = len(unique_market_ids)
    for i, market_id in enumerate(unique_market_ids, 1):
        # 每10个显示一次进度，或者每100个显示详细进度
        if i % 10 == 0 or i == 1:
            print(f"  进度: {i}/{total} ({i*100//total}%)", end="\r")
        
        try:
            market_detail = client.get_market(market_id)
            if isinstance(market_detail, dict):
                market_name = (
                    market_detail.get("question") or
                    market_detail.get("title") or
                    market_detail.get("slug") or
                    market_detail.get("name") or
                    ""
                )
                if market_name:
                    market_names_cache[market_id] = market_name
        except Exception as e:
            # 静默处理错误，继续处理下一个市场
            pass
    
    print()  # 换行
    
    print(f"✓ 成功获取 {len(market_names_cache)} 个市场的名称")
    
    # 更新 token 列表中的市场名称
    updated_count = 0
    for token in tokens:
        market_id = token.get("market_id", "")
        if market_id in market_names_cache:
            if token.get("market_name") == "未知市场":
                token["market_name"] = market_names_cache[market_id]
                updated_count += 1
    
    print(f"✓ 更新了 {updated_count} 个 token 的市场名称")
    
    return tokens


def get_all_tradable_tokens(client: ClobClient) -> list:
    """
    获取所有可交易市场的 token_id 列表
    
    Args:
        client: ClobClient 实例
        
    Returns:
        包含市场信息的列表，每个元素包含：
        - market_name: 市场名称
        - market_id: 市场ID (condition_id)
        - token_id: Token ID
        - outcome: 结果 (Yes/No 等)
    """
    all_tokens = []
    
    try:
        # 方法1: 优先使用 Gamma API 获取 Crypto 分类的市场
        print("尝试通过 Gamma API 获取 Crypto 分类的市场...")
        markets = []
        
        try:
            gamma_url = "https://gamma-api.polymarket.com/markets"
            
            # 获取 Crypto 分类的市场
            params = {
                "category": "crypto",
                "limit": 1000,
                "active": "true"
            }
            
            response = requests.get(gamma_url, params=params, timeout=30)
            if response.status_code == 200:
                gamma_data = response.json()
                gamma_markets = gamma_data.get("data", [])
                print(f"  ✓ 从 Gamma API 获取到 {len(gamma_markets)} 个 Crypto 市场")
                markets = gamma_markets
            else:
                print(f"  Gamma API 返回错误: {response.status_code}")
        except Exception as e:
            print(f"  通过 Gamma API 获取失败: {e}")
            print("  尝试使用 get_simplified_markets() 获取...")
        
        # 方法2: 如果没有从 Gamma API 获取到数据，使用 get_simplified_markets()
        if not markets:
            print("\n尝试使用 get_simplified_markets() 获取市场...")
            try:
                # 只获取第一页，不使用分页（避免重复和无限循环）
                markets_data = client.get_simplified_markets()
                
                # 处理不同的响应格式
                if isinstance(markets_data, dict):
                    markets = markets_data.get("data", markets_data.get("markets", []))
                    total = markets_data.get("total", markets_data.get("count"))
                    if total:
                        print(f"  获取到 {len(markets)} 个市场 (总计: {total})")
                    else:
                        print(f"  获取到 {len(markets)} 个市场")
                elif isinstance(markets_data, list):
                    markets = markets_data
                    print(f"  获取到 {len(markets)} 个市场")
                else:
                    markets = []
                    print(f"  未获取到市场数据")
            except Exception as e:
                print(f"  get_simplified_markets() 失败: {e}")
        
        if markets:
            print(f"\n  共获取到 {len(markets)} 个市场，开始处理...")
            
            for market in markets:
                if isinstance(market, dict):
                    market_id = market.get("condition_id", market.get("market", ""))
                    
                    # 尝试从多个字段获取市场名称（只使用简化数据，不调用 API）
                    market_name = (
                        market.get("question") or 
                        market.get("title") or 
                        market.get("slug") or 
                        market.get("name") or
                        ""
                    )
                    
                    # 获取 tokens（只使用简化数据）
                    tokens = market.get("tokens", [])
                    print(market)
                    for token in tokens:
                        if isinstance(token, dict):
                            token_id = token.get("token_id", "")
                            outcome = token.get("outcome", "")
                            
                            # 处理 token_id 格式
                            if isinstance(token_id, int):
                                token_id = hex(token_id)
                            elif isinstance(token_id, str) and token_id.isdigit():
                                token_id = hex(int(token_id))
                            
                            if token_id:
                                all_tokens.append({
                                    "market_name": market_name if market_name else "未知市场",
                                    "market_id": market_id,
                                    "token_id": token_id,
                                    "outcome": outcome
                                })
            
            if all_tokens:
                print(f"✓ 成功获取 {len(all_tokens)} 个 token_id")
                # 检查是否需要更新市场名称
                needs_update = any(token.get("market_name") == "未知市场" for token in all_tokens)
                if needs_update:
                    print("\n检测到部分市场名称为'未知市场'，开始更新...")
                    all_tokens = update_market_names(client, all_tokens)
                else:
                    print("✓ 所有市场名称已正确获取")
                return all_tokens
        
    except Exception as e:
        print(f"获取市场失败: {e}")
        import traceback
        traceback.print_exc()
    
    return all_tokens


def update_existing_json_file(filename: str = "tradable_tokens.json"):
    """
    更新现有 JSON 文件中的市场名称
    
    Args:
        filename: JSON 文件名
    """
    import json
    
    print("=" * 70)
    print("更新现有 JSON 文件中的市场名称")
    print("=" * 70)
    
    try:
        # 读取现有文件
        print(f"\n1. 读取文件: {filename}...")
        with open(filename, "r", encoding="utf-8") as f:
            tokens = json.load(f)
        print(f"   ✓ 读取了 {len(tokens)} 个 token")
        
        # 创建客户端
        print("\n2. 初始化客户端...")
        client = create_client()
        print(f"   ✓ 客户端初始化成功")
        
        # 更新市场名称
        print("\n3. 更新市场名称...")
        tokens = update_market_names(client, tokens)
        
        # 保存更新后的文件
        print(f"\n4. 保存更新后的文件...")
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(tokens, f, indent=2, ensure_ascii=False)
        print(f"   ✓ 已保存到 {filename}")
        
        # 显示更新后的示例
        print("\n更新后的前 5 个示例:")
        for i, token in enumerate(tokens[:5], 1):
            print(f"\n  {i}. 市场名称: {token['market_name']}")
            print(f"     市场ID: {token['market_id']}")
            print(f"     Token ID: {token['token_id']}")
            print(f"     结果: {token['outcome']}")
        
        print("\n" + "=" * 70)
        print("完成")
        print("=" * 70)
        
    except FileNotFoundError:
        print(f"\n❌ 文件 {filename} 不存在")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()


def main():
    """主函数"""
    print("=" * 70)
    print("获取所有可交易市场的 token_id")
    print("=" * 70)
    
    try:
        # 创建客户端
        print("\n1. 初始化客户端...")
        client = create_client()
        print(f"   ✓ 客户端初始化成功")
        print(f"   ✓ 钱包地址: {client.get_address()}")
        
        # 获取所有 token_id
        print("\n2. 获取所有可交易市场的 token_id...")
        tokens = get_all_tradable_tokens(client)
        
        if tokens:
            print(f"\n✓ 成功获取 {len(tokens)} 个 token_id")
            
            # 显示前几个示例
            print("\n前 5 个示例:")
            for i, token in enumerate(tokens[:5], 1):
                print(f"\n  {i}. 市场名称: {token['market_name']}")
                print(f"     市场ID: {token['market_id']}")
                print(f"     Token ID: {token['token_id']}")
                print(f"     结果: {token['outcome']}")
            
            # 保存到文件（可选）
            print(f"\n3. 保存结果...")
            import json
            with open("tradable_tokens.json", "w", encoding="utf-8") as f:
                json.dump(tokens, f, indent=2, ensure_ascii=False)
            print(f"   ✓ 已保存到 tradable_tokens.json")
            
            # 返回列表格式
            print("\n" + "=" * 70)
            print("结果列表格式:")
            print("=" * 70)
            print(f"共 {len(tokens)} 个可交易的 token_id")
            print("\n列表格式示例:")
            print("[")
            for token in tokens[:3]:
                print(f"  {{")
                print(f"    'market_name': '{token['market_name']}',")
                print(f"    'market_id': '{token['market_id']}',")
                print(f"    'token_id': '{token['token_id']}',")
                print(f"    'outcome': '{token['outcome']}'")
                print(f"  }},")
            print("  ...")
            print("]")
            
        else:
            print("\n⚠️ 未能获取到任何 token_id")
            print("可能的原因:")
            print("  1. API 方法不可用")
            print("  2. 需要其他方式获取市场列表")
            print("  3. 网络连接问题")
        
        print("\n" + "=" * 70)
        print("完成")
        print("=" * 70)
        
        return tokens
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return []


if __name__ == "__main__":
    import sys
    
    # 如果提供了参数 "--update"，则更新现有文件
    if len(sys.argv) > 1 and sys.argv[1] == "--update":
        update_existing_json_file()
    else:
        tokens = main()

