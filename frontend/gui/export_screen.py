import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from backend.adapters.json_repository import JsonRepository

class ExportScreen:
    def __init__(self, parent):
        self.parent = parent
        self.export_window = None
        self.repository = JsonRepository()
        
    def show(self):
        if self.export_window is not None:
            return
            
        self.export_window = tk.Toplevel(self.parent)
        self.export_window.title("Exportar para Excel")
        self.export_window.geometry("400x200")
        self.export_window.transient(self.parent)
        self.export_window.grab_set()
        
        # Centraliza a janela
        self.export_window.update_idletasks()
        width = self.export_window.winfo_width()
        height = self.export_window.winfo_height()
        x = (self.export_window.winfo_screenwidth() // 2) - (width // 2)
        y = (self.export_window.winfo_screenheight() // 2) - (height // 2)
        self.export_window.geometry(f"{width}x{height}+{x}+{y}")
        
        # Frame principal
        frame = ttk.Frame(self.export_window, padding="20")
        frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Caminho do arquivo
        self.file_path = tk.StringVar()
        path_label = ttk.Label(frame, text="Salvar como:")
        path_label.grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        
        path_frame = ttk.Frame(frame)
        path_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 20))
        
        path_entry = ttk.Entry(path_frame, textvariable=self.file_path, width=40)
        path_entry.grid(row=0, column=0, padx=(0, 5))
        
        browse_button = ttk.Button(
            path_frame,
            text="Procurar",
            command=self.browse_file
        )
        browse_button.grid(row=0, column=1)
        
        # Botões de ação
        button_frame = ttk.Frame(frame)
        button_frame.grid(row=2, column=0, sticky=(tk.W, tk.E))
        
        export_button = ttk.Button(
            button_frame,
            text="Exportar",
            command=self.export
        )
        export_button.grid(row=0, column=0, padx=5)
        
        cancel_button = ttk.Button(
            button_frame,
            text="Cancelar",
            command=self.hide
        )
        cancel_button.grid(row=0, column=1, padx=5)
        
    def browse_file(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")]
        )
        if filename:
            self.file_path.set(filename)
            
    def export(self):
        if not self.file_path.get():
            messagebox.showerror(
                "Erro",
                "Por favor, selecione um local para salvar o arquivo"
            )
            return
        try:
            print("\nIniciando processo de exportação...")
            self.repository.export_to_excel(self.file_path.get())
            print("Exportação concluída com sucesso!")
            messagebox.showinfo(
                "Sucesso",
                "Dados exportados com sucesso para Excel!"
            )
            self.hide()
        except Exception as e:
            print(f"Erro durante a exportação: {str(e)}")
            messagebox.showerror(
                "Erro",
                f"Erro ao exportar dados: {str(e)}"
            )
            
            
    def hide(self):
        if self.export_window is not None:
            self.export_window.destroy()
            self.export_window = None