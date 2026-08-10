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

    def __init__(self, model_name: str = "bge-m3", cache_size: int = 1000,
                 backend: str = "ollama", ollama_base_url: str = "http://localhost:11434"):
        """
        初始化嵌入服务

        Args:
            model_name: 模型名称
                - backend="sentence_transformers": HuggingFace模型名（默认已废弃）
                - backend="ollama": Ollama中的模型名，如 "bge-m3", "nomic-embed-text"
            cache_size: 缓存大小，LRU缓存最近计算的嵌入
            backend: 后端类型，"ollama" 或 "sentence_transformers"
            ollama_base_url: Ollama 服务地址
        """
        self.model_name = model_name
        self.cache_size = cache_size
        self.backend = backend
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.model = None
        self.dimension = None
        self._initialized = False
        self._initialize_model()

        # 创建带缓存的嵌入函数
        self._embed_cached = lru_cache(maxsize=cache_size)(self._embed_uncached)
    
    def _initialize_model(self):
        """初始化嵌入模型"""
        if self.backend == "ollama":
            self._init_ollama_backend()
        else:
            self._init_sentence_transformers_backend()

    def _init_ollama_backend(self):
        """初始化 Ollama 嵌入后端"""
        # 先设置已知模型的维度（避免首次 embed 时额外调用）
        model_lower = self.model_name.lower()
        if "bge-m3" in model_lower:
            self.dimension = 1024
        elif "nomic-embed-text" in model_lower or "nomic" in model_lower:
            self.dimension = 768
        else:
            self.dimension = 1024  # 通用默认值

        # 验证 Ollama 服务是否可用
        try:
            import urllib.request
            req = urllib.request.Request(f"{self.ollama_base_url}/api/tags",
                                         method="GET",
                                         headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    self._initialized = True
                    print(f"✅ Ollama 嵌入后端就绪，模型: {self.model_name}，维度: {self.dimension}")
                else:
                    print(f"⚠️ Ollama 服务响应异常 (HTTP {resp.status})，使用随机嵌入后备")
        except Exception as e:
            print(f"⚠️ Ollama 服务不可用 ({e})，使用随机嵌入 + 关键词搜索后备")
            self._initialized = False

    def _init_sentence_transformers_backend(self):
        """初始化 sentence-transformers 嵌入后端（保留兼容）"""
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            print("⚠️ sentence-transformers 未安装，使用随机嵌入作为后备方案")
            self.model = None
            self.dimension = 384
            self._initialized = False
            return

        import threading

        result = [None]
        exception = [None]
        done = threading.Event()

        def load_model():
            try:
                model = SentenceTransformer(self.model_name, device='cpu', local_files_only=True)
                result[0] = model
            except Exception:
                try:
                    model = SentenceTransformer(self.model_name, device='cpu')
                    result[0] = model
                except Exception as e:
                    exception[0] = e
            finally:
                done.set()

        t = threading.Thread(target=load_model, daemon=True)
        t.start()

        if done.wait(timeout=18):
            if exception[0]:
                print(f"⚠️ 无法加载嵌入模型 '{self.model_name}': {exception[0]}")
                self.model = None
                self.dimension = 384
                self._initialized = False
            else:
                self.model = result[0]
                try:
                    test_embedding = self.model.encode(["test"])
                    self.dimension = len(test_embedding[0])
                    self._initialized = True
                    print(f"✅ 嵌入模型 '{self.model_name}' 初始化成功，维度: {self.dimension}")
                except Exception as e:
                    print(f"⚠️ 嵌入模型加载不完整: {e}")
                    self.model = None
                    self.dimension = 384
                    self._initialized = False
        else:
            print(f"⚠️ 加载嵌入模型 '{self.model_name}' 超时（网络不可用）")
            self.model = None
            self.dimension = 384
            self._initialized = False
    
    def _normalize_text(self, text: str) -> str:
        """归一化文本，去除常见前缀结构，让 embedding 聚焦在内容语义"""
        import re
        # 去除常见 pattern（按特异性从高到低排列）
        patterns = [
            # 用户信息类事实前缀
            r'^用户(?:手机号|职业|偏好|爱好|名字|姓名|叫|人称)\s*[:：]?\s*',
            r'^用户(?:是|喜欢|热爱|热衷于|平时|爱)\s*',
            # 自我介绍前缀
            r'^(?:我是|我叫|我的名字叫?|名字叫?|我的职业是|我是一个|我是一名?|我的电话|我的手机|手机号)\s*',
            r'^(?:我喜欢|我平时|我爱|我热衷于|我爱好|我是一名?)\s*',
            # 其他常见前缀
            r'^用户要求学习:\s*',
        ]
        for p in patterns:
            text = re.sub(p, '', text, count=1)
        return text.strip()

    def _ollama_embed(self, text: str) -> list:
        """通过 Ollama API 获取嵌入向量"""
        normalized = self._normalize_text(text)
        import urllib.request
        import json
        data = json.dumps({"model": self.model_name, "input": [normalized]}).encode()
        req = urllib.request.Request(
            f"{self.ollama_base_url}/api/embed",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
        return result["embeddings"][0]

    def _ollama_embed_batch(self, texts: list, batch_size: int = 32) -> list:
        """通过 Ollama API 批量获取嵌入向量"""
        # 批量归一化
        normalized_batch = [self._normalize_text(t) for t in texts if t and t.strip()]
        if not normalized_batch:
            return []
        import urllib.request
        import json
        data = json.dumps({"model": self.model_name, "input": normalized_batch}).encode()
        req = urllib.request.Request(
            f"{self.ollama_base_url}/api/embed",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())
        return result["embeddings"]

    def _embed_uncached(self, text: str) -> List[float]:
        """不带缓存的嵌入计算（真实嵌入，失败时抛异常由 embed() 走不缓存随机回退）"""
        if self.backend == "ollama" and self._initialized:
            return self._ollama_embed(text)
        elif self.model is not None:
            # 使用Sentence Transformers
            embedding = self.model.encode([text])[0]
            return embedding.tolist()
        else:
            # 未就绪：抛异常，避免随机向量进入 lru_cache（服务恢复后缓存仍是随机值）
            raise RuntimeError(f"嵌入后端未就绪 (backend={self.backend})")

    def _random_embed(self, text: str) -> List[float]:
        """确定性随机向量后备方案"""
        import hashlib
        seed = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
        # 用局部 RNG（default_rng），不污染全局 numpy 随机状态（线程安全）
        rng = np.random.default_rng(seed)
        return rng.standard_normal(self.dimension).tolist()
    
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
                self.logger.debug(f"嵌入计算失败，随机回退(不缓存): {str(e)}")
            # 返回随机向量作为后备（不经过 lru_cache，避免服务恢复后仍用随机值）
            return self._random_embed(text.strip())
    
    def embed_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        批量嵌入计算

        Args:
            texts: 文本列表
            batch_size: 批处理大小（Ollama 后端会一次性发送全部）

        Returns:
            向量嵌入列表
        """
        if not texts:
            return []

        # 过滤空文本
        valid_texts = [t.strip() for t in texts if t and t.strip()]
        if not valid_texts:
            return [[] for _ in texts]

        # Ollama 后端 — 支持批量
        if self.backend == "ollama" and self._initialized:
            try:
                ollama_embs = self._ollama_embed_batch(valid_texts, batch_size)
                result = []
                emb_idx = 0
                for original_text in texts:
                    if original_text and original_text.strip():
                        result.append(ollama_embs[emb_idx])
                        emb_idx += 1
                    else:
                        result.append([0.0] * self.dimension)
                return result
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Ollama批量嵌入失败: {str(e)}")
                # 逐个回退
                return [self.embed(text) for text in texts]

        # Sentence Transformers 后端
        if self.model is not None:
            try:
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
        if self.backend == "ollama":
            return self._initialized
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