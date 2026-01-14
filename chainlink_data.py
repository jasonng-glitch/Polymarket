"""
Chainlink BTC/USD 当前价格读取
"""

from typing import Optional, Dict, Any
from datetime import datetime
from web3 import Web3
from web3.contract import Contract


class ChainlinkDataLoader:
    """
    Chainlink BTC/USD 价格数据加载器
    用于读取当前 BTC/USD 价格
    """
    
    # Chainlink AggregatorV3Interface ABI (只包含最新价格查询)
    AGGREGATOR_V3_INTERFACE_ABI = [
        {
            "inputs": [],
            "name": "latestRoundData",
            "outputs": [
                {"internalType": "uint80", "name": "roundId", "type": "uint80"},
                {"internalType": "int256", "name": "answer", "type": "int256"},
                {"internalType": "uint256", "name": "startedAt", "type": "uint256"},
                {"internalType": "uint256", "name": "updatedAt", "type": "uint256"},
                {"internalType": "uint80", "name": "answeredInRound", "type": "uint80"}
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "decimals",
            "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
            "stateMutability": "view",
            "type": "function"
        }
    ]
    
    # Polygon 网络上 Chainlink BTC/USD 代理合约地址
    POLYGON_BTC_USD_PROXY = "0xc907E116054Ad103354f2D350FD2514433D57F6f"
    
    def __init__(self, rpc_url: str, network: str = "polygon"):
        """
        初始化 Chainlink 数据加载器
        
        Args:
            rpc_url: RPC 节点 URL (例如: Infura, Alchemy, 或公共节点)
            network: 网络名称 (polygon, ethereum 等)
        """
        self.rpc_url = rpc_url
        self.network = network
        self.web3: Optional[Web3] = None
        self._connect()
    
    def _connect(self) -> None:
        """连接到区块链网络"""
        try:
            self.web3 = Web3(Web3.HTTPProvider(self.rpc_url))
            if not self.web3.is_connected():
                raise ConnectionError(f"无法连接到 {self.network} 网络: {self.rpc_url}")
        except Exception as e:
            raise ConnectionError(f"连接失败: {str(e)}")
    
    def get_price_feed_contract(self, proxy_address: str) -> Contract:
        """
        获取价格预言机合约实例
        
        Args:
            proxy_address: Chainlink 代理合约地址
            
        Returns:
            Web3 合约实例
        """
        if not self.web3:
            raise RuntimeError("Web3 连接未初始化")
        
        checksum_address = Web3.to_checksum_address(proxy_address)
        contract = self.web3.eth.contract(
            address=checksum_address,
            abi=self.AGGREGATOR_V3_INTERFACE_ABI
        )
        return contract
    
    def get_btc_usd_price(self, proxy_address: Optional[str] = None) -> Dict[str, Any]:
        """
        获取当前的 BTC/USD 价格
        
        Args:
            proxy_address: 代理合约地址，如果为 None 则使用默认的 Polygon BTC/USD 地址
            
        Returns:
            包含价格信息的字典：
            - price: BTC/USD 价格
            - updatedAt: 更新时间戳（Unix 秒）
            - updatedAtReadable: 可读时间格式
            - roundId: 当前轮次 ID
        """
        if proxy_address is None:
            proxy_address = self.POLYGON_BTC_USD_PROXY
        
        contract = self.get_price_feed_contract(proxy_address)
        decimals = contract.functions.decimals().call()
        latest_data = contract.functions.latestRoundData().call()
        
        round_id, answer, started_at, updated_at, answered_in_round = latest_data
        price = float(answer) / (10 ** decimals)
        
        # 转换为可读时间格式
        updated_at_readable = datetime.fromtimestamp(updated_at).strftime("%Y-%m-%d %H:%M:%S")
        
        return {
            'price': price,
            'roundId': round_id,
            'updatedAt': updated_at,
            'updatedAtReadable': updated_at_readable,
            'decimals': decimals
        }


# 使用示例
if __name__ == "__main__":
    # 示例：使用公共 RPC 节点（可能需要替换为您的 RPC URL）
    RPC_URL = "https://polygon-rpc.com"  # 公共节点，可以替换为 Infura、Alchemy 等
    
    try:
        loader = ChainlinkDataLoader(rpc_url=RPC_URL)
        price_data = loader.get_btc_usd_price()
        
        print(f"BTC/USD 价格: ${price_data['price']:,.2f}")
        print(f"更新时间: {price_data['updatedAtReadable']}")
        print(f"轮次 ID: {price_data['roundId']}")
    except Exception as e:
        print(f"错误: {e}")
