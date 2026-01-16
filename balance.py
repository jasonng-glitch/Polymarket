"""
Polymarket 账户余额和持仓查询脚本
独立运行，检查账户余额和现有持仓
"""

import os
from dotenv import load_dotenv
from datetime import datetime
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import AssetType, BalanceAllowanceParams

# 加载环境变量
load_dotenv()

# 配置参数
HOST = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon mainnet
PRIVATE_KEY = os.getenv("POLYMARKET_PRIVATE_KEY")
SIGNATURE_TYPE = int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "1"))
FUNDER = os.getenv("POLYMARKET_FUNDER_E", "")


def create_client() -> ClobClient:
    """创建并初始化 ClobClient"""
    if not PRIVATE_KEY:
        raise ValueError("POLYMARKET_PRIVATE_KEY 环境变量未设置，请检查 .env 文件")
    
    client = ClobClient(
        host=HOST,
        key=PRIVATE_KEY,
        chain_id=CHAIN_ID,
        signature_type=SIGNATURE_TYPE,
        funder=FUNDER if FUNDER else None
    )
    
    # 获取或创建 API 凭证
    api_creds = client.create_or_derive_api_creds()
    client.set_api_creds(api_creds)
    
    return client


def timestamp_to_readable(timestamp) -> str:
    """
    将时间戳转换为可读时间格式
    
    Args:
        timestamp: Unix 时间戳（秒，整数/浮点数）或 ISO 8601 格式字符串
        
    Returns:
        格式化的时间字符串，例如: "2025-01-15 10:30:45"
    """
    if not timestamp and timestamp != 0:
        return "未知"
    
    # 如果是字符串，先尝试作为数字时间戳处理
    if isinstance(timestamp, str):
        # 先尝试转换为数字（可能是字符串格式的时间戳）
        try:
            ts = float(timestamp)
            # 如果是数字字符串，作为时间戳处理
            if ts > 0:
                dt = datetime.fromtimestamp(ts)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
        
        # 如果不是数字，尝试解析 ISO 8601 格式
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return f"无效时间格式 ({timestamp})"
    
    # 如果是数字，作为 Unix 时间戳处理
    try:
        ts = float(timestamp)
        
        # 检查是否是有效的时间戳范围（1970-2100年之间）
        # 秒级时间戳范围大约在 0 到 4102444800 之间
        if ts < 0:
            return f"无效时间戳 ({timestamp})"
        
        # 如果大于 1e12，可能是微秒时间戳，除以 1e6
        if ts > 1e12:
            ts = ts / 1_000_000
        # 如果大于 1e10，可能是毫秒时间戳，除以 1000
        elif ts > 1e10:
            ts = ts / 1000
        
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError, OverflowError) as e:
        return f"无效时间 ({timestamp}, 错误: {str(e)})"


def get_market_name(client: ClobClient, condition_id: str) -> str:
    """
    获取市场名称（可读名称）
    
    Args:
        client: ClobClient 实例
        condition_id: 市场 condition_id（market 字段）
        
    Returns:
        市场名称，如果获取失败则返回 condition_id 的缩写
    """
    if not condition_id:
        return "未知市场"
    
    try:
        # 尝试通过 get_market 获取市场信息
        market_info = client.get_market(condition_id)
        if isinstance(market_info, dict):
            # 尝试获取市场名称字段（根据实际 API 返回调整）
            name = market_info.get("question", market_info.get("title", market_info.get("slug", "")))
            if name:
                return name
    except Exception:
        pass
    
    # 如果无法获取，返回缩写的 condition_id
    if len(condition_id) > 20:
        return f"{condition_id[:10]}...{condition_id[-10:]}"
    return condition_id


def get_balance(client: ClobClient) -> dict:
    """
    获取账户余额 (USDC)
    
    Args:
        client: ClobClient 实例
        
    Returns:
        包含余额信息的字典
    """
    try:
        params = BalanceAllowanceParams(
            asset_type=AssetType.COLLATERAL,
            signature_type=SIGNATURE_TYPE
        )
        result = client.get_balance_allowance(params)
        
        if isinstance(result, dict):
            balance_raw = result.get("balance", "-1")
            allowances_raw = result["allowances"]

            balance_wei = float(balance_raw)
            
            # USDC 有 6 位小数
            balance_usdc = balance_wei / 1_000_000
            allowances_usdc = [float(allowance_wei) / 1_000_000 for allowance_wei in allowances_raw.values()]
            
            return {
                "balance_usdc": balance_usdc,
                "balance_raw": balance_raw,
                "allowance(CTF Exchange)": allowances_usdc[0],
                "allowance(Neg Risk CTF Exchange)": allowances_usdc[1],
                "allowance(Neg Risk Adapter)": allowances_usdc[2],
            }
        else:
            return {"error": f"意外的响应格式: {result}"}
            
    except Exception as e:
        return {"error": str(e)}


def normalize_position_data(data: dict, data_type: str = "unknown") -> dict:
    """
    将不同来源的持仓/订单数据转换为统一格式
    
    Args:
        data: 原始数据字典
        data_type: 数据类型 ("trade" 或 "order")
        
    Returns:
        统一格式的持仓数据字典
    """
    normalized = {
        "id": data.get("id", ""),
        "market": data.get("market", ""),
        "asset_id": data.get("asset_id", ""),
        "outcome": data.get("outcome", ""),
        "side": data.get("side", ""),
        "price": float(data.get("price", 0)),
        "size": float(data.get("size", data.get("original_size", data.get("size_matched", 0)))),
        "status": data.get("status", ""),
        "data_type": data_type,  # "trade" 或 "order"
        "trader_side": data.get("trader_side", data.get("side", "")),  # 交易者方向
        "fee_rate_bps": data.get("fee_rate_bps", 0),  # 费率（基点）
    }
    
    # 处理订单特有字段
    if data_type == "order":
        normalized["size_matched"] = float(data.get("size_matched", 0))
        normalized["original_size"] = float(data.get("original_size", 0))
        normalized["size_remaining"] = normalized["original_size"] - normalized["size_matched"]
        normalized["order_type"] = data.get("order_type", "")
        normalized["created_at"] = data.get("created_at", 0)
        normalized["expiration"] = data.get("expiration", 0)
    
    # 处理交易特有字段
    if data_type == "trade":
        normalized["size_matched"] = normalized["size"]  # 交易都是已成交的
        normalized["size_remaining"] = 0.0
        normalized["match_time"] = data.get("match_time", 0)
        normalized["match_time_readable"] = timestamp_to_readable(normalized["match_time"])
        normalized["transaction_hash"] = data.get("transaction_hash", "")
        normalized["taker_order_id"] = data.get("taker_order_id", "")
    
    # 通用字段
    normalized["owner"] = data.get("owner", "")
    normalized["maker_address"] = data.get("maker_address", "")
    normalized["last_update"] = data.get("last_update", data.get("match_time", data.get("created_at", 0)))
    normalized["last_update_readable"] = timestamp_to_readable(normalized["last_update"])
    
    # 如果是订单，也添加创建时间的可读格式
    if data_type == "order":
        normalized["created_at_readable"] = timestamp_to_readable(normalized.get("created_at", 0))
    
    return normalized


def get_positions(client: ClobClient) -> list:
    """
    获取当前持仓（统一格式）
    
    Args:
        client: ClobClient 实例
        
    Returns:
        统一格式的持仓列表（包含市场名称）
    """
    all_positions = []
    
    try:
        # 方法1: 获取已成交的交易（这些是实际的持仓）
        print("   获取已成交的交易（持仓）...")
        try:
            trades = client.get_trades()
            if trades:
                print(f"   找到 {len(trades)} 个已成交交易")
                for trade in trades:
                    if isinstance(trade, dict):
                        normalized = normalize_position_data(trade, "trade")
                        # 添加市场名称
                        market_id = normalized.get("market", "")
                        normalized["market_name"] = get_market_name(client, market_id)
                        all_positions.append(normalized)
        except Exception as e:
            print(f"   获取交易失败: {e}")
        
        # 方法2: 获取未完成的订单（这些是挂单，不是持仓）
        print("\n   获取未完成的订单（挂单）...")
        try:
            orders = client.get_orders()
            if orders:
                print(f"   找到 {len(orders)} 个订单")
                for order in orders:
                    if isinstance(order, dict):
                        status = order.get("status", "").upper()
                        # 只处理未完成的订单（挂单）
                        if status in ["LIVE", "OPEN", "PENDING"]:
                            normalized = normalize_position_data(order, "order")
                            # 添加市场名称
                            market_id = normalized.get("market", "")
                            normalized["market_name"] = get_market_name(client, market_id)
                            all_positions.append(normalized)
        except Exception as e:
            print(f"   获取订单失败: {e}")
        
        return all_positions
        
    except Exception as e:
        print(f"   获取持仓时出错: {e}")
        import traceback
        traceback.print_exc()
        return []


def main():
    """主函数"""
    print("=" * 70)
    print("POLYMARKET 账户余额和持仓查询")
    print("=" * 70)
    
    try:
        # 创建客户端
        print("\n1. 初始化客户端...")
        client = create_client()
        # print(dir(client))
        address = client.get_address()
        print(f"   ✓ 钱包地址: {address}")
        print(f"   ✓ 客户端初始化成功")
        
        # 获取余额
        print("\n2. 查询账户余额...")
        balance_info = get_balance(client)
        
        if "error" in balance_info:
            print(f"   ✗ 错误: {balance_info['error']}")
        else:
            print(f"   💰 USDC 余额: ${balance_info['balance_usdc']:.6f}")
            print(f"   🔓 授权额度: ${balance_info['allowance(CTF Exchange)']:.6f}, ${balance_info['allowance(Neg Risk CTF Exchange)']:.6f}, ${balance_info['allowance(Neg Risk Adapter)']:.6f}")
            # print(f"   原始余额: {balance_info['balance_raw']}")
            # print(f"   原始授权: {balance_info['allowance_raw']}")
        
        # 获取持仓
        print("\n3. 查询当前持仓...")
        positions = get_positions(client)
        
        show = 5
        if positions:
            # 分类显示
            trades = [p for p in positions if p.get("data_type") == "trade"]
            orders = [p for p in positions if p.get("data_type") == "order"]
            
            if trades:
                print(f"\n   📜 历史订单 ({len(trades)} 个):")
                for i, pos in enumerate(trades[:show], 1):
                    print(f"\n   历史订单 {i}:")
                    print(f"     市场名称: {pos.get('market_name', pos.get('market', '未知'))}")
                    print(f"     市场ID: {pos.get('market', '')[:20]}...")
                    print(f"     结果: {pos.get('outcome', '')}")
                    print(f"     方向: {pos.get('side', '')}")
                    trader_side = pos.get('trader_side', '').upper() if pos.get('trader_side') else ''
                    print(f"     Taker Or Maker: {trader_side if trader_side else '未知'}")
                    print(f"     数量: {pos.get('size', 0)}")
                    print(f"     价格: ${pos.get('price', 0):.4f}")
                    fee_rate = pos.get('fee_rate_bps', 0)
                    if fee_rate:
                        # Polymarket API 返回的 fee_rate_bps 需要除以 10000 才能得到百分比
                        # 例如: 1000 -> 0.1%, 3000 -> 0.3%
                        fee_percent = float(fee_rate) / 10000  # 转换为百分比
                        fee_bps = float(fee_rate) / 100  # 转换为标准 bps (1000 -> 10 bps)
                        print(f"     费率: {fee_bps:.0f} bps ({fee_percent:.2f}%)")
                    match_time = pos.get('match_time', 0)
                    match_time_readable = pos.get('match_time_readable', timestamp_to_readable(match_time))
                    print(f"     时间戳: {match_time} (成交时间: {match_time_readable})")
                    print(f"     状态: {pos.get('status', '')}")
                    if pos.get('transaction_hash'):
                        print(f"     交易哈希: {pos.get('transaction_hash')}")
                
                if len(trades) > show:
                    print(f"\n   ... 还有 {len(trades) - show} 个历史订单未显示")
            
            if orders:
                print(f"\n   📋 未完成订单 ({len(orders)} 个):")
                for i, pos in enumerate(orders[:show], 1):
                    print(f"\n   订单 {i} (挂单):")
                    print(f"     市场名称: {pos.get('market_name', pos.get('market', '未知'))}")
                    print(f"     市场ID: {pos.get('market', '')[:20]}...")
                    print(f"     结果: {pos.get('outcome', '')}")
                    print(f"     方向: {pos.get('side', '')}")
                    trader_side = pos.get('trader_side', '').upper() if pos.get('trader_side') else ''
                    print(f"     Taker Or Maker: {trader_side if trader_side else '未知'}")
                    print(f"     数量: {pos.get('size_remaining', 0)} / {pos.get('original_size', 0)}")
                    print(f"     价格: ${pos.get('price', 0):.4f}")
                    fee_rate = pos.get('fee_rate_bps', 0)
                    if fee_rate:
                        # Polymarket API 返回的 fee_rate_bps 需要除以 10000 才能得到百分比
                        # 例如: 1000 -> 0.1%, 3000 -> 0.3%
                        fee_percent = float(fee_rate) / 10000  # 转换为百分比
                        fee_bps = float(fee_rate) / 100  # 转换为标准 bps (1000 -> 10 bps)
                        print(f"     费率: {fee_bps:.0f} bps ({fee_percent:.2f}%)")
                    created_at = pos.get('created_at', 0)
                    created_at_readable = pos.get('created_at_readable', timestamp_to_readable(created_at))
                    print(f"     时间戳: {created_at} (创建时间: {created_at_readable})")
                    print(f"     状态: {pos.get('status', '')}")
                
                if len(orders) > show:
                    print(f"\n   ... 还有 {len(orders) - show} 个订单未显示")
        else:
            print("   ✓ 当前没有持仓或订单")
        
        print("\n" + "=" * 70)
        print("查询完成")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n✗ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

