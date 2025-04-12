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
        
        # Campo de URL
        self.url_label = ttk.Label(self.main_frame, text="URL:")
        self.url_label.grid(row=0, column=0, padx=5, pady=5)
        
        self.url_entry = ttk.Entry(self.main_frame, width=50)
        self.url_entry.grid(row=0, column=1, padx=5, pady=5)
        # Adiciona bind para tecla Enter
        self.url_entry.bind('<Return>', lambda e: self.start_scraping())
        
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
        # Botão de iniciar scraping
        self.start_button = ttk.Button(
            self.main_frame,
            text="Iniciar Scraping",
            command=lambda: self.start_scraping()  # Usando lambda para manter consistência com o bind do Enter
        )
        self.start_button.grid(row=2, column=0, columnspan=2, pady=10)
        
        
        # Esconde componentes de progresso inicialmente
        self.progress_label.grid_remove()
        self.progress_bar.grid_remove()
    def start_scraping(self, event=None):  # Adicionado parâmetro event para suportar bind do Enter
        # Solicita login antes de iniciar o scraping
        if not request_login(self.root):
            messagebox.showerror("Erro", "É necessário fazer login para continuar")
            return

        url = self.url_entry.get().strip()  # Remove espaços em branco
        if not url:
            messagebox.showerror("Erro", "Por favor, insira uma URL válida")
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
        self.url_entry.configure(state='disabled')
        self.start_button.configure(state='disabled')
        self.progress_label.configure(text="Iniciando extração...\nPor favor, aguarde.")
        self.progress_label.grid()
        self.progress_bar.grid()
        self.progress_bar.start(10)
        
    def hide_processing_state(self):
        self.is_processing = False
        self.url_entry.configure(state='normal')
        self.start_button.configure(state='normal')
        
        self.progress_label.grid_remove()
        self.progress_bar.grid_remove()
        
    def update_progress(self, percentage, message):
        self.progress_bar['value'] = percentage
        self.progress_label.configure(text=message)
        self.root.update()
        
    def run(self):
        print("\nInterface iniciada. Aguardando entrada de URL...")
        self.root.mainloop()