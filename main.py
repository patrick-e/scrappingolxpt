from frontend.gui.main_window import MainWindow
from backend.adapters.scraping_adapter import BeautifulSoupAdapter
from backend.adapters.json_repository import JsonRepository
from backend.config.credentials import CredentialsManager
def main():
    print("\n=== Iniciando Web Scraping Tool ===")
    print("Inicializando componentes...")

    # Inicializa os adaptadores
    credentials_manager = CredentialsManager()
    scraping_service = BeautifulSoupAdapter()  # Credenciais serão carregadas quando necessário
    repository = JsonRepository()
    print("Componentes inicializados com sucesso")

    # Inicia a interface gráfica
    app = MainWindow(scraping_service, repository)
    app.run()

if __name__ == "__main__":
    main()