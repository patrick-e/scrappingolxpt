from abc import ABC, abstractmethod
from ..entities.scraping import ScrapingData

class ScrapingServicePort(ABC):
    @abstractmethod
    def extract_data(self, url: str, progress_callback=None) -> ScrapingData:
        """
        Extrai dados da URL fornecida
        
        Args:
            url: URL para extrair dados
            progress_callback: Função opcional para atualizar o progresso (recebe percentage e message)
        """
        pass

    @abstractmethod
    def transform_data(self, data: ScrapingData) -> dict:
        """Transforma os dados extraídos"""
        pass