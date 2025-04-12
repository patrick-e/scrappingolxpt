from frontend.gui.main_window import MainWindow
from backend.adapters.scraping_adapter import BeautifulSoupAdapter
from backend.adapters.json_repository import JsonRepository

def main():
    print("\n=== Iniciando Web Scraping Tool ===")
    print("Inicializando componentes...")

    # Inicializa os adaptadores
    scraping_service = BeautifulSoupAdapter()  # Proxies serão buscados automaticamente
    repository = JsonRepository()
    print("Componentes inicializados com sucesso")

    # Inicia a interface gráfica
    app = MainWindow(scraping_service, repository)
    app.run()

if __name__ == "__main__":
    main()