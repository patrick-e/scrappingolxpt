import tkinter as tk
from tkinter import ttk, messagebox
from backend.config.credentials import CredentialsManager

class LoginScreen:
    def __init__(self, parent):
        self.parent = parent
        self.window = tk.Toplevel(parent)
        self.window.title("Login OLX")
        self.window.geometry("300x200")
        self.window.resizable(False, False)
        
        # Centraliza a janela
        self.window.transient(parent)
        self.window.grab_set()
        
        # Frames
        main_frame = ttk.Frame(self.window, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Widgets
        ttk.Label(main_frame, text="Email:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.email_var = tk.StringVar()
        self.email_entry = ttk.Entry(main_frame, textvariable=self.email_var, width=30)
        self.email_entry.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(main_frame, text="Senha:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(main_frame, textvariable=self.password_var, show="*", width=30)
        self.password_entry.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=5)
        
        # Botão de login
        self.login_button = ttk.Button(main_frame, text="Login", command=self.save_credentials)
        self.login_button.grid(row=4, column=0, sticky=(tk.W, tk.E), pady=20)
        
        # Configura comportamento ao fechar a janela
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Foca no primeiro campo
        self.email_entry.focus()
        
        # Resultado do login
        self.login_success = False
        
    def save_credentials(self):
        """Salva as credenciais e fecha a janela"""
        email = self.email_var.get().strip()
        password = self.password_var.get().strip()
        
        if not email or not password:
            messagebox.showerror("Erro", "Por favor, preencha todos os campos")
            return
        
        try:
            credentials = CredentialsManager()
            credentials.save_credentials(email, password)
            self.login_success = True
            self.window.destroy()
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao salvar credenciais: {str(e)}")
    
    def on_close(self):
        """Chamado quando a janela é fechada"""
        if not self.login_success:
            if messagebox.askokcancel("Sair", "Você precisa fazer login para continuar. Deseja realmente sair?"):
                self.window.destroy()
        else:
            self.window.destroy()

def request_login(parent):
    """
    Solicita login ao usuário.
    Retorna True se as credenciais foram salvas com sucesso.
    """
    login_screen = LoginScreen(parent)
    parent.wait_window(login_screen.window)
    return login_screen.login_success