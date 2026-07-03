"""
嵌入服务模块
提供文本向量化功能，支持多种嵌入模型
"""

import os
import numpy as np
from typing import List, Dict, Any, Optional
from functools import lru_cache

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

try:
    import chromadb.utils.embedding_functions as embedding_functions
    CHROMA_EMBEDDING_AVAILABLE = True
except Exception:
    # chromadb 不兼容 Python 3.14+ (pydantic v1 + Pydantic v1 ConfigError)
    CHROMA_EMBEDDING_AVAILABLE = False


class EmbeddingService:
    """嵌入服务类
    
    提供文本向量化功能，支持多种嵌入模型和缓存机制。
    """
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", cache_size: int = 1000):
        """
        初始化嵌入服务
        
        Args:
            model_name: 嵌入模型名称
                - "all-MiniLM-L6-v2": 小型高效模型 (384维)
                - "all-mpnet-base-v2": 高质量模型 (768维)
                - "text-embedding-ada-002": OpenAI模型 (需要API)
                - 或其他Sentence Transformers模型
            cache_size: 缓存大小，LRU缓存最近计算的嵌入
        """
        self.model_name = model_name
        self.cache_size = cache_size
        self.model = None
        self.dimension = None
        self._initialize_model()
        
        # 创建带缓存的嵌入函数
        self._embed_cached = lru_cache(maxsize=cache_size)(self._embed_uncached)
    
    def _initialize_model(self):
        """初始化嵌入模型（先尝试本地缓存，避免网络阻塞）"""
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            print("⚠️ sentence-transformers 未安装，使用随机嵌入作为后备方案")
            self.model = None
            self.dimension = 384
            return

        import threading

        result = [None]
        exception = [None]
        done = threading.Event()

        def load_model():
            try:
                # 先尝试本地缓存（不联网）
                model = SentenceTransformer(self.model_name, device='cpu', local_files_only=True)
                result[0] = model
            except Exception:
                # 缓存未命中 - 尝试联网下载（带15秒超时）
                try:
                    model = SentenceTransformer(self.model_name, device='cpu')
                    result[0] = model
                except Exception as e:
                    exception[0] = e
            finally:
                done.set()

        t = threading.Thread(target=load_model, daemon=True)
        t.start()

        # 等待最多 18 秒（本地缓存快速 + 联网重试缓冲）
        if done.wait(timeout=18):
            if exception[0]:
                print(f"⚠️ 无法加载嵌入模型 '{self.model_name}': {exception[0]}")
                print("⚠️ 将使用随机嵌入 + 关键词搜索作为后备方案")
                self.model = None
                self.dimension = 384
            else:
                self.model = result[0]
                try:
                    test_embedding = self.model.encode(["test"])
                    self.dimension = len(test_embedding[0])
                    print(f"✅ 嵌入模型 '{self.model_name}' 初始化成功，维度: {self.dimension}")
                except Exception as e:
                    print(f"⚠️ 嵌入模型加载不完整: {e}")
                    self.model = None
                    self.dimension = 384
        else:
            print(f"⚠️ 加载嵌入模型 '{self.model_name}' 超时（网络不可用）")
            print("⚠️ 将使用随机嵌入 + 关键词搜索作为后备方案")
            self.model = None
            self.dimension = 384
    
    def _embed_uncached(self, text: str) -> List[float]:
        """不带缓存的嵌入计算"""
        if self.model is not None:
            # 使用Sentence Transformers
            embedding = self.model.encode([text])[0]
            return embedding.tolist()
        else:
            # 后备方案：生成确定性随机向量
            # 使用文本哈希作为随机种子，确保相同文本生成相同向量
            import hashlib
            seed = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
            np.random.seed(seed)
            return np.random.randn(self.dimension).tolist()
    
    def embed(self, text: str) -> List[float]:
        """
        将文本转换为向量嵌入
        
        Args:
            text: 输入文本
            
        Returns:
            向量嵌入列表
        """
        if not text or not text.strip():
            # 空文本返回零向量
            return [0.0] * self.dimension
        
        try:
            return self._embed_cached(text.strip())
        except Exception as e:
            if self.logger:
                self.logger.error(f"嵌入计算失败: {str(e)}")
            # 返回随机向量作为后备
            import hashlib
            seed = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
            np.random.seed(seed)
            return np.random.randn(self.dimension).tolist()
    
    def embed_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        批量嵌入计算
        
        Args:
            texts: 文本列表
            batch_size: 批处理大小
            
        Returns:
            向量嵌入列表
        """
        if not texts:
            return []
        
        # 过滤空文本
        valid_texts = [t.strip() for t in texts if t and t.strip()]
        if not valid_texts:
            return [[] for _ in texts]
        
        if self.model is not None:
            try:
                # 批量计算嵌入
                embeddings = self.model.encode(valid_texts, batch_size=batch_size)
                result = []
                text_idx = 0
                
                for original_text in texts:
                    if original_text and original_text.strip():
                        result.append(embeddings[text_idx].tolist())
                        text_idx += 1
                    else:
                        result.append([0.0] * self.dimension)
                
                return result
                
            except Exception as e:
                if self.logger:
                    self.logger.error(f"批量嵌入计算失败: {str(e)}")
        
        # 后备方案：逐个计算
        return [self.embed(text) for text in texts]
    
    def get_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """
        计算两个嵌入的余弦相似度
        
        Args:
            embedding1: 第一个嵌入向量
            embedding2: 第二个嵌入向量
            
        Returns:
            余弦相似度 (-1 到 1)
        """
        if not embedding1 or not embedding2:
            return 0.0
        
        # 转换为numpy数组
        v1 = np.array(embedding1)
        v2 = np.array(embedding2)
        
        # 计算余弦相似度
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return np.dot(v1, v2) / (norm1 * norm2)
    
    def is_ready(self) -> bool:
        """检查嵌入服务是否就绪"""
        return self.model is not None

    def set_logger(self, logger):
        """设置日志记录器"""
        self.logger = logger
    
    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        return {
            "model_name": self.model_name,
            "dimension": self.dimension,
            "cache_size": self.cache_size,
            "model_available": self.model is not None
        }


class ChromaEmbeddingFunction:
    """Chroma兼容的嵌入函数包装器"""
    
    def __init__(self, embedding_service: EmbeddingService):
        self.embedding_service = embedding_service
    
    def __call__(self, texts: List[str]) -> List[List[float]]:
        """Chroma嵌入函数接口"""
        return self.embedding_service.embed_batch(texts)


def create_default_embedding_service() -> EmbeddingService:
    """创建默认的嵌入服务实例"""
    return EmbeddingService(model_name="all-MiniLM-L6-v2")


def test_embedding_service():
    """测试嵌入服务"""
    print("🧪 测试嵌入服务...")
    
    # 创建嵌入服务
    service = create_default_embedding_service()
    
    # 测试单个嵌入
    text1 = "这是一个测试句子"
    embedding1 = service.embed(text1)
    print(f"✅ 文本1嵌入维度: {len(embedding1)}")
    
    # 测试相同文本生成相同嵌入
    embedding1_again = service.embed(text1)
    similarity = service.get_similarity(embedding1, embedding1_again)
    print(f"✅ 相同文本相似度: {similarity:.6f} (应该接近1.0)")
    
    # 测试不同文本
    text2 = "这是另一个不同的句子"
    embedding2 = service.embed(text2)
    similarity = service.get_similarity(embedding1, embedding2)
    print(f"✅ 不同文本相似度: {similarity:.6f} (应该小于1.0)")
    
    # 测试批量嵌入
    texts = ["句子1", "句子2", "句子3"]
    embeddings = service.embed_batch(texts)
    print(f"✅ 批量嵌入: {len(embeddings)} 个嵌入，每个 {len(embeddings[0])} 维")
    
    # 获取模型信息
    info = service.get_model_info()
    print(f"✅ 模型信息: {info}")
    
    print("🎉 嵌入服务测试完成")
    return service


if __name__ == "__main__":
    test_embedding_service()


__all__ = [
    'EmbeddingService',
    'ChromaEmbeddingFunction',
    'create_default_embedding_service',
    'test_embedding_service',
]