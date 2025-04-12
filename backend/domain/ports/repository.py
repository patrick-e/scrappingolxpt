from abc import ABC, abstractmethod
from ..entities.scraping import ScrapingData

class RepositoryPort(ABC):
    @abstractmethod
    def save(self, data: ScrapingData) -> None:
        """Salva os dados extraídos"""
        pass

    @abstractmethod
    def load(self) -> list[ScrapingData]:
        """Carrega os dados salvos"""
        pass

    @abstractmethod
    def export_to_excel(self, filename: str) -> None:
        """Exporta os dados para Excel"""
        pass