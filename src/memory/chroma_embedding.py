"""
Chroma兼容的嵌入函数模块
专门处理Chroma 1.x版本的嵌入函数接口
"""

from typing import List, Optional
from .embedding_service import EmbeddingService


class ChromaEmbeddingFunction:
    """Chroma兼容的嵌入函数包装器
    
    适用于Chroma 1.x版本的嵌入函数接口。
    """
    
    def __init__(self, embedding_service: EmbeddingService):
        self.embedding_service = embedding_service
    
    def __call__(self, input: List[str]) -> List[List[float]]:
        """Chroma嵌入函数接口
        
        Args:
            input: 输入文本列表
            
        Returns:
            嵌入向量列表
        """
        return self.embedding_service.embed_batch(input)
    
    def embed_documents(self, documents: List[str]) -> List[List[float]]:
        """为文档生成嵌入
        
        Args:
            documents: 文档文本列表
            
        Returns:
            嵌入向量列表
        """
        return self.embedding_service.embed_batch(documents)
    
    def embed_query(self, query: str) -> List[float]:
        """为查询生成嵌入
        
        Args:
            query: 查询文本
            
        Returns:
            嵌入向量
        """
        return self.embedding_service.embed(query)


class SimpleEmbeddingFunction:
    """简单的嵌入函数实现，用于测试或简单场景"""
    
    def __init__(self, dimension: int = 384):
        self.dimension = dimension
    
    def __call__(self, input: List[str]) -> List[List[float]]:
        """简单的嵌入函数接口
        
        生成确定性随机向量作为嵌入
        """
        import numpy as np
        import hashlib
        
        embeddings = []
        for text in input:
            if not text or not text.strip():
                embeddings.append([0.0] * self.dimension)
                continue
            
            # 使用文本哈希作为随机种子，确保相同文本生成相同向量
            seed = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
            np.random.seed(seed)
            embeddings.append(np.random.randn(self.dimension).tolist())
        
        return embeddings


def create_chroma_embedding_function(embedding_service: Optional[EmbeddingService] = None):
    """创建Chroma兼容的嵌入函数
    
    Args:
        embedding_service: 嵌入服务实例，如果为None则创建默认实例
        
    Returns:
        ChromaEmbeddingFunction实例
    """
    if embedding_service is None:
        embedding_service = EmbeddingService()
    return ChromaEmbeddingFunction(embedding_service)


def test_chroma_embedding():
    """测试Chroma嵌入函数"""
    print("🧪 测试Chroma嵌入函数...")
    
    try:
        # 创建嵌入服务
        from .embedding_service import EmbeddingService
        embedding_service = EmbeddingService()
        
        # 创建Chroma嵌入函数
        chroma_embedding = create_chroma_embedding_function(embedding_service)
        
        # 测试批量嵌入
        texts = ["测试文本1", "测试文本2", "测试文本3"]
        embeddings = chroma_embedding(texts)
        
        print(f"✅ 批量嵌入测试成功，生成了 {len(embeddings)} 个嵌入")
        print(f"✅ 每个嵌入维度: {len(embeddings[0])}")
        
        # 测试文档嵌入方法
        doc_embeddings = chroma_embedding.embed_documents(texts)
        print(f"✅ 文档嵌入测试成功，生成了 {len(doc_embeddings)} 个文档嵌入")
        
        # 测试查询嵌入方法
        query_embedding = chroma_embedding.embed_query("测试查询")
        print(f"✅ 查询嵌入测试成功，嵌入维度: {len(query_embedding)}")
        
        # 测试简单嵌入函数
        simple_embedding = SimpleEmbeddingFunction(dimension=384)
        simple_embeddings = simple_embedding(texts)
        print(f"✅ 简单嵌入函数测试成功，生成了 {len(simple_embeddings)} 个嵌入")
        
        print("🎉 Chroma嵌入函数测试完成")
        return True
        
    except Exception as e:
        print(f"❌ Chroma嵌入函数测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_chroma_embedding()


__all__ = [
    'ChromaEmbeddingFunction',
    'SimpleEmbeddingFunction',
    'create_chroma_embedding_function',
    'test_chroma_embedding',
]