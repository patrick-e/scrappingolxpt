import tkinter as tk
from tkinter import ttk, messagebox
from .export_screen import ExportScreen
from .login_screen import request_login

class MainWindow:
    def __init__(self, scraping_service, repository):
        # Recebe os adaptadores via construtor
        self.scraping_service = scraping_service
        self.repository = repository
        
        self.root = tk.Tk()
        self.root.title("Web Scraping Tool")
        self.root.geometry("600x400")
        
        # Configuração do layout principal
        self.setup_layout()
        
        # Componentes
        self.export_screen = ExportScreen(self.root)
        self.is_processing = False
        
    def setup_layout(self):
        # Frame principal
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Frame para centralizar os botões
        button_frame = ttk.Frame(self.main_frame)
        button_frame.grid(row=0, column=0, columnspan=2, pady=20)
        
        # Botões de pesquisa centralizados
        self.recent_button = ttk.Button(
            button_frame,
            text="Mais Recentes",
            width=20,
            command=lambda: self.start_scraping("https://www.olx.pt/ads/?search%5Border%5D=created_at:desc")
        )
        self.recent_button.grid(row=0, column=0, padx=10, pady=5)
        
        self.relevant_button = ttk.Button(
            button_frame,
            text="Principais",
            width=20,
            command=lambda: self.start_scraping("https://www.olx.pt/ads/?search%5Border%5D=relevance:desc")
        )
        self.relevant_button.grid(row=0, column=1, padx=10, pady=5)
        
        # Frame para progresso
        self.progress_frame = ttk.Frame(self.main_frame)
        self.progress_frame.grid(row=1, column=0, columnspan=2, pady=10)
        
        # Mensagem de progresso
        self.progress_label = ttk.Label(
            self.progress_frame,
            text="",
            justify=tk.CENTER
        )
        self.progress_label.grid(row=0, column=0, pady=(0, 5))
        
        # Barra de progresso
        self.progress_bar = ttk.Progressbar(
            self.progress_frame,
            mode='determinate',
            length=300
        )
        self.progress_bar.grid(row=1, column=0)
        # Esconde componentes de progresso inicialmente
        self.progress_label.grid_remove()
        self.progress_bar.grid_remove()
    def start_scraping(self, url):
        # Solicita login antes de iniciar o scraping
        if not request_login(self.root):
            messagebox.showerror("Erro", "É necessário fazer login para continuar")
            return

            
        print(f"\nIniciando scraping para URL: {url}")
        self.show_processing_state()
        self.root.update()  # Força atualização da interface

        try:
            # Extrai dados
            print("Iniciando extração de dados...")
            scraping_data = self.scraping_service.extract_data(url, self.update_progress)
            
            # Transforma dados
            print("Transformando dados extraídos...")
            transformed_data = self.scraping_service.transform_data(scraping_data)
            
            # Salva dados
            print("Salvando dados processados...")
            self.repository.save(scraping_data)
            
            # Atualiza interface
            self.hide_processing_state()
            print("Operação concluída com sucesso!")
            messagebox.showinfo("Sucesso", f"Dados extraídos e salvos com sucesso!\nForam processados {len(scraping_data.data)} itens.")
            
        except Exception as e:
            print(f"Erro durante o processamento: {str(e)}")
            self.hide_processing_state()
            messagebox.showerror("Erro", str(e))
        
    def show_processing_state(self):
        self.is_processing = True
        self.recent_button.configure(state='disabled')
        self.relevant_button.configure(state='disabled')
        self.progress_label.configure(text="Iniciando extração...\nPor favor, aguarde.")
        self.progress_label.grid()
        self.progress_bar.grid()
        self.progress_bar.start(10)
        
    def hide_processing_state(self):
        self.is_processing = False
        self.recent_button.configure(state='normal')
        self.relevant_button.configure(state='normal')
        
        self.progress_label.grid_remove()
        self.progress_bar.grid_remove()
        
    def update_progress(self, percentage, message):
        self.progress_bar['value'] = percentage
        self.progress_label.configure(text=message)
        self.root.update()
        
    def run(self):
        print("\nInterface iniciada. Selecione 'Mais Recentes' ou 'Principais' para iniciar o scraping...")
        self.root.mainloop()