import json
import pandas as pd
from ..domain.ports.repository import RepositoryPort
from ..domain.entities.scraping import ScrapingData

class JsonRepository(RepositoryPort):
    def __init__(self, filename: str = "data.json"):
        self.filename = filename

    def save(self, data: ScrapingData) -> None:
        print(f"\nIniciando salvamento dos dados no arquivo {self.filename}")
        try:
            # Carrega dados existentes
            try:
                with open(self.filename, 'r') as f:
                    existing_data = json.load(f)
            except FileNotFoundError:
                existing_data = []

            # Adiciona novo dado
            existing_data.append({
                'url': data.url,
                'data': data.data
            })

            # Salva dados atualizados
            with open(self.filename, 'w') as f:
                json.dump(existing_data, f, indent=4)
            print(f"Dados salvos com sucesso. Total de registros: {len(existing_data)}")

        except Exception as e:
            raise Exception(f"Erro ao salvar dados: {str(e)}")

    def load(self) -> list[ScrapingData]:
        print(f"\nCarregando dados do arquivo {self.filename}")
        try:
            with open(self.filename, 'r') as f:
                data = json.load(f)
                result = [ScrapingData(item['url'], item['data']) for item in data]
                print(f"Dados carregados com sucesso. Total de registros: {len(result)}")
                return result
        except FileNotFoundError:
            print("Arquivo não encontrado. Retornando lista vazia.")
            return []
        except Exception as e:
            raise Exception(f"Erro ao carregar dados: {str(e)}")

    def export_to_excel(self, filename: str) -> None:
        print(f"\nIniciando exportação para Excel: {filename}")
        try:
            data = self.load()
            df = pd.DataFrame([item.data for item in data])
            df.to_excel(filename, index=False)
            print(f"Dados exportados com sucesso para {filename}. Total de registros: {len(df)}")
        except Exception as e:
            raise Exception(f"Erro ao exportar para Excel: {str(e)}")